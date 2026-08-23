"""End-to-end Home Assistant lifecycle tests for fresh registry identities."""

from __future__ import annotations

from collections.abc import Mapping
from unittest.mock import patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_TOKEN, CONF_URL, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.meshmonitor.const import (
    CONF_NODE_DEVICE_POLICY,
    CONF_SERVER_OPTIONS,
    CONF_SOURCE_ID,
    CONF_SOURCE_NAME,
    CONF_SOURCE_OPTIONS,
    CONF_SOURCE_TYPE,
    CONF_SOURCES,
    DOMAIN,
    NODE_DEVICE_POLICY_ALL,
)
from custom_components.meshmonitor.registry import (
    node_device_identifier,
    node_entity_unique_id,
    server_fingerprint,
    source_device_identifier,
    source_entity_unique_id,
)
from custom_components.meshmonitor.vendor_meshmonitor_client import (
    MeshMonitorConnectionError,
    Node,
    SourceSnapshot,
    SourceStatus,
)

SERVER_A_URL = "https://alpha.mesh.invalid/base"
SERVER_B_URL = "https://bravo.mesh.invalid/base"


def _entry(
    url: str,
    sources: tuple[tuple[str, str], ...],
) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title=url.removeprefix("https://"),
        data={
            CONF_URL: url,
            CONF_TOKEN: "synthetic-token",
            CONF_SOURCES: [
                {
                    CONF_SOURCE_ID: source_id,
                    CONF_SOURCE_NAME: source_name,
                    CONF_SOURCE_TYPE: "meshtastic",
                }
                for source_id, source_name in sources
            ],
        },
        options={
            CONF_SERVER_OPTIONS: {
                "enable_sidebar_panel": False,
                CONF_NODE_DEVICE_POLICY: NODE_DEVICE_POLICY_ALL,
            },
            CONF_SOURCE_OPTIONS: {
                source_id: {
                    "scan_interval": 3600,
                    "enable_message_polling": False,
                    "enable_device_trackers": True,
                }
                for source_id, _source_name in sources
            },
        },
        version=2,
        unique_id=server_fingerprint(url),
    )


def _node(
    node_id: str,
    long_name: str | None,
    *,
    short_name: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
) -> Node:
    data: dict[str, object] = {
        "id": node_id,
        "lastHeard": "2026-08-17T12:00:00Z",
    }
    if long_name is not None:
        data["longName"] = long_name
    if short_name is not None:
        data["shortName"] = short_name
    if latitude is not None:
        data["latitude"] = latitude
    if longitude is not None:
        data["longitude"] = longitude
    return Node.from_dict(data)


def _snapshot(source_id: str, nodes: list[Node]) -> SourceSnapshot:
    return SourceSnapshot.create(
        source_id,
        SourceStatus.from_dict({"connected": True}),
        nodes,
        None,
        [],
        {},
    )


class _ScriptedClient:
    """Return one synthetic snapshot or failure per source refresh."""

    def __init__(
        self,
        script: Mapping[str, list[SourceSnapshot | Exception]],
    ) -> None:
        self._script = script

    async def get_snapshot(self, source_id: str) -> SourceSnapshot:
        result = self._script[source_id].pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def _entry_entities(
    registry: er.EntityRegistry, entry: MockConfigEntry
) -> dict[str, er.RegistryEntry]:
    return {
        item.unique_id: item
        for item in er.async_entries_for_config_entry(registry, entry.entry_id)
    }


