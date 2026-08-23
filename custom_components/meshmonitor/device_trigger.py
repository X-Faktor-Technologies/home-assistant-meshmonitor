"""UI-discoverable device triggers for received mesh messages."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.device_automation import DEVICE_TRIGGER_BASE_SCHEMA
from homeassistant.const import (
    CONF_DEVICE_ID,
    CONF_DOMAIN,
    CONF_FOR,
    CONF_PLATFORM,
    CONF_TYPE,
)
from homeassistant.core import CALLBACK_TYPE, Event, HassJob, HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import selector
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.trigger import TriggerActionType, TriggerInfo
from homeassistant.helpers.typing import ConfigType

from .const import (
    DOMAIN,
    EVENT_AUTOMATION_EXECUTED,
    EVENT_MESSAGE_RECEIVED,
    EVENT_NODE_DISCOVERED,
    EVENT_NODE_UPDATED,
    EVENT_POSITION_UPDATED,
    EVENT_SOURCE_CONNECTION_CHANGED,
    EVENT_TELEMETRY_RECEIVED,
)

TRIGGER_ANY_MESSAGE = "message_received"
TRIGGER_DIRECT_MESSAGE = "direct_message_received"
TRIGGER_CHANNEL_MESSAGE = "channel_message_received"
TRIGGER_SOURCE_CONNECTED = "source_connected"
TRIGGER_SOURCE_DISCONNECTED = "source_disconnected"
TRIGGER_AUTOMATION_COMPLETED = "automation_completed"
TRIGGER_AUTOMATION_FAILED = "automation_failed"
TRIGGER_NODE_DISCOVERED = "node_discovered"
TRIGGER_NODE_UPDATED = "node_updated"
TRIGGER_TELEMETRY_RECEIVED = "telemetry_received"
TRIGGER_POSITION_UPDATED = "position_updated"
TRIGGER_TYPES = (
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
)

ATTR_SENDER = "sender"
ATTR_CHANNEL = "channel"
ATTR_TEXT_REQUIRED = "text_required"
ATTR_NODE = "node"
ATTR_METRIC = "metric"

TRIGGER_SCHEMA = DEVICE_TRIGGER_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_TYPE): vol.In(TRIGGER_TYPES),
        vol.Optional(ATTR_SENDER): vol.All(str, str.strip, vol.Length(min=1, max=128)),
        vol.Optional(ATTR_CHANNEL): vol.Coerce(int),
        vol.Optional(ATTR_TEXT_REQUIRED, default=False): cv.boolean,
        vol.Optional(ATTR_NODE): vol.All(str, str.strip, vol.Length(min=1, max=128)),
        vol.Optional(ATTR_METRIC): vol.All(str, str.strip, vol.Length(min=1, max=128)),
        vol.Optional(CONF_FOR): cv.positive_time_period_dict,
    }
)


async def async_get_triggers(
    hass: HomeAssistant, device_id: str
) -> list[dict[str, Any]]:
    """Return message triggers only for MeshMonitor source devices."""
    if _source_id_for_device(hass, device_id) is None:
        return []
    return [
        {
            CONF_PLATFORM: "device",
            CONF_DEVICE_ID: device_id,
            CONF_DOMAIN: DOMAIN,
            CONF_TYPE: trigger_type,
        }
        for trigger_type in TRIGGER_TYPES
    ]


async def async_attach_trigger(
    hass: HomeAssistant,
    config: ConfigType,
    action: TriggerActionType,
    trigger_info: TriggerInfo,
) -> CALLBACK_TYPE:
    """Attach a source-aware listener while retaining the full event payload."""
    config = TRIGGER_SCHEMA(config)
    source_id = _source_id_for_device(hass, config[CONF_DEVICE_ID])
    if source_id is None:
        raise vol.Invalid("The selected device is not a loaded MeshMonitor source")
    trigger_type = config[CONF_TYPE]
    trigger_data = trigger_info["trigger_data"]
    job = HassJob(action, f"MeshMonitor {trigger_type} device trigger")
    pending_cancel: CALLBACK_TYPE | None = None

    @callback
    def run_action(event: Event) -> None:
        hass.loop.call_soon(
            hass.async_run_hass_job,
            job,
            {
                "trigger": {
                    **trigger_data,
                    "platform": "device",
                    "event": event,
                    "description": f"MeshMonitor {trigger_type}",
                }
            },
            event.context,
        )

    @callback
    def handle_event(event: Event) -> None:
        nonlocal pending_cancel
        if trigger_type in (
            TRIGGER_SOURCE_CONNECTED,
            TRIGGER_SOURCE_DISCONNECTED,
        ):
            if event.data.get("source_id") != source_id:
                return
            connected = event.data.get("connected")
            if not isinstance(connected, bool):
                return
            desired = trigger_type == TRIGGER_SOURCE_CONNECTED
            if connected is not desired:
                if pending_cancel is not None:
                    pending_cancel()
                    pending_cancel = None
                return
            duration = config.get(CONF_FOR)
            if duration and pending_cancel is None:
                target_event = event

                @callback
                def delayed_action(_now: Any) -> None:
                    nonlocal pending_cancel
                    pending_cancel = None
                    run_action(target_event)

                pending_cancel = async_call_later(hass, duration, delayed_action)
                return
            if pending_cancel is not None:
                return
        elif trigger_type in (
            TRIGGER_AUTOMATION_COMPLETED,
            TRIGGER_AUTOMATION_FAILED,
        ):
            if event.data.get("source_id") != source_id:
                return
            status = event.data.get("status")
            if trigger_type == TRIGGER_AUTOMATION_COMPLETED and status != "completed":
                return
            if trigger_type == TRIGGER_AUTOMATION_FAILED and status != "failed":
                return
        elif trigger_type in (
            TRIGGER_NODE_DISCOVERED,
            TRIGGER_NODE_UPDATED,
            TRIGGER_TELEMETRY_RECEIVED,
            TRIGGER_POSITION_UPDATED,
        ):
            if event.data.get("source_id") != source_id:
                return
            if ATTR_NODE in config and config[ATTR_NODE].casefold() not in {
                str(event.data.get("node_id") or "").casefold(),
                str(event.data.get("node_name") or "").casefold(),
            }:
                return
            if (
                trigger_type == TRIGGER_TELEMETRY_RECEIVED
                and ATTR_METRIC in config
                and str(event.data.get("metric") or "").casefold()
                != config[ATTR_METRIC].casefold()
            ):
                return
        else:
            if source_id not in event.data.get("source_ids", ()):
                return
            is_direct = event.data.get("is_direct") is True
            if trigger_type == TRIGGER_DIRECT_MESSAGE and not is_direct:
                return
            if trigger_type == TRIGGER_CHANNEL_MESSAGE and is_direct:
                return
            if not _message_filters_match(config, event):
                return
        run_action(event)

    event_type = (
        EVENT_SOURCE_CONNECTION_CHANGED
        if trigger_type in (TRIGGER_SOURCE_CONNECTED, TRIGGER_SOURCE_DISCONNECTED)
        else EVENT_AUTOMATION_EXECUTED
        if trigger_type in (TRIGGER_AUTOMATION_COMPLETED, TRIGGER_AUTOMATION_FAILED)
        else EVENT_NODE_DISCOVERED
        if trigger_type == TRIGGER_NODE_DISCOVERED
        else EVENT_NODE_UPDATED
        if trigger_type == TRIGGER_NODE_UPDATED
        else EVENT_TELEMETRY_RECEIVED
        if trigger_type == TRIGGER_TELEMETRY_RECEIVED
        else EVENT_POSITION_UPDATED
        if trigger_type == TRIGGER_POSITION_UPDATED
        else EVENT_MESSAGE_RECEIVED
    )
    remove_listener = hass.bus.async_listen(event_type, handle_event)

    @callback
    def remove_trigger() -> None:
        nonlocal pending_cancel
        remove_listener()
        if pending_cancel is not None:
            pending_cancel()
            pending_cancel = None

    return remove_trigger


async def async_get_trigger_capabilities(
    hass: HomeAssistant, config: ConfigType
) -> dict[str, vol.Schema]:
    """Expose optional message filters in Home Assistant's visual editor."""
    config = TRIGGER_SCHEMA(config)
    if config[CONF_TYPE] in (
        TRIGGER_SOURCE_CONNECTED,
        TRIGGER_SOURCE_DISCONNECTED,
    ):
        return {
            "extra_fields": vol.Schema(
                {vol.Optional(CONF_FOR): cv.positive_time_period_dict}
            )
        }
    if config[CONF_TYPE] not in (
        TRIGGER_ANY_MESSAGE,
        TRIGGER_DIRECT_MESSAGE,
        TRIGGER_CHANNEL_MESSAGE,
        TRIGGER_NODE_DISCOVERED,
        TRIGGER_NODE_UPDATED,
        TRIGGER_TELEMETRY_RECEIVED,
        TRIGGER_POSITION_UPDATED,
    ):
        return {"extra_fields": vol.Schema({})}
    source = _source_for_device(hass, config[CONF_DEVICE_ID])
    if source is None:
        return {"extra_fields": vol.Schema({})}
    node_options: list[Any] = [
        {"value": node.id, "label": node.long_name or node.short_name or node.id}
        for node in sorted(
            source.coordinator.nodes.values(),
            key=lambda node: (node.long_name or node.short_name or node.id).casefold(),
        )
    ]
    if config[CONF_TYPE] in (
        TRIGGER_NODE_DISCOVERED,
        TRIGGER_NODE_UPDATED,
        TRIGGER_TELEMETRY_RECEIVED,
        TRIGGER_POSITION_UPDATED,
    ):
        node_fields: dict[vol.Marker, Any] = {
            vol.Optional(ATTR_NODE): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=node_options,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                    custom_value=True,
                )
            )
        }
        if config[CONF_TYPE] == TRIGGER_TELEMETRY_RECEIVED:
            metrics = sorted(
                {
                    record.telemetry_type
                    for record in getattr(source.coordinator.data, "telemetry", ())
                    if record.telemetry_type
                },
                key=str.casefold,
            )
            node_fields[vol.Optional(ATTR_METRIC)] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=metrics,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                    custom_value=True,
                )
            )
        return {"extra_fields": vol.Schema(node_fields)}
    sender_options = node_options
    channels = getattr(getattr(source.coordinator, "data", None), "channels", ())
    channel_options: list[selector.SelectOptionDict] = [
        {
            "value": str(channel.index),
            "label": channel.display_name or channel.name or f"Channel {channel.index}",
        }
        for channel in channels
        if channel.index is not None
    ]
    fields: dict[vol.Marker, Any] = {
        vol.Optional(ATTR_SENDER): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=sender_options,
                mode=selector.SelectSelectorMode.DROPDOWN,
                custom_value=True,
            )
        ),
        vol.Optional(ATTR_TEXT_REQUIRED, default=False): selector.BooleanSelector(),
    }
    if config[CONF_TYPE] != TRIGGER_DIRECT_MESSAGE:
        fields[vol.Optional(ATTR_CHANNEL)] = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=channel_options,
                mode=selector.SelectSelectorMode.DROPDOWN,
                custom_value=True,
            )
        )
    return {"extra_fields": vol.Schema(fields)}


