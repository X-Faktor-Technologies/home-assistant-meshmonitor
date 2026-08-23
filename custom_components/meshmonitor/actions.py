"""Native Home Assistant actions for bounded MeshMonitor radio writes."""

from __future__ import annotations

from hashlib import sha256
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr

from . import MeshMonitorSourceRuntime, source_runtimes
from .const import (
    CONF_ENABLE_TRANSMIT,
    DOMAIN,
    SOURCE_TYPE_MESHCORE,
    SOURCE_TYPE_MESHTASTIC,
    SOURCE_TYPE_RETICULUM,
)
from .registry import node_device_identifier, source_device_identifier
from .transmit import (
    TransmitGuardError,
    ensure_automated_airtime,
    reserve_advert_send,
    reserve_message_send,
)
from .vendor_meshmonitor_client import (
    MeshMonitorAuthenticationError,
    MeshMonitorConnectionError,
    MeshMonitorPermissionError,
    MeshMonitorRateLimitError,
    MeshMonitorResponseError,
    MeshMonitorServerError,
    MeshMonitorTransmitDisabledError,
)

SERVICE_SEND_DIRECT_MESSAGE = "send_direct_message"
SERVICE_SEND_CHANNEL_MESSAGE = "send_channel_message"
SERVICE_SEND_ADVERT = "send_advert"
ATTR_SOURCE_DEVICE_ID = "source_device_id"
ATTR_DESTINATION_DEVICE_ID = "destination_device_id"
ATTR_RECIPIENT = "recipient"
ATTR_TEXT = "text"
ATTR_CHANNEL = "channel"
ATTR_REPLY_ID = "reply_id"


def _validate_destination_choice(data: dict[str, Any]) -> dict[str, Any]:
    """Require exactly one visual-editor destination method."""
    selected = ATTR_DESTINATION_DEVICE_ID in data
    entered = ATTR_RECIPIENT in data
    if selected == entered:
        raise vol.Invalid("provide exactly one of destination_device_id or recipient")
    return data


_DEVICE_ID = vol.All(str, vol.Length(min=1, max=64))
_RECIPIENT = vol.All(str, str.strip, vol.Length(min=1, max=128))
_TEXT = vol.All(str, vol.Length(min=1, max=200))
SEND_DIRECT_SCHEMA = vol.All(
    vol.Schema(
        {
            vol.Required(ATTR_SOURCE_DEVICE_ID): _DEVICE_ID,
            vol.Optional(ATTR_DESTINATION_DEVICE_ID): _DEVICE_ID,
            vol.Optional(ATTR_RECIPIENT): _RECIPIENT,
            vol.Required(ATTR_TEXT): _TEXT,
            vol.Optional(ATTR_REPLY_ID): vol.All(vol.Coerce(int), vol.Range(min=0, max=0xFFFFFFFF)),
        }
    ),
    _validate_destination_choice,
)
SEND_CHANNEL_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_SOURCE_DEVICE_ID): _DEVICE_ID,
        vol.Required(ATTR_CHANNEL): vol.All(vol.Coerce(int), vol.Range(min=0, max=255)),
        vol.Required(ATTR_TEXT): _TEXT,
    }
)
SEND_ADVERT_SCHEMA = vol.Schema({vol.Required(ATTR_SOURCE_DEVICE_ID): _DEVICE_ID})


def async_register_actions(hass: HomeAssistant) -> None:
    """Register actions once so saved automations remain editable while offline."""
    registrations = (
        (SERVICE_SEND_DIRECT_MESSAGE, _async_send_direct_message, SEND_DIRECT_SCHEMA),
        (SERVICE_SEND_CHANNEL_MESSAGE, _async_send_channel_message, SEND_CHANNEL_SCHEMA),
        (SERVICE_SEND_ADVERT, _async_send_advert, SEND_ADVERT_SCHEMA),
    )
    for name, handler, schema in registrations:
        hass.services.async_register(
            DOMAIN,
            name,
            handler,
            schema=schema,
            supports_response=SupportsResponse.OPTIONAL,
        )


