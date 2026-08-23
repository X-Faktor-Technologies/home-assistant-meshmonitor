"""Source-aware visual-editor device action tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.components.device_automation import (
    DeviceAutomationType,
    async_get_device_automations,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_DEVICE_ID, CONF_DOMAIN, CONF_TOKEN, CONF_TYPE, CONF_URL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import selector
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.meshmonitor import MeshMonitorRuntimeData, MeshMonitorSourceRuntime
from custom_components.meshmonitor.actions import async_register_actions
from custom_components.meshmonitor.const import (
    CONF_ENABLE_NODE_MANAGEMENT,
    CONF_ENABLE_TRANSMIT,
    CONF_SOURCE_OPTIONS,
    DOMAIN,
)
from custom_components.meshmonitor.device_action import (
    ACTION_FAVORITE_NODE,
    ACTION_IGNORE_NODE,
    ACTION_REQUEST_NEIGHBORS,
    ACTION_REQUEST_NODEINFO,
    ACTION_REQUEST_POSITION,
    ACTION_REQUEST_TRACEROUTE,
    ACTION_SEND_DIRECT_TO_KNOWN_NODE,
    ACTION_SEND_TO_KNOWN_CHANNEL,
    ACTION_UNFAVORITE_NODE,
    ACTION_UNIGNORE_NODE,
    ATTR_CHANNEL,
    ATTR_DESTINATION_NODE_ID,
    async_call_action_from_config,
    async_get_action_capabilities,
    async_get_actions,
)
from custom_components.meshmonitor.registry import (
    node_device_identifier,
    server_fingerprint,
    source_device_identifier,
)
from custom_components.meshmonitor.vendor_meshmonitor_client import Node


def _runtime(
    hass: HomeAssistant,
) -> tuple[MeshMonitorSourceRuntime, str, MeshMonitorSourceRuntime, str, str]:
    meshtastic_nodes = {
        "!00000001": Node.from_dict({"id": "!00000001", "longName": "Local Meshtastic"}),
        "!1234abcd": Node.from_dict(
            {
                "id": "!1234abcd",
                "longName": "Remote Alpha",
                "shortName": "ALFA",
                "isFavorite": False,
            }
        ),
        "!abcdef12": Node.from_dict(
            {"id": "!abcdef12", "longName": "Remote Beta", "isFavorite": True}
        ),
    }
    meshcore_local = "1" * 64
    meshcore_remote = "2" * 64
    meshcore_nodes = {
        meshcore_local: Node.from_meshcore_dict(
            {"publicKey": meshcore_local, "name": "Local MeshCore"}
        ),
        meshcore_remote: Node.from_meshcore_dict(
            {"publicKey": meshcore_remote, "name": "Remote Core"}
        ),
    }
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_URL: "http://mesh.invalid", CONF_TOKEN: "token", "sources": []},
        options={
            CONF_SOURCE_OPTIONS: {
                "meshtastic-a": {CONF_ENABLE_TRANSMIT: True},
                "meshcore-a": {CONF_ENABLE_TRANSMIT: True},
            }
        },
    )
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    meshtastic = MeshMonitorSourceRuntime(
        entry,
        Mock(),
        Mock(
            nodes=meshtastic_nodes,
            data=SimpleNamespace(
                status=SimpleNamespace(local_node_id="!00000001"),
                channels=(
                    SimpleNamespace(index=0, display_name="Primary", name=None),
                    SimpleNamespace(index=2, display_name=None, name="Telemetry"),
                ),
            ),
        ),
        "meshtastic-a",
        "Meshtastic A",
        "meshtastic",
    )
    meshcore = MeshMonitorSourceRuntime(
        entry,
        Mock(),
        Mock(
            nodes=meshcore_nodes,
            data=SimpleNamespace(
                status=SimpleNamespace(local_node_id=meshcore_local),
                channels=(SimpleNamespace(index=1, display_name=None, name="Public"),),
            ),
        ),
        "meshcore-a",
        "MeshCore A",
        "meshcore",
    )
    fingerprint = server_fingerprint(entry.data[CONF_URL])
    entry.runtime_data = MeshMonitorRuntimeData(
        meshtastic.client,
        fingerprint,
        {meshtastic.source_id: meshtastic, meshcore.source_id: meshcore},
    )
    registry = dr.async_get(hass)
    meshtastic_device = registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={source_device_identifier(fingerprint, meshtastic.source_id)},
    )
    meshcore_device = registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={source_device_identifier(fingerprint, meshcore.source_id)},
    )
    remote_device = registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={node_device_identifier(fingerprint, meshtastic.source_id, "!abcdef12")},
    )
    return (
        meshtastic,
        meshtastic_device.id,
        meshcore,
        meshcore_device.id,
        remote_device.id,
    )


@pytest.mark.asyncio
async def test_only_source_devices_offer_dynamic_direct_action(
    hass: HomeAssistant,
) -> None:
    _, meshtastic_device_id, _, _, remote_device_id = _runtime(hass)
    actions = await async_get_actions(hass, meshtastic_device_id)
    assert actions[:2] == [
        {
            CONF_DEVICE_ID: meshtastic_device_id,
            CONF_DOMAIN: DOMAIN,
            CONF_TYPE: ACTION_SEND_DIRECT_TO_KNOWN_NODE,
        },
        {
            CONF_DEVICE_ID: meshtastic_device_id,
            CONF_DOMAIN: DOMAIN,
            CONF_TYPE: ACTION_SEND_TO_KNOWN_CHANNEL,
        },
    ]
    assert [action[CONF_TYPE] for action in actions[2:]] == [
        ACTION_REQUEST_TRACEROUTE,
        ACTION_REQUEST_POSITION,
        ACTION_REQUEST_NODEINFO,
        ACTION_REQUEST_NEIGHBORS,
    ]
    assert await async_get_actions(hass, remote_device_id) == []


@pytest.mark.asyncio
async def test_ha_device_automation_loader_discovers_source_action(
    hass: HomeAssistant,
) -> None:
    """Exercise the same device-action listing path used by the HA editor."""
    _, source_device_id, _, _, _ = _runtime(hass)

    actions = await async_get_device_automations(
        hass, DeviceAutomationType.ACTION, [source_device_id]
    )

    assert actions[source_device_id][:2] == [
        {
            CONF_DEVICE_ID: source_device_id,
            CONF_DOMAIN: DOMAIN,
            CONF_TYPE: ACTION_SEND_DIRECT_TO_KNOWN_NODE,
            "metadata": {},
        },
        {
            CONF_DEVICE_ID: source_device_id,
            CONF_DOMAIN: DOMAIN,
            CONF_TYPE: ACTION_SEND_TO_KNOWN_CHANNEL,
            "metadata": {},
        },
    ]
    assert [action[CONF_TYPE] for action in actions[source_device_id][2:]] == [
        ACTION_REQUEST_TRACEROUTE,
        ACTION_REQUEST_POSITION,
        ACTION_REQUEST_NODEINFO,
        ACTION_REQUEST_NEIGHBORS,
    ]


@pytest.mark.asyncio
async def test_capabilities_regenerate_from_each_exact_source(
    hass: HomeAssistant,
) -> None:
    _, meshtastic_device_id, _, meshcore_device_id, _ = _runtime(hass)

    meshtastic = await async_get_action_capabilities(
        hass,
        {
            CONF_DEVICE_ID: meshtastic_device_id,
            CONF_DOMAIN: DOMAIN,
            CONF_TYPE: ACTION_SEND_DIRECT_TO_KNOWN_NODE,
        },
    )
    meshcore = await async_get_action_capabilities(
        hass,
        {
            CONF_DEVICE_ID: meshcore_device_id,
            CONF_DOMAIN: DOMAIN,
            CONF_TYPE: ACTION_SEND_DIRECT_TO_KNOWN_NODE,
        },
    )

    meshtastic_fields = {
        marker.schema: validator for marker, validator in meshtastic["extra_fields"].schema.items()
    }
    meshcore_fields = {
        marker.schema: validator for marker, validator in meshcore["extra_fields"].schema.items()
    }
    destination = meshtastic_fields[ATTR_DESTINATION_NODE_ID]
    assert isinstance(destination, selector.SelectSelector)
    assert [option["value"] for option in destination.config["options"]] == [
        "!abcdef12",
        "!1234abcd",
    ]
    assert destination.config["options"][1]["label"] == ("Remote Alpha (ALFA · !1234abcd)")
    assert [
        option["value"] for option in meshcore_fields[ATTR_DESTINATION_NODE_ID].config["options"]
    ] == ["2" * 64]


@pytest.mark.asyncio
async def test_dynamic_action_uses_guarded_service_contract(
    hass: HomeAssistant,
) -> None:
    source, source_device_id, _, _, _ = _runtime(hass)
    source.client.send_meshtastic_message = AsyncMock(
        return_value=SimpleNamespace(message_id="message-3", delivery_state="accepted")
    )
    async_register_actions(hass)

    await async_call_action_from_config(
        hass,
        {
            CONF_DEVICE_ID: source_device_id,
            CONF_DOMAIN: DOMAIN,
            CONF_TYPE: ACTION_SEND_DIRECT_TO_KNOWN_NODE,
            ATTR_DESTINATION_NODE_ID: "!1234abcd",
            "text": "dynamic destination",
        },
        {},
        None,
    )

    source.client.send_meshtastic_message.assert_awaited_once_with(
        "meshtastic-a", "dynamic destination", to_node_id="!1234abcd"
    )


@pytest.mark.asyncio
async def test_meshtastic_request_action_uses_source_scoped_client(
    hass: HomeAssistant,
) -> None:
    source, source_device_id, _, _, _ = _runtime(hass)
    source.client.request_meshtastic_node_action = AsyncMock()

    capabilities = await async_get_action_capabilities(
        hass,
        {
            CONF_DEVICE_ID: source_device_id,
            CONF_DOMAIN: DOMAIN,
            CONF_TYPE: ACTION_REQUEST_POSITION,
        },
    )
    fields = {
        marker.schema: validator
        for marker, validator in capabilities["extra_fields"].schema.items()
    }
    assert list(fields) == [ATTR_DESTINATION_NODE_ID]

    await async_call_action_from_config(
        hass,
        {
            CONF_DEVICE_ID: source_device_id,
            CONF_DOMAIN: DOMAIN,
            CONF_TYPE: ACTION_REQUEST_POSITION,
            ATTR_DESTINATION_NODE_ID: "!1234abcd",
        },
        {},
        None,
    )

    source.client.request_meshtastic_node_action.assert_awaited_once_with(
        "meshtastic-a", "!1234abcd", "position"
    )


@pytest.mark.asyncio
async def test_meshcore_source_does_not_offer_meshtastic_requests(
    hass: HomeAssistant,
) -> None:
    _, _, _, meshcore_device_id, _ = _runtime(hass)

    actions = await async_get_actions(hass, meshcore_device_id)

    assert all(action[CONF_TYPE] not in {
        ACTION_REQUEST_TRACEROUTE,
        ACTION_REQUEST_POSITION,
        ACTION_REQUEST_NODEINFO,
        ACTION_REQUEST_NEIGHBORS,
    } for action in actions)


@pytest.mark.asyncio
async def test_explicit_node_management_gate_exposes_and_executes_server_only_actions(
    hass: HomeAssistant,
) -> None:
    source, source_device_id, _, _, _ = _runtime(hass)
    source.entry.options[CONF_SOURCE_OPTIONS][source.source_id][
        CONF_ENABLE_NODE_MANAGEMENT
    ] = True
    source.client.set_meshtastic_favorite = AsyncMock()
    source.client.set_meshtastic_ignored = AsyncMock()
    source.coordinator.async_request_refresh = AsyncMock()

    actions = await async_get_actions(hass, source_device_id)
    assert [action[CONF_TYPE] for action in actions[-4:]] == [
        ACTION_FAVORITE_NODE,
        ACTION_UNFAVORITE_NODE,
        ACTION_IGNORE_NODE,
        ACTION_UNIGNORE_NODE,
    ]

    await async_call_action_from_config(
        hass,
        {
            CONF_DEVICE_ID: source_device_id,
            CONF_DOMAIN: DOMAIN,
            CONF_TYPE: ACTION_IGNORE_NODE,
            ATTR_DESTINATION_NODE_ID: "!1234abcd",
        },
        {},
        None,
    )
    source.client.set_meshtastic_ignored.assert_awaited_once_with(
        "meshtastic-a", "!1234abcd", True
    )
    source.coordinator.async_request_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_channel_capabilities_and_action_use_exact_source_inventory(
    hass: HomeAssistant,
) -> None:
    source, source_device_id, _, _, _ = _runtime(hass)
    source.client.send_meshtastic_message = AsyncMock(
        return_value=SimpleNamespace(message_id="message-4", delivery_state="accepted")
    )
    async_register_actions(hass)
    capabilities = await async_get_action_capabilities(
        hass,
        {
            CONF_DEVICE_ID: source_device_id,
            CONF_DOMAIN: DOMAIN,
            CONF_TYPE: ACTION_SEND_TO_KNOWN_CHANNEL,
        },
    )
    fields = {
        marker.schema: validator
        for marker, validator in capabilities["extra_fields"].schema.items()
    }
    channel = fields[ATTR_CHANNEL]
    assert [option["value"] for option in channel.config["options"]] == ["0", "2"]
    assert channel.config["options"][0]["label"] == "Primary"

    await async_call_action_from_config(
        hass,
        {
            CONF_DEVICE_ID: source_device_id,
            CONF_DOMAIN: DOMAIN,
            CONF_TYPE: ACTION_SEND_TO_KNOWN_CHANNEL,
            ATTR_CHANNEL: 2,
            "text": "channel destination",
        },
        {},
        None,
    )
    source.client.send_meshtastic_message.assert_awaited_once_with(
        "meshtastic-a", "channel destination", channel=2
    )


@pytest.mark.asyncio
async def test_channel_action_rejects_stale_channel(hass: HomeAssistant) -> None:
    _, source_device_id, _, _, _ = _runtime(hass)
    with pytest.raises(ServiceValidationError, match="not current"):
        await async_call_action_from_config(
            hass,
            {
                CONF_DEVICE_ID: source_device_id,
                CONF_DOMAIN: DOMAIN,
                CONF_TYPE: ACTION_SEND_TO_KNOWN_CHANNEL,
                ATTR_CHANNEL: 7,
                "text": "stale channel",
            },
            {},
            None,
        )


@pytest.mark.asyncio
async def test_dynamic_action_rejects_destination_from_another_source(
    hass: HomeAssistant,
) -> None:
    _, source_device_id, _, _, _ = _runtime(hass)
    with pytest.raises(ServiceValidationError, match="not a current remote node"):
        await async_call_action_from_config(
            hass,
            {
                CONF_DEVICE_ID: source_device_id,
                CONF_DOMAIN: DOMAIN,
                CONF_TYPE: ACTION_SEND_DIRECT_TO_KNOWN_NODE,
                ATTR_DESTINATION_NODE_ID: "2" * 64,
                "text": "wrong source",
            },
            {},
            None,
        )