def _message_filters_match(config: ConfigType, event: Event) -> bool:
    """Apply only explicit optional filters and retain the original payload."""
    sender = config.get(ATTR_SENDER)
    if sender is not None:
        candidate = sender.casefold()
        if candidate not in {
            str(event.data.get("sender_id") or "").casefold(),
            str(event.data.get("sender_name") or "").casefold(),
        }:
            return False
    if ATTR_CHANNEL in config and event.data.get("channel") != config[ATTR_CHANNEL]:
        return False
    if config.get(ATTR_TEXT_REQUIRED) and not str(event.data.get("text") or "").strip():
        return False
    return True


def _source_id_for_device(hass: HomeAssistant, device_id: str) -> str | None:
    """Resolve a loaded source device without exposing the server fingerprint."""
    source = _source_for_device(hass, device_id)
    return source.source_id if source is not None else None


def _source_for_device(hass: HomeAssistant, device_id: str) -> Any | None:
    """Resolve a loaded source runtime from a registry device."""
    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        return None
    for domain, identifier in device.identifiers:
        if domain != DOMAIN or not identifier.startswith("source:"):
            continue
        parts = identifier.split(":", 2)
        if len(parts) != 3:
            continue
        fingerprint, source_id = parts[1], parts[2]
        for entry in hass.config_entries.async_loaded_entries(DOMAIN):
            runtime = getattr(entry, "runtime_data", None)
            if getattr(runtime, "fingerprint", None) != fingerprint:
                continue
            sources = getattr(runtime, "sources", {})
            if source_id in sources:
                return sources[source_id]
    return None