async def _async_send_direct_message(call: ServiceCall) -> dict[str, Any] | None:
    await _ensure_automation_or_admin(call)
    source = source_from_device(call.hass, call.data[ATTR_SOURCE_DEVICE_ID])
    destination = (
        _node_id_from_device(call.hass, source, call.data[ATTR_DESTINATION_DEVICE_ID])
        if ATTR_DESTINATION_DEVICE_ID in call.data
        else _node_id_from_recipient(source, call.data[ATTR_RECIPIENT])
    )
    _ensure_transmit_enabled(source)
    _reserve_message(call, source, f"direct:{destination}:{call.data[ATTR_TEXT]}")
    try:
        result: Any
        if source.source_type == SOURCE_TYPE_RETICULUM:
            if ATTR_REPLY_ID in call.data:
                raise ServiceValidationError(
                    "Numeric reply linkage is supported only by Meshtastic sources"
                )
            result = await source.client.send_reticulum_message(
                source.source_id,
                call.data[ATTR_TEXT],
                to_destination_hash=destination,
            )
        elif source.source_type == SOURCE_TYPE_MESHCORE:
            if ATTR_REPLY_ID in call.data:
                raise ServiceValidationError(
                    "Reply linkage is supported only by Meshtastic sources"
                )
            result = await source.client.send_meshcore_message(
                source.source_id, call.data[ATTR_TEXT], to_public_key=destination
            )
        else:
            send_kwargs: dict[str, Any] = {"to_node_id": destination}
            if ATTR_REPLY_ID in call.data:
                send_kwargs["reply_id"] = call.data[ATTR_REPLY_ID]
            result = await source.client.send_meshtastic_message(
                source.source_id, call.data[ATTR_TEXT], **send_kwargs
            )
    except ValueError as exc:
        raise ServiceValidationError(str(exc)) from exc
    except Exception as exc:
        raise _action_error(exc) from exc
    return _optional_response(call, _send_result(source, result))


async def _async_send_channel_message(call: ServiceCall) -> dict[str, Any] | None:
    await _ensure_automation_or_admin(call)
    source = source_from_device(call.hass, call.data[ATTR_SOURCE_DEVICE_ID])
    _ensure_transmit_enabled(source)
    channel = call.data[ATTR_CHANNEL]
    _reserve_message(call, source, f"channel:{channel}:{call.data[ATTR_TEXT]}")
    try:
        if source.source_type == SOURCE_TYPE_MESHCORE:
            result = await source.client.send_meshcore_message(
                source.source_id, call.data[ATTR_TEXT], channel=channel
            )
        else:
            result = await source.client.send_meshtastic_message(
                source.source_id, call.data[ATTR_TEXT], channel=channel
            )
    except ValueError as exc:
        raise ServiceValidationError(str(exc)) from exc
    except Exception as exc:
        raise _action_error(exc) from exc
    return _optional_response(call, _send_result(source, result))


async def _async_send_advert(call: ServiceCall) -> dict[str, Any] | None:
    await _ensure_automation_or_admin(call)
    source = source_from_device(call.hass, call.data[ATTR_SOURCE_DEVICE_ID])
    if source.source_type != SOURCE_TYPE_MESHCORE:
        raise ServiceValidationError("Send advert requires a MeshCore source device")
    _ensure_transmit_enabled(source)
    try:
        ensure_automated_airtime(source, call.context)
        reserve_advert_send(call.hass, _replay_key(call, source, "advert"))
        await source.client.send_meshcore_advert(source.source_id)
    except TransmitGuardError as exc:
        raise ServiceValidationError(exc.message) from exc
    except Exception as exc:
        raise _action_error(exc) from exc
    return _optional_response(
        call,
        {
            "accepted": True,
            "source_id": source.source_id,
            "protocol": source.source_type,
            "delivery_state": "accepted",
        },
    )


async def request_meshtastic_node_action(
    hass: HomeAssistant,
    source: MeshMonitorSourceRuntime,
    destination: str,
    action: str,
    context: Any,
) -> None:
    """Execute one guarded Meshtastic node request from a device action."""
    user_id = getattr(context, "user_id", None)
    if user_id is not None:
        user = await hass.auth.async_get_user(user_id)
        if user is None or not user.is_admin:
            raise ServiceValidationError(
                "MeshMonitor radio actions require an administrator or HA automation context"
            )
    if source.source_type == SOURCE_TYPE_MESHCORE:
        raise ServiceValidationError("This request requires a Meshtastic source")
    _ensure_transmit_enabled(source)
    context_id = getattr(context, "id", "no-context")
    body = f"request:{action}:{destination}"
    try:
        ensure_automated_airtime(source, context)
        reserve_message_send(
            hass,
            f"action:{context_id}:{source.source_id}:{sha256(body.encode()).hexdigest()}",
        )
    except TransmitGuardError as exc:
        raise ServiceValidationError(exc.message) from exc
    try:
        await source.client.request_meshtastic_node_action(source.source_id, destination, action)
    except ValueError as exc:
        raise ServiceValidationError(str(exc)) from exc
    except Exception as exc:
        raise _action_error(exc) from exc


def source_from_device(hass: HomeAssistant, device_id: str) -> MeshMonitorSourceRuntime:
    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        raise ServiceValidationError("The selected MeshMonitor source device does not exist")
    for entry in hass.config_entries.async_loaded_entries(DOMAIN):
        runtime = getattr(entry, "runtime_data", None)
        fingerprint = getattr(runtime, "fingerprint", None)
        if not fingerprint:
            continue
        for source in source_runtimes(entry):
            if source_device_identifier(fingerprint, source.source_id) in device.identifiers:
                return source
    raise ServiceValidationError(
        "Select a loaded MeshMonitor source device, not a remote node device"
    )