async def test_platform_registry_persists_across_failure_reappearance_and_restart(
    hass: HomeAssistant,
) -> None:
    """Exercise real platform registration, reload, and restart-shaped setup."""
    server_a = _entry(
        SERVER_A_URL,
        (("source-a", "Alpha"), ("source-b", "Bravo")),
    )
    server_b = _entry(SERVER_B_URL, (("source-a", "Other alpha"),))
    server_a.add_to_hass(hass)
    server_b.add_to_hass(hass)

    initial_nodes = [
        _node("shared-node", "Relay.One", latitude=40.0, longitude=-74.0),
        _node("punctuated-node", "Relay One"),
        _node("!abcd1234", None),
        _node("foreign-node", "Foreign Collision"),
    ]
    renamed_nodes = [
        _node("shared-node", "Renamed after setup", latitude=40.0, longitude=-74.0),
        *initial_nodes[1:],
    ]
    reappeared_nodes = [_node("shared-node", "Relay.One")]
    other_server_nodes = [_node("shared-node", "Relay.One")]
    clients = {
        SERVER_A_URL: _ScriptedClient(
            {
                "source-a": [
                    _snapshot("source-a", initial_nodes),
                    _snapshot("source-a", renamed_nodes),
                    _snapshot("source-a", renamed_nodes),
                ],
                "source-b": [
                    MeshMonitorConnectionError("synthetic source outage"),
                    _snapshot("source-b", reappeared_nodes),
                    _snapshot("source-b", reappeared_nodes),
                ],
            }
        ),
        SERVER_B_URL: _ScriptedClient(
            {"source-a": [_snapshot("source-a", other_server_nodes)]}
        ),
    }

    entity_registry = er.async_get(hass)
    entity_registry.async_get_or_create(
        "sensor",
        "foreign_integration",
        "foreign-unique-id",
        suggested_object_id="mm_foreign_collision_last_heard",
    )

    def client_factory(url: str, _token: str, **_kwargs: object) -> _ScriptedClient:
        return clients[url]

    with patch(
        "custom_components.meshmonitor.MeshMonitorClient",
        side_effect=client_factory,
    ):
        assert await hass.config_entries.async_setup(server_a.entry_id)
        await hass.async_block_till_done()
        assert server_a.state is ConfigEntryState.LOADED

        fingerprint_a = server_fingerprint(SERVER_A_URL)
        source_b_total_id = source_entity_unique_id(
            fingerprint_a, "source-b", "total_nodes"
        )
        before = _entry_entities(entity_registry, server_a)
        source_b_state = hass.states.get(before[source_b_total_id].entity_id)
        assert source_b_state is not None
        assert source_b_state.state == STATE_UNAVAILABLE

        shared_unique_id = node_entity_unique_id(
            fingerprint_a, "source-a", "shared-node", "last_heard"
        )
        shared_entity_id = before[shared_unique_id].entity_id
        assert shared_entity_id.startswith("sensor.mm_relay_one_last_heard_")
        assert not shared_entity_id.endswith("_2")

        foreign_unique_id = node_entity_unique_id(
            fingerprint_a, "source-a", "foreign-node", "last_heard"
        )
        assert before[foreign_unique_id].entity_id.startswith(
            "sensor.mm_foreign_collision_last_heard_"
        )
        missing_unique_id = node_entity_unique_id(
            fingerprint_a, "source-a", "!abcd1234", "last_heard"
        )
        assert before[missing_unique_id].entity_id == "sensor.mm_abcd1234_last_heard"

        runtime_before_reload = server_a.runtime_data
        assert await hass.config_entries.async_reload(server_a.entry_id)
        await hass.async_block_till_done()
        assert server_a.state is ConfigEntryState.LOADED
        assert server_a.runtime_data is not runtime_before_reload

        after_reappearance = _entry_entities(entity_registry, server_a)
        assert after_reappearance[shared_unique_id].entity_id == shared_entity_id
        source_b_state = hass.states.get(after_reappearance[source_b_total_id].entity_id)
        assert source_b_state is not None
        assert source_b_state.state != STATE_UNAVAILABLE
        source_b_node = node_entity_unique_id(
            fingerprint_a, "source-b", "shared-node", "last_heard"
        )
        assert source_b_node in after_reappearance
        assert len(set(after_reappearance)) == len(after_reappearance)

        entity_ids_before_restart = {
            unique_id: item.entity_id for unique_id, item in after_reappearance.items()
        }
        assert await hass.config_entries.async_unload(server_a.entry_id)
        await hass.async_block_till_done()
        assert server_a.state is ConfigEntryState.NOT_LOADED
        assert await hass.config_entries.async_setup(server_a.entry_id)
        await hass.async_block_till_done()
        assert server_a.state is ConfigEntryState.LOADED
        assert {
            unique_id: item.entity_id
            for unique_id, item in _entry_entities(entity_registry, server_a).items()
        } == entity_ids_before_restart

        assert server_b.state is ConfigEntryState.LOADED

    fingerprint_b = server_fingerprint(SERVER_B_URL)
    server_b_unique_id = node_entity_unique_id(
        fingerprint_b, "source-a", "shared-node", "last_heard"
    )
    server_b_entity = _entry_entities(entity_registry, server_b)[server_b_unique_id]
    assert server_b_entity.entity_id != shared_entity_id
    assert server_b_entity.entity_id.startswith("sensor.mm_relay_one_last_heard_")
    assert not server_b_entity.entity_id.endswith("_2")

    device_registry = dr.async_get(hass)
    for entry, fingerprint, source_ids in (
        (server_a, fingerprint_a, ("source-a", "source-b")),
        (server_b, fingerprint_b, ("source-a",)),
    ):
        for source_id in source_ids:
            source_device = device_registry.async_get_device(
                identifiers={source_device_identifier(fingerprint, source_id)}
            )
            assert source_device is not None
            node_device = device_registry.async_get_device(
                identifiers={
                    node_device_identifier(
                        fingerprint, source_id, "shared-node"
                    )
                }
            )
            assert node_device is not None
            assert node_device.via_device_id == source_device.id
            last_heard_id = node_entity_unique_id(
                fingerprint, source_id, "shared-node", "last_heard"
            )
            assert _entry_entities(entity_registry, entry)[last_heard_id].device_id == (
                node_device.id
            )

    assert await hass.config_entries.async_unload(server_a.entry_id)
    assert await hass.config_entries.async_unload(server_b.entry_id)
    await hass.async_block_till_done()
