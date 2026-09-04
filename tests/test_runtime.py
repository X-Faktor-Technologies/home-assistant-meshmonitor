"""Native Home Assistant tests for exact-server runtime ownership."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from homeassistant.const import CONF_TOKEN, CONF_URL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.meshmonitor import (
    MeshMonitorRuntimeData,
    MeshMonitorSourceRuntime,
    _async_create_and_migrate_source_devices,
    _async_reconcile_shared_runtime,
    async_setup_entry,
)
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
    NODE_DEVICE_POLICY_FAVORITES,
)
from custom_components.meshmonitor.coordinator import MeshMonitorCoordinator
from custom_components.meshmonitor.device_tracker import MeshMonitorNodeTracker
from custom_components.meshmonitor.device_tracker import (
    async_setup_entry as async_setup_trackers,
)
from custom_components.meshmonitor.entity import (
    async_add_node_entities,
    async_wait_node_entity_removals,
)
from custom_components.meshmonitor.registry import (
    node_device_identifier,
    server_device_identifier,
    server_fingerprint,
    source_device_identifier,
)
from custom_components.meshmonitor.sensor import async_setup_entry as async_setup_sensors
from custom_components.meshmonitor.vendor_meshmonitor_client import (
    Node,
    SourceSnapshot,
    SourceStatus,
)


def _entry(*, options: dict[str, object] | None = None) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="mesh.invalid",
        data={
            CONF_URL: "https://mesh.invalid",
            CONF_TOKEN: "synthetic-token",
            CONF_SOURCES: [
                {
                    CONF_SOURCE_ID: "source-a",
                    CONF_SOURCE_NAME: "Alpha",
                    CONF_SOURCE_TYPE: "meshtastic",
                },
                {
                    CONF_SOURCE_ID: "source-b",
                    CONF_SOURCE_NAME: "Bravo",
                    CONF_SOURCE_TYPE: "meshcore",
                },
            ],
        },
        options=options
        or {
            CONF_SERVER_OPTIONS: {"enable_sidebar_panel": False},
            CONF_SOURCE_OPTIONS: {
                "source-a": {"scan_interval": 75, "enable_message_polling": False},
                "source-b": {"scan_interval": 90, "enable_message_polling": False},
            },
        },
        version=2,
        unique_id=server_fingerprint("https://mesh.invalid"),
    )


async def test_dynamic_discovery_waits_for_matching_entity_removal(
    hass: HomeAssistant,
) -> None:
    """A rediscovered unique ID is added only after its old platform object exits."""
    gate = asyncio.Event()

    async def remove_old_entity() -> None:
        await gate.wait()

    removal = hass.async_create_task(remove_old_entity(), "Remove old node entity")
    hass.data.setdefault(DOMAIN, {})["node_entity_removals"] = {"node-entity": removal}
    entity = SimpleNamespace(unique_id="node-entity")
    added: list[object] = []

    async_add_node_entities(
        hass,
        lambda entities: added.extend(entities),  # type: ignore[arg-type]
        [entity],  # type: ignore[list-item]
    )
    assert added == []

    gate.set()
    await hass.async_block_till_done()
    assert added == [entity]


async def test_dynamic_discovery_drops_entity_that_becomes_ineligible_while_waiting(
    hass: HomeAssistant,
) -> None:
    """A stale queued rediscovery cannot resurrect an ineligible entity."""
    gate = asyncio.Event()

    async def remove_old_entity() -> None:
        await gate.wait()

    removal = hass.async_create_task(remove_old_entity(), "Remove old node entity")
    hass.data.setdefault(DOMAIN, {})["node_entity_removals"] = {"node-entity": removal}
    entity = SimpleNamespace(unique_id="node-entity")
    state = SimpleNamespace(eligible=True)
    added: list[object] = []
    stale: list[object] = []

    async_add_node_entities(
        hass,
        lambda entities: added.extend(entities),  # type: ignore[arg-type]
        [entity],  # type: ignore[list-item]
        is_current=lambda _: state.eligible,
        on_stale=stale.append,
    )
    state.eligible = False
    gate.set()
    await hass.async_block_till_done()

    assert added == []
    assert stale == [entity]


async def test_removal_waits_use_exact_source_and_node_identity(
    hass: HomeAssistant,
) -> None:
    """Delimiter-bearing source IDs cannot collide in retirement waits."""
    target_gate = asyncio.Event()
    other_gate = asyncio.Event()

    async def wait_for(gate: asyncio.Event) -> None:
        await gate.wait()

    target = hass.async_create_task(wait_for(target_gate), "Remove target node entity")
    other = hass.async_create_task(wait_for(other_gate), "Remove other node entity")
    domain_data = hass.data.setdefault(DOMAIN, {})
    domain_data["node_entity_removals"] = {"target": target, "other": other}
    domain_data["node_entity_removal_identities"] = {
        "target": ("fingerprint", "source-a", "child"),
        "other": ("fingerprint", "source-a:child", "node"),
    }

    waiter = hass.async_create_task(
        async_wait_node_entity_removals(
            hass, "fingerprint", "source-a", "child"
        ),
        "Wait for target removal",
    )
    target_gate.set()
    await waiter

    assert not other.done()
    other_gate.set()
    await other


async def test_confirmed_favorite_write_updates_coordinator_memory(
    hass: HomeAssistant,
) -> None:
    """A confirmed write bypasses a temporarily stale follow-up API snapshot."""
    node = Node.from_dict({"id": "node-1", "isFavorite": False})
    snapshot = SourceSnapshot.create(
        "source-a",
        SourceStatus.from_dict({"connected": True, "localNodeId": "local"}),
        [node],
        None,
        [],
        {},
    )
    coordinator = MeshMonitorCoordinator(
        hass, Mock(), "source-a", "meshcore"
    )
    coordinator.async_set_updated_data(snapshot)
    listener = Mock()
    coordinator.async_add_listener(listener)

    coordinator.async_set_node_favorite("node-1", True)

    assert coordinator.nodes["node-1"].is_favorite is True
    assert coordinator.nodes["node-1"].raw["isFavorite"] is True
    listener.assert_called_once_with()


async def test_setup_serializes_sources_keeps_failed_sibling_and_creates_sources(
    hass: HomeAssistant,
) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    order: list[str] = []

    def coordinator(source_id: str, *, succeeds: bool) -> Mock:
        async def first_refresh() -> None:
            order.append(source_id)
            if not succeeds:
                raise ConfigEntryNotReady("synthetic unavailable source")

        return Mock(
            source_id=source_id,
            data=None,
            last_update_success=succeeds,
            async_config_entry_first_refresh=AsyncMock(side_effect=first_refresh),
            async_add_listener=Mock(return_value=Mock()),
        )

    first = coordinator("source-a", succeeds=False)
    second = coordinator("source-b", succeeds=True)
    client = Mock()
    factory = Mock(side_effect=[first, second])

    with (
        patch("custom_components.meshmonitor.MeshMonitorClient", return_value=client),
        patch("custom_components.meshmonitor.MeshMonitorCoordinator", factory),
        patch(
            "custom_components.meshmonitor.async_register_websocket_commands"
        ),
        patch(
            "custom_components.meshmonitor._async_reconcile_shared_runtime",
            new=AsyncMock(),
        ),
        patch.object(
            hass.config_entries,
            "async_forward_entry_setups",
            new=AsyncMock(),
        ) as forward,
    ):
        assert await async_setup_entry(hass, entry) is True

    assert order == ["source-a", "source-b"]
    assert list(entry.runtime_data.sources) == ["source-a", "source-b"]
    assert entry.runtime_data.client is client
    assert factory.call_args_list[0].args[2:4] == ("source-a", "meshtastic")
    assert factory.call_args_list[1].args[2:4] == ("source-b", "meshcore")
    assert factory.call_args_list[0].args[4].total_seconds() == 75
    assert factory.call_args_list[1].args[4].total_seconds() == 90
    forward.assert_awaited_once_with(entry, ["sensor", "device_tracker"])

    fingerprint = server_fingerprint("https://mesh.invalid")
    registry = dr.async_get(hass)
    for source_id in ("source-a", "source-b"):
        source = registry.async_get_device(
            identifiers={source_device_identifier(fingerprint, source_id)}
        )
        assert source is not None
        assert source.via_device_id is None


async def test_setup_does_not_attach_node_monitor_to_reticulum(
    hass: HomeAssistant,
) -> None:
    entry = _entry()
    entry.data[CONF_SOURCES].append(
        {
            CONF_SOURCE_ID: "source-rns",
            CONF_SOURCE_NAME: "RNS",
            CONF_SOURCE_TYPE: "reticulum",
        }
    )
    entry.add_to_hass(hass)
    coordinators = [
        Mock(
            source_id=source_id,
            data=None,
            last_update_success=True,
            async_config_entry_first_refresh=AsyncMock(),
            async_add_listener=Mock(return_value=Mock()),
        )
        for source_id in ("source-a", "source-b", "source-rns")
    ]

    with (
        patch("custom_components.meshmonitor.MeshMonitorClient", return_value=Mock()),
        patch("custom_components.meshmonitor.MeshMonitorCoordinator", side_effect=coordinators),
        patch("custom_components.meshmonitor.MeshMonitorNodeEventMonitor") as monitor,
        patch("custom_components.meshmonitor.async_register_websocket_commands"),
        patch(
            "custom_components.meshmonitor._async_reconcile_shared_runtime",
            new=AsyncMock(),
        ),
        patch.object(
            hass.config_entries,
            "async_forward_entry_setups",
            new=AsyncMock(),
        ),
    ):
        assert await async_setup_entry(hass, entry) is True

    assert [call.args[3] for call in monitor.call_args_list] == [
        "meshtastic",
        "meshcore",
    ]


async def test_device_model_migration_preserves_local_entity_registry_identity(
    hass: HomeAssistant,
) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    fingerprint = server_fingerprint(entry.data[CONF_URL])
    devices = dr.async_get(hass)
    entities = er.async_get(hass)
    server_identifier = server_device_identifier(fingerprint)
    server = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={server_identifier},
        entry_type=dr.DeviceEntryType.SERVICE,
    )
    source_identifier = source_device_identifier(fingerprint, "source-a")
    source_device = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={source_identifier},
        via_device=server_identifier,
    )
    local_identifier = node_device_identifier(fingerprint, "source-a", "!000004d2")
    old_local_device = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={local_identifier},
        via_device=source_identifier,
    )
    entity = entities.async_get_or_create(
        "sensor",
        DOMAIN,
        f"node:{fingerprint}:source-a:!000004d2:last_heard",
        config_entry=entry,
        device_id=old_local_device.id,
        suggested_object_id="mm_alpha_last_heard",
    )
    node = Node.from_dict({"id": "!000004d2", "longName": "Alpha"})
    snapshot = SourceSnapshot.create(
        "source-a",
        SourceStatus.from_dict({"connected": True, "localNodeId": "1234"}),
        [node],
        None,
        [],
        {},
    )
    client = Mock()
    source = MeshMonitorSourceRuntime(
        entry,
        client,
        Mock(data=snapshot, nodes={node.id: node}),
        "source-a",
        "Alpha",
        "meshtastic",
    )
    entry.runtime_data = MeshMonitorRuntimeData(
        client, fingerprint, {source.source_id: source}
    )

    _async_create_and_migrate_source_devices(hass, entry)

    assert devices.async_get(server.id) is None
    assert devices.async_get(old_local_device.id) is None
    migrated_source = devices.async_get(source_device.id)
    assert migrated_source is not None
    assert migrated_source.via_device_id is None
    migrated_entity = entities.async_get(entity.entity_id)
    assert migrated_entity is not None
    assert migrated_entity.unique_id == entity.unique_id
    assert migrated_entity.device_id == source_device.id


async def test_setup_rejects_legacy_shape_before_creating_client(
    hass: HomeAssistant,
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_URL: "https://mesh.invalid",
            CONF_TOKEN: "synthetic-token",
            CONF_SOURCE_ID: "legacy-source",
        },
    )
    entry.add_to_hass(hass)

    with (
        patch("custom_components.meshmonitor.MeshMonitorClient") as client,
        patch.object(
            hass.config_entries,
            "async_forward_entry_setups",
            new=AsyncMock(),
        ),
    ):
        try:
            await async_setup_entry(hass, entry)
        except ConfigEntryError as error:
            assert "Legacy source-shaped" in str(error)
        else:
            raise AssertionError("legacy entry unexpectedly loaded")
    client.assert_not_called()


async def test_sensor_platform_batches_sources_and_attaches_nodes_to_exact_source(
    hass: HomeAssistant,
) -> None:
    entry = _entry(
        options={
            CONF_SERVER_OPTIONS: {CONF_NODE_DEVICE_POLICY: NODE_DEVICE_POLICY_ALL},
            CONF_SOURCE_OPTIONS: {},
        }
    )
    entry.add_to_hass(hass)
    client = Mock()
    sources = {}
    for source_id, source_name, source_type in (
        ("source-a", "Alpha", "meshtastic"),
        ("source-b", "Bravo", "meshcore"),
    ):
        node = Node.from_dict(
            {
                "id": "node-1",
                "longName": "Shared label",
                "lastHeard": "2026-08-17T12:00:00Z",
            }
        )
        snapshot = SourceSnapshot.create(
            source_id,
            SourceStatus.from_dict({"connected": True, "localNodeId": "node-1"}),
            [node],
            None,
            [],
            {},
        )
        coordinator = Mock(
            data=snapshot,
            nodes={node.id: node},
            last_update_success=True,
            async_add_listener=Mock(return_value=Mock()),
        )
        sources[source_id] = MeshMonitorSourceRuntime(
            entry, client, coordinator, source_id, source_name, source_type
        )
    fingerprint = server_fingerprint(entry.data[CONF_URL])
    entry.runtime_data = MeshMonitorRuntimeData(client, fingerprint, sources)
    added = []

    def add_entities(entities: object) -> None:
        added.extend(entities)  # type: ignore[arg-type]

    await async_setup_sensors(hass, entry, add_entities)  # type: ignore[arg-type]

    last_heard = [
        entity
        for entity in added
        if getattr(getattr(entity, "entity_description", None), "key", None)
        == "last_heard"
    ]
    assert len(last_heard) == 2
    assert len({entity.entity_id for entity in last_heard}) == 2
    assert all(
        entity.entity_id.startswith("sensor.mm_shared_label_last_heard_")
        for entity in last_heard
    )
    assert all(not entity.entity_id.endswith("_2") for entity in last_heard)
    assert {
        next(iter(entity.device_info["identifiers"])) for entity in last_heard
    } == {
        source_device_identifier(fingerprint, "source-a"),
        source_device_identifier(fingerprint, "source-b"),
    }
    assert all("via_device" not in entity.device_info for entity in last_heard)


async def test_sensor_discovery_readds_node_after_favorite_policy_removal(
    hass: HomeAssistant,
) -> None:
    """An ineligible interval must not permanently suppress rediscovery."""
    entry = _entry(
        options={
            CONF_SERVER_OPTIONS: {
                CONF_NODE_DEVICE_POLICY: NODE_DEVICE_POLICY_FAVORITES
            },
            CONF_SOURCE_OPTIONS: {},
        }
    )
    entry.add_to_hass(hass)
    favorite = Node.from_dict(
        {
            "id": "node-1",
            "longName": "Mobile node",
            "lastHeard": "2026-08-17T12:00:00Z",
            "isFavorite": True,
        }
    )
    coordinator = Mock(
        data=SimpleNamespace(status=SimpleNamespace(local_node_id="local")),
        nodes={favorite.id: favorite},
        last_update_success=True,
        async_add_listener=Mock(return_value=Mock()),
    )
    source = MeshMonitorSourceRuntime(
        entry, Mock(), coordinator, "source-a", "Alpha", "meshtastic"
    )
    entry.runtime_data = MeshMonitorRuntimeData(
        source.client,
        server_fingerprint(entry.data[CONF_URL]),
        {source.source_id: source},
    )
    added = []

    def add_entities(entities: object) -> None:
        added.extend(entities)  # type: ignore[arg-type]

    await async_setup_sensors(hass, entry, add_entities)  # type: ignore[arg-type]
    listener = coordinator.async_add_listener.call_args.args[0]
    initial_count = len(added)
    assert sum(getattr(entity, "node_id", None) == favorite.id for entity in added) == 1

    coordinator.nodes = {
        favorite.id: Node.from_dict(
            {
                "id": favorite.id,
                "longName": "Mobile node",
                "lastHeard": "2026-08-17T12:00:00Z",
                "isFavorite": False,
            }
        )
    }
    listener()
    assert len(added) == initial_count

    coordinator.nodes = {favorite.id: favorite}
    listener()
    assert len(added) == initial_count + 1
    assert sum(getattr(entity, "node_id", None) == favorite.id for entity in added) == 2


async def test_sensor_discovery_keeps_existing_sensor_during_value_loss(
    hass: HomeAssistant,
) -> None:
    """A transient missing value does not rediscover an active node sensor."""
    entry = _entry(
        options={
            CONF_SERVER_OPTIONS: {CONF_NODE_DEVICE_POLICY: NODE_DEVICE_POLICY_ALL},
            CONF_SOURCE_OPTIONS: {},
        }
    )
    entry.add_to_hass(hass)
    reported = Node.from_dict(
        {"id": "node-1", "longName": "Mobile node", "batteryLevel": 50}
    )
    missing = Node.from_dict({"id": reported.id, "longName": "Mobile node"})
    coordinator = Mock(
        data=SimpleNamespace(status=SimpleNamespace(local_node_id="local")),
        nodes={reported.id: reported},
        last_update_success=True,
        async_add_listener=Mock(return_value=Mock()),
    )
    source = MeshMonitorSourceRuntime(
        entry, Mock(), coordinator, "source-a", "Alpha", "meshtastic"
    )
    entry.runtime_data = MeshMonitorRuntimeData(
        source.client,
        server_fingerprint(entry.data[CONF_URL]),
        {source.source_id: source},
    )
    added: list[object] = []

    await async_setup_sensors(
        hass,
        entry,
        lambda entities: added.extend(entities),  # type: ignore[arg-type]
    )
    listener = coordinator.async_add_listener.call_args.args[0]
    assert sum(
        getattr(getattr(entity, "entity_description", None), "key", None) == "battery"
        for entity in added
    ) == 1

    coordinator.nodes = {missing.id: missing}
    listener()
    coordinator.nodes = {
        reported.id: Node.from_dict(
            {"id": reported.id, "longName": "Mobile node", "batteryLevel": 51}
        )
    }
    listener()

    assert sum(
        getattr(getattr(entity, "entity_description", None), "key", None) == "battery"
        for entity in added
    ) == 1


async def test_tracker_discovery_keeps_existing_tracker_during_coordinate_loss(
    hass: HomeAssistant,
) -> None:
    """A coordinate gap does not rediscover an active node tracker."""
    entry = _entry(
        options={
            CONF_SERVER_OPTIONS: {CONF_NODE_DEVICE_POLICY: NODE_DEVICE_POLICY_ALL},
            CONF_SOURCE_OPTIONS: {},
        }
    )
    entry.add_to_hass(hass)
    positioned = Node.from_dict(
        {
            "id": "node-1",
            "longName": "Mobile node",
            "latitude": 40.0,
            "longitude": -74.0,
        }
    )
    unpositioned = Node.from_dict(
        {"id": positioned.id, "longName": "Mobile node"}
    )
    coordinator = Mock(
        data=SimpleNamespace(status=SimpleNamespace(local_node_id="local")),
        nodes={unpositioned.id: unpositioned},
        last_update_success=True,
        async_add_listener=Mock(return_value=Mock()),
    )
    source = MeshMonitorSourceRuntime(
        entry, Mock(), coordinator, "source-a", "Alpha", "meshtastic"
    )
    entry.runtime_data = MeshMonitorRuntimeData(
        source.client,
        server_fingerprint(entry.data[CONF_URL]),
        {source.source_id: source},
    )
    added: list[object] = []

    def add_entities(entities: object) -> None:
        added.extend(entities)  # type: ignore[arg-type]

    await async_setup_trackers(hass, entry, add_entities)  # type: ignore[arg-type]
    listener = coordinator.async_add_listener.call_args.args[0]
    assert added == []

    coordinator.nodes = {positioned.id: positioned}
    listener()
    assert len(added) == 1

    coordinator.nodes = {unpositioned.id: unpositioned}
    listener()
    coordinator.nodes = {positioned.id: positioned}
    listener()

    assert len(added) == 1


async def test_tracker_rediscovery_waits_for_authoritative_removal(
    hass: HomeAssistant,
) -> None:
    """A retired tracker exits before the same tracker identity is rediscovered."""
    entry = _entry(
        options={
            CONF_SERVER_OPTIONS: {
                CONF_NODE_DEVICE_POLICY: NODE_DEVICE_POLICY_FAVORITES
            },
            CONF_SOURCE_OPTIONS: {},
        }
    )
    entry.add_to_hass(hass)
    favorite = Node.from_dict(
        {
            "id": "node-1",
            "longName": "Mobile node",
            "latitude": 40.0,
            "longitude": -74.0,
            "isFavorite": True,
        }
    )
    ineligible = Node.from_dict(
        {
            "id": favorite.id,
            "longName": "Mobile node",
            "latitude": 40.0,
            "longitude": -74.0,
            "isFavorite": False,
        }
    )
    coordinator = Mock(
        data=SimpleNamespace(status=SimpleNamespace(local_node_id="local")),
        nodes={favorite.id: favorite},
        last_update_success=True,
        async_add_listener=Mock(return_value=Mock()),
    )
    source = MeshMonitorSourceRuntime(
        entry, Mock(), coordinator, "source-a", "Alpha", "meshtastic"
    )
    entry.runtime_data = MeshMonitorRuntimeData(
        source.client,
        server_fingerprint(entry.data[CONF_URL]),
        {source.source_id: source},
    )
    added: list[MeshMonitorNodeTracker] = []

    def add_entities(entities: object) -> None:
        added.extend(entities)  # type: ignore[arg-type]

    await async_setup_trackers(hass, entry, add_entities)  # type: ignore[arg-type]
    tracker = added[0]
    tracker.hass = hass
    listener = coordinator.async_add_listener.call_args.args[0]
    removal_gate = asyncio.Event()

    async def remove_tracker(**_: object) -> None:
        await removal_gate.wait()

    coordinator.nodes = {ineligible.id: ineligible}
    with patch.object(tracker, "async_remove", AsyncMock(side_effect=remove_tracker)):
        tracker._handle_coordinator_update()
        assert tracker.async_remove.await_count == 1

        listener()
        coordinator.nodes = {favorite.id: favorite}
        listener()
        assert len(added) == 1

        removal_gate.set()
        await hass.async_block_till_done()

    assert len(added) == 2
    assert added[1].unique_id == tracker.unique_id


async def test_shared_message_runtime_uses_server_interval_and_enabled_sources(
    hass: HomeAssistant,
) -> None:
    entry = _entry(
        options={
            CONF_SERVER_OPTIONS: {
                "enable_sidebar_panel": False,
                "message_scan_interval": 45,
            },
            CONF_SOURCE_OPTIONS: {
                "source-a": {"enable_message_polling": True},
                "source-b": {"enable_message_polling": False},
            },
        }
    )
    entry.add_to_hass(hass)
    client = Mock()
    sources = {
        source_id: MeshMonitorSourceRuntime(
            entry,
            client,
            Mock(),
            source_id,
            source_id.title(),
            source_type,
        )
        for source_id, source_type in (
            ("source-a", "meshtastic"),
            ("source-b", "meshcore"),
        )
    }
    entry.runtime_data = MeshMonitorRuntimeData(
        client,
        server_fingerprint(entry.data[CONF_URL]),
        sources,
    )
    unsubscribe = Mock()
    coordinator = Mock(async_initialize=AsyncMock(return_value=unsubscribe))
    factory = Mock(return_value=coordinator)

    with (
        patch("custom_components.meshmonitor._active_entries", return_value=[entry]),
        patch("custom_components.meshmonitor.MeshMonitorMessageCoordinator", factory),
    ):
        await _async_reconcile_shared_runtime(hass)

    args = factory.call_args.args
    assert args[0] is hass
    assert [source.source_id for source in args[1]] == ["source-a"]
    assert args[2] == "https://mesh.invalid"
    assert args[3].total_seconds() == 45
    assert list(hass.data[DOMAIN]["message_coordinators"]) == [entry.entry_id]
