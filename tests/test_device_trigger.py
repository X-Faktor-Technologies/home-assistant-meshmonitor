"""UI-discoverable message device trigger tests."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    CONF_DEVICE_ID,
    CONF_DOMAIN,
    CONF_FOR,
    CONF_PLATFORM,
    CONF_TYPE,
    CONF_URL,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.meshmonitor import MeshMonitorRuntimeData, MeshMonitorSourceRuntime
from custom_components.meshmonitor.const import (
    DOMAIN,
    EVENT_AUTOMATION_EXECUTED,
    EVENT_MESSAGE_RECEIVED,
    EVENT_NODE_DISCOVERED,
    EVENT_NODE_UPDATED,
    EVENT_POSITION_UPDATED,
    EVENT_SOURCE_CONNECTION_CHANGED,
    EVENT_TELEMETRY_RECEIVED,
)
from custom_components.meshmonitor.device_trigger import (
    ATTR_CHANNEL,
    ATTR_METRIC,
    ATTR_NODE,
    ATTR_SENDER,
    ATTR_TEXT_REQUIRED,
    TRIGGER_ANY_MESSAGE,
    TRIGGER_AUTOMATION_COMPLETED,
    TRIGGER_AUTOMATION_FAILED,
    TRIGGER_CHANNEL_MESSAGE,
    TRIGGER_DIRECT_MESSAGE,
    TRIGGER_NODE_DISCOVERED,
    TRIGGER_NODE_UPDATED,
    TRIGGER_POSITION_UPDATED,
    TRIGGER_SOURCE_CONNECTED,
    TRIGGER_SOURCE_DISCONNECTED,
    TRIGGER_TELEMETRY_RECEIVED,
    async_attach_trigger,
    async_get_trigger_capabilities,
    async_get_triggers,
)
from custom_components.meshmonitor.registry import (
    node_device_identifier,
    server_fingerprint,
    source_device_identifier,
)


def _devices(hass: HomeAssistant) -> tuple[str, str]:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_URL: "http://mesh.invalid", "sources": []},
    )
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    fingerprint = server_fingerprint(entry.data[CONF_URL])
    source = MeshMonitorSourceRuntime(
        entry,
        Mock(),
        Mock(
            nodes={
                "!1234abcd": Mock(
                    id="!1234abcd", long_name="Remote Alpha", short_name="ALFA"
                )
            },
            data=Mock(
                channels=(Mock(index=0, display_name="Primary", name=None),),
                telemetry=(Mock(telemetry_type="battery"),),
            ),
        ),
        "source-a",
        "Source A",
        "meshtastic",
    )
    entry.runtime_data = MeshMonitorRuntimeData(
        source.client, fingerprint, {source.source_id: source}
    )
    registry = dr.async_get(hass)
    source_device = registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={source_device_identifier(fingerprint, source.source_id)},
    )
    node_device = registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={node_device_identifier(fingerprint, source.source_id, "!1234abcd")},
    )
    return source_device.id, node_device.id


@pytest.mark.asyncio
async def test_only_source_devices_offer_received_message_triggers(
    hass: HomeAssistant,
) -> None:
    source_device_id, node_device_id = _devices(hass)
    triggers = await async_get_triggers(hass, source_device_id)
    assert [trigger[CONF_TYPE] for trigger in triggers] == [
        TRIGGER_ANY_MESSAGE,
        TRIGGER_DIRECT_MESSAGE,
        TRIGGER_CHANNEL_MESSAGE,
        TRIGGER_SOURCE_CONNECTED,
        TRIGGER_SOURCE_DISCONNECTED,
        TRIGGER_AUTOMATION_COMPLETED,
        TRIGGER_AUTOMATION_FAILED,
        TRIGGER_NODE_DISCOVERED,
        TRIGGER_NODE_UPDATED,
        TRIGGER_TELEMETRY_RECEIVED,
        TRIGGER_POSITION_UPDATED,
    ]
    assert all(trigger[CONF_DEVICE_ID] == source_device_id for trigger in triggers)
    assert await async_get_triggers(hass, node_device_id) == []


@pytest.mark.asyncio
async def test_direct_trigger_filters_source_and_message_kind(hass: HomeAssistant) -> None:
    source_device_id, _ = _devices(hass)
    action = AsyncMock()
    remove = await async_attach_trigger(
        hass,
        {
            CONF_PLATFORM: "device",
            CONF_DOMAIN: DOMAIN,
            CONF_DEVICE_ID: source_device_id,
            CONF_TYPE: TRIGGER_DIRECT_MESSAGE,
        },
        action,
        {"trigger_data": {}, "variables": {}},
    )
    hass.bus.async_fire(
        EVENT_MESSAGE_RECEIVED,
        {"source_ids": ["other"], "is_direct": True, "text": "wrong source"},
    )
    hass.bus.async_fire(
        EVENT_MESSAGE_RECEIVED,
        {"source_ids": ["source-a"], "is_direct": False, "text": "channel"},
    )
    hass.bus.async_fire(
        EVENT_MESSAGE_RECEIVED,
        {"source_ids": ["source-a"], "is_direct": True, "text": "announce me"},
    )
    await hass.async_block_till_done()
    action.assert_awaited_once()
    variables = action.await_args.args[0]
    assert variables["trigger"]["event"].data["text"] == "announce me"
    remove()


@pytest.mark.asyncio
async def test_message_trigger_optional_filters(hass: HomeAssistant) -> None:
    source_device_id, _ = _devices(hass)
    action = AsyncMock()
    remove = await async_attach_trigger(
        hass,
        {
            CONF_PLATFORM: "device",
            CONF_DOMAIN: DOMAIN,
            CONF_DEVICE_ID: source_device_id,
            CONF_TYPE: TRIGGER_CHANNEL_MESSAGE,
            ATTR_SENDER: "Remote Alpha",
            ATTR_CHANNEL: 0,
            ATTR_TEXT_REQUIRED: True,
        },
        action,
        {"trigger_data": {}, "variables": {}},
    )
    hass.bus.async_fire(
        EVENT_MESSAGE_RECEIVED,
        {
            "source_ids": ["source-a"],
            "is_direct": False,
            "sender_name": "Remote Alpha",
            "channel": 0,
        },
    )
    hass.bus.async_fire(
        EVENT_MESSAGE_RECEIVED,
        {
            "source_ids": ["source-a"],
            "is_direct": False,
            "sender_name": "Remote Alpha",
            "channel": 0,
            "text": "speak this",
        },
    )
    await hass.async_block_till_done()
    action.assert_awaited_once()
    remove()


@pytest.mark.asyncio
async def test_message_trigger_capabilities_are_source_aware(
    hass: HomeAssistant,
) -> None:
    source_device_id, _ = _devices(hass)
    result = await async_get_trigger_capabilities(
        hass,
        {
            CONF_PLATFORM: "device",
            CONF_DOMAIN: DOMAIN,
            CONF_DEVICE_ID: source_device_id,
            CONF_TYPE: TRIGGER_CHANNEL_MESSAGE,
        },
    )
    fields = {
        marker.schema: validator
        for marker, validator in result["extra_fields"].schema.items()
    }
    assert fields[ATTR_SENDER].config["options"][0]["value"] == "!1234abcd"
    assert fields[ATTR_CHANNEL].config["options"] == [
        {"value": "0", "label": "Primary"}
    ]
    assert ATTR_TEXT_REQUIRED in fields


@pytest.mark.asyncio
async def test_node_trigger_filters_and_telemetry_capabilities(
    hass: HomeAssistant,
) -> None:
    source_device_id, _ = _devices(hass)
    config = {
        CONF_PLATFORM: "device",
        CONF_DOMAIN: DOMAIN,
        CONF_DEVICE_ID: source_device_id,
        CONF_TYPE: TRIGGER_TELEMETRY_RECEIVED,
        ATTR_NODE: "!1234abcd",
        ATTR_METRIC: "battery",
    }
    capabilities = await async_get_trigger_capabilities(hass, config)
    fields = {
        marker.schema: validator
        for marker, validator in capabilities["extra_fields"].schema.items()
    }
    assert fields[ATTR_NODE].config["options"][0]["value"] == "!1234abcd"
    assert fields[ATTR_METRIC].config["options"] == ["battery"]

    action = AsyncMock()
    remove = await async_attach_trigger(
        hass, config, action, {"trigger_data": {}, "variables": {}}
    )
    hass.bus.async_fire(
        EVENT_TELEMETRY_RECEIVED,
        {"source_id": "source-a", "node_id": "!1234abcd", "metric": "voltage"},
    )
    hass.bus.async_fire(
        EVENT_TELEMETRY_RECEIVED,
        {"source_id": "source-a", "node_id": "!1234abcd", "metric": "battery"},
    )
    await hass.async_block_till_done()
    action.assert_awaited_once()
    remove()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("trigger_type", "event_type", "event_data"),
    [
        (
            TRIGGER_SOURCE_CONNECTED,
            EVENT_SOURCE_CONNECTION_CHANGED,
            {"source_id": "source-a", "connected": True},
        ),
        (
            TRIGGER_SOURCE_DISCONNECTED,
            EVENT_SOURCE_CONNECTION_CHANGED,
            {"source_id": "source-a", "connected": False},
        ),
        (
            TRIGGER_AUTOMATION_COMPLETED,
            EVENT_AUTOMATION_EXECUTED,
            {"source_id": "source-a", "status": "completed"},
        ),
        (
            TRIGGER_AUTOMATION_FAILED,
            EVENT_AUTOMATION_EXECUTED,
            {"source_id": "source-a", "status": "failed"},
        ),
        (
            TRIGGER_NODE_DISCOVERED,
            EVENT_NODE_DISCOVERED,
            {"source_id": "source-a", "node_id": "!1234abcd"},
        ),
        (
            TRIGGER_NODE_UPDATED,
            EVENT_NODE_UPDATED,
            {"source_id": "source-a", "node_id": "!1234abcd"},
        ),
        (
            TRIGGER_TELEMETRY_RECEIVED,
            EVENT_TELEMETRY_RECEIVED,
            {"source_id": "source-a", "node_id": "!1234abcd", "metric": "battery"},
        ),
        (
            TRIGGER_POSITION_UPDATED,
            EVENT_POSITION_UPDATED,
            {"source_id": "source-a", "node_id": "!1234abcd"},
        ),
    ],
)
async def test_source_and_automation_triggers(
    hass: HomeAssistant,
    trigger_type: str,
    event_type: str,
    event_data: dict[str, object],
) -> None:
    source_device_id, _ = _devices(hass)
    action = AsyncMock()
    remove = await async_attach_trigger(
        hass,
        {
            CONF_PLATFORM: "device",
            CONF_DOMAIN: DOMAIN,
            CONF_DEVICE_ID: source_device_id,
            CONF_TYPE: trigger_type,
        },
        action,
        {"trigger_data": {}, "variables": {}},
    )
    hass.bus.async_fire(event_type, {**event_data, "source_id": "other"})
    hass.bus.async_fire(event_type, event_data)
    await hass.async_block_till_done()
    action.assert_awaited_once()
    remove()


@pytest.mark.asyncio
async def test_source_duration_waits_and_opposite_transition_cancels(
    hass: HomeAssistant,
) -> None:
    source_device_id, _ = _devices(hass)
    action = AsyncMock()
    remove = await async_attach_trigger(
        hass,
        {
            CONF_PLATFORM: "device",
            CONF_DOMAIN: DOMAIN,
            CONF_DEVICE_ID: source_device_id,
            CONF_TYPE: TRIGGER_SOURCE_DISCONNECTED,
            CONF_FOR: {"minutes": 2},
        },
        action,
        {"trigger_data": {}, "variables": {}},
    )
    now = dt_util.utcnow()
    hass.bus.async_fire(
        EVENT_SOURCE_CONNECTION_CHANGED,
        {"source_id": "source-a", "connected": False},
    )
    await hass.async_block_till_done()
    async_fire_time_changed(hass, now + timedelta(seconds=119))
    await hass.async_block_till_done()
    action.assert_not_awaited()

    hass.bus.async_fire(
        EVENT_SOURCE_CONNECTION_CHANGED,
        {"source_id": "source-a", "connected": True},
    )
    async_fire_time_changed(hass, now + timedelta(minutes=3))
    await hass.async_block_till_done()
    action.assert_not_awaited()

    hass.bus.async_fire(
        EVENT_SOURCE_CONNECTION_CHANGED,
        {"source_id": "source-a", "connected": False},
    )
    await hass.async_block_till_done()
    async_fire_time_changed(hass, now + timedelta(minutes=5, seconds=1))
    await hass.async_block_till_done()
    action.assert_awaited_once()
    remove()


@pytest.mark.asyncio
async def test_source_duration_capability_and_unload_cancellation(
    hass: HomeAssistant,
) -> None:
    source_device_id, _ = _devices(hass)
    config = {
        CONF_PLATFORM: "device",
        CONF_DOMAIN: DOMAIN,
        CONF_DEVICE_ID: source_device_id,
        CONF_TYPE: TRIGGER_SOURCE_CONNECTED,
    }
    capabilities = await async_get_trigger_capabilities(hass, config)
    assert CONF_FOR in {
        marker.schema for marker in capabilities["extra_fields"].schema
    }

    action = AsyncMock()
    remove = await async_attach_trigger(
        hass,
        {**config, CONF_FOR: {"seconds": 30}},
        action,
        {"trigger_data": {}, "variables": {}},
    )
    now = dt_util.utcnow()
    hass.bus.async_fire(
        EVENT_SOURCE_CONNECTION_CHANGED,
        {"source_id": "source-a", "connected": True},
    )
    await hass.async_block_till_done()
    remove()
    async_fire_time_changed(hass, now + timedelta(minutes=1))
    await hass.async_block_till_done()
    action.assert_not_awaited()


@pytest.mark.asyncio
async def test_repeated_target_transition_does_not_restart_duration(
    hass: HomeAssistant,
) -> None:
    source_device_id, _ = _devices(hass)
    action = AsyncMock()
    remove = await async_attach_trigger(
        hass,
        {
            CONF_PLATFORM: "device",
            CONF_DOMAIN: DOMAIN,
            CONF_DEVICE_ID: source_device_id,
            CONF_TYPE: TRIGGER_SOURCE_DISCONNECTED,
            CONF_FOR: {"seconds": 30},
        },
        action,
        {"trigger_data": {}, "variables": {}},
    )
    now = dt_util.utcnow()
    event_data = {"source_id": "source-a", "connected": False}
    hass.bus.async_fire(EVENT_SOURCE_CONNECTION_CHANGED, event_data)
    await hass.async_block_till_done()
    async_fire_time_changed(hass, now + timedelta(seconds=20))
    hass.bus.async_fire(EVENT_SOURCE_CONNECTION_CHANGED, event_data)
    await hass.async_block_till_done()
    async_fire_time_changed(hass, now + timedelta(seconds=31))
    await hass.async_block_till_done()
    action.assert_awaited_once()
    remove()