async def _ensure_automation_or_admin(call: ServiceCall) -> None:
    """Allow HA-owned automation contexts and authenticated administrators only."""
    user_id = call.context.user_id
    if user_id is None:
        return
    user = await call.hass.auth.async_get_user(user_id)
    if user is None or not user.is_admin:
        raise ServiceValidationError(
            "MeshMonitor radio actions require an administrator or HA automation context"
        )


def _node_id_from_device(
    hass: HomeAssistant, source: MeshMonitorSourceRuntime, device_id: str
) -> str:
    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        raise ServiceValidationError("The selected destination node device does not exist")
    fingerprint = source.entry.runtime_data.fingerprint
    for node in source.coordinator.nodes.values():
        if node_device_identifier(fingerprint, source.source_id, node.id) in device.identifiers:
            return node.id
    raise ServiceValidationError(
        "Select a remote node device belonging to the selected MeshMonitor source"
    )


def _node_id_from_recipient(source: MeshMonitorSourceRuntime, recipient: str) -> str:
    """Resolve one source-local exact node name, or return a protocol-native ID."""
    if source.source_type == SOURCE_TYPE_RETICULUM:
        destinations = getattr(getattr(source.coordinator, "data", None), "destinations", ())
        exact_hash = next(
            (
                str(destination.destination_hash)
                for destination in destinations
                if destination.destination_hash == recipient
            ),
            None,
        )
        if exact_hash is not None:
            return exact_hash
        normalized = recipient.strip().casefold()
        matches = {
            str(destination.destination_hash)
            for destination in destinations
            if destination.display_name
            and destination.display_name.strip().casefold() == normalized
        }
        if len(matches) == 1:
            return matches.pop()
        if len(matches) > 1:
            raise ServiceValidationError(
                "That Reticulum name is ambiguous; use its destination hash"
            )
        return recipient

    nodes = getattr(source.coordinator, "nodes", {})
    exact_id = next(
        (str(node.id) for node in nodes.values() if node.id == recipient),
        None,
    )
    if exact_id is not None:
        return exact_id

    normalized = recipient.casefold()
    matches = {
        str(node.id)
        for node in nodes.values()
        if any(
            name is not None and name.strip().casefold() == normalized
            for name in (node.long_name, node.short_name)
        )
    }
    if len(matches) == 1:
        return matches.pop()
    if len(matches) > 1:
        raise ServiceValidationError(
            "That node name is ambiguous on the selected source; use its protocol-native ID"
        )
    return recipient


def _ensure_transmit_enabled(source: MeshMonitorSourceRuntime) -> None:
    if source.source_type not in {
        SOURCE_TYPE_MESHCORE,
        SOURCE_TYPE_MESHTASTIC,
        SOURCE_TYPE_RETICULUM,
    }:
        raise ServiceValidationError(
            "Outbound actions are not supported for this MeshMonitor source"
        )
    if not source.options.get(CONF_ENABLE_TRANSMIT, False):
        raise ServiceValidationError(
            "Outbound radio actions are disabled for the selected MeshMonitor source"
        )


def _reserve_message(call: ServiceCall, source: MeshMonitorSourceRuntime, body: str) -> None:
    try:
        ensure_automated_airtime(source, call.context)
        reserve_message_send(call.hass, _replay_key(call, source, body))
    except TransmitGuardError as exc:
        raise ServiceValidationError(exc.message) from exc


def _replay_key(call: ServiceCall, source: MeshMonitorSourceRuntime, body: str) -> str:
    context_id = getattr(call.context, "id", "no-context")
    return f"action:{context_id}:{source.source_id}:{sha256(body.encode()).hexdigest()}"


def _action_error(exc: Exception) -> HomeAssistantError:
    if isinstance(exc, MeshMonitorPermissionError):
        return ServiceValidationError("The MeshMonitor token lacks the required write permission")
    if isinstance(exc, MeshMonitorAuthenticationError):
        return HomeAssistantError("MeshMonitor rejected the API token")
    if isinstance(exc, MeshMonitorTransmitDisabledError):
        return ServiceValidationError("MeshMonitor has transmit disabled for this source")
    if isinstance(exc, MeshMonitorRateLimitError):
        return HomeAssistantError("MeshMonitor rate limited the radio action")
    if isinstance(exc, MeshMonitorConnectionError):
        return HomeAssistantError("MeshMonitor is unreachable")
    if isinstance(exc, (MeshMonitorResponseError, MeshMonitorServerError)):
        return HomeAssistantError("MeshMonitor rejected the radio action")
    return HomeAssistantError("The MeshMonitor radio action failed")


def _send_result(source: MeshMonitorSourceRuntime, result: Any) -> dict[str, Any]:
    return {
        "accepted": True,
        "source_id": source.source_id,
        "protocol": source.source_type,
        "message_id": getattr(result, "message_id", None) or getattr(result, "id", None),
        "delivery_state": getattr(result, "delivery_state", None)
        or getattr(result, "state", None)
        or "accepted",
    }


def _optional_response(call: ServiceCall, response: dict[str, Any]) -> dict[str, Any] | None:
    """Return structured data only when the script requested a response variable."""
    return response if call.return_response else None
