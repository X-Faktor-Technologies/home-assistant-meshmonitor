"""Source-aware visual-editor actions for MeshMonitor devices."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID, CONF_DOMAIN, CONF_TYPE
from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import selector
from homeassistant.helpers.typing import ConfigType

from .const import CONF_ENABLE_NODE_MANAGEMENT, DOMAIN, SOURCE_TYPE_MESHCORE

if TYPE_CHECKING:
    from . import MeshMonitorSourceRuntime
    from .vendor_meshmonitor_client import Node

ATTR_DESTINATION_NODE_ID = "destination_node_id"
ATTR_CHANNEL = "channel"
ATTR_TEXT = "text"

ACTION_SEND_DIRECT_TO_KNOWN_NODE = "send_direct_message_to_known_node"
ACTION_SEND_TO_KNOWN_CHANNEL = "send_channel_message_to_known_channel"
ACTION_REQUEST_TRACEROUTE = "request_traceroute_from_known_node"
ACTION_REQUEST_POSITION = "request_position_from_known_node"
ACTION_REQUEST_NODEINFO = "request_node_info_from_known_node"
ACTION_REQUEST_NEIGHBORS = "request_neighbors_from_known_node"
ACTION_FAVORITE_NODE = "favorite_known_node"
ACTION_UNFAVORITE_NODE = "unfavorite_known_node"
ACTION_IGNORE_NODE = "ignore_known_node"
ACTION_UNIGNORE_NODE = "unignore_known_node"
REQUEST_ACTIONS = {
    ACTION_REQUEST_TRACEROUTE: "traceroute",
    ACTION_REQUEST_POSITION: "position",
    ACTION_REQUEST_NODEINFO: "nodeinfo",
    ACTION_REQUEST_NEIGHBORS: "neighbors",
}
ACTION_TYPES = {
    ACTION_SEND_DIRECT_TO_KNOWN_NODE,
    ACTION_SEND_TO_KNOWN_CHANNEL,
    *REQUEST_ACTIONS,
    ACTION_FAVORITE_NODE,
    ACTION_UNFAVORITE_NODE,
    ACTION_IGNORE_NODE,
    ACTION_UNIGNORE_NODE,
}

ACTION_SCHEMA = vol.Any(
    cv.DEVICE_ACTION_BASE_SCHEMA.extend(
        {
            vol.Required(CONF_TYPE): vol.In({ACTION_SEND_DIRECT_TO_KNOWN_NODE}),
            vol.Required(ATTR_DESTINATION_NODE_ID): cv.string,
            vol.Required(ATTR_TEXT): vol.All(str, vol.Length(min=1, max=200)),
        }
    ),
    cv.DEVICE_ACTION_BASE_SCHEMA.extend(
        {
            vol.Required(CONF_TYPE): vol.In({ACTION_SEND_TO_KNOWN_CHANNEL}),
            vol.Required(ATTR_CHANNEL): vol.All(vol.Coerce(int), vol.Range(min=0, max=255)),
            vol.Required(ATTR_TEXT): vol.All(str, vol.Length(min=1, max=200)),
        }
    ),
    cv.DEVICE_ACTION_BASE_SCHEMA.extend(
        {
            vol.Required(CONF_TYPE): vol.In(set(REQUEST_ACTIONS)),
            vol.Required(ATTR_DESTINATION_NODE_ID): cv.string,
        }
    ),
    cv.DEVICE_ACTION_BASE_SCHEMA.extend(
        {
            vol.Required(CONF_TYPE): vol.In(
                {
                    ACTION_FAVORITE_NODE,
                    ACTION_UNFAVORITE_NODE,
                    ACTION_IGNORE_NODE,
                    ACTION_UNIGNORE_NODE,
                }
            ),
            vol.Required(ATTR_DESTINATION_NODE_ID): cv.string,
        }
    ),
)


async def async_get_actions(hass: HomeAssistant, device_id: str) -> list[dict[str, Any]]:
    """Offer the dynamic message action only on loaded source devices."""
    source = _source_from_device(hass, device_id)
    if source is None:
        return []
    actions = [
        {
            CONF_DEVICE_ID: device_id,
            CONF_DOMAIN: DOMAIN,
            CONF_TYPE: ACTION_SEND_DIRECT_TO_KNOWN_NODE,
        }
    ]
    channels = getattr(getattr(source.coordinator, "data", None), "channels", ())
    if any(channel.index is not None for channel in channels):
        actions.append(
            {
                CONF_DEVICE_ID: device_id,
                CONF_DOMAIN: DOMAIN,
                CONF_TYPE: ACTION_SEND_TO_KNOWN_CHANNEL,
            }
        )
    if source.source_type != SOURCE_TYPE_MESHCORE:
        actions.extend(
            {
                CONF_DEVICE_ID: device_id,
                CONF_DOMAIN: DOMAIN,
                CONF_TYPE: action_type,
            }
            for action_type in REQUEST_ACTIONS
        )
    if source.options.get(CONF_ENABLE_NODE_MANAGEMENT, False):
        actions.extend(
            {
                CONF_DEVICE_ID: device_id,
                CONF_DOMAIN: DOMAIN,
                CONF_TYPE: action_type,
            }
            for action_type in (ACTION_FAVORITE_NODE, ACTION_UNFAVORITE_NODE)
        )
        if source.source_type != SOURCE_TYPE_MESHCORE:
            actions.extend(
                {
                    CONF_DEVICE_ID: device_id,
                    CONF_DOMAIN: DOMAIN,
                    CONF_TYPE: action_type,
                }
                for action_type in (ACTION_IGNORE_NODE, ACTION_UNIGNORE_NODE)
            )
    return actions


async def async_get_action_capabilities(
    hass: HomeAssistant, config: ConfigType
) -> dict[str, vol.Schema]:
    """Build a fresh source-local node selector for the automation editor."""
    source = _source_from_device(hass, config[CONF_DEVICE_ID])
    if source is None:
        raise ServiceValidationError("Select a loaded MeshMonitor source device")
    if config[CONF_TYPE] == ACTION_SEND_TO_KNOWN_CHANNEL:
        channel_options: list[selector.SelectOptionDict] = [
            {
                "value": str(channel.index),
                "label": channel.display_name
                or channel.name
                or f"Channel {channel.index}",
            }
            for channel in getattr(
                getattr(source.coordinator, "data", None), "channels", ()
            )
            if channel.index is not None
        ]
        return {
            "extra_fields": vol.Schema(
                {
                    vol.Required(ATTR_CHANNEL): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=channel_options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                            custom_value=False,
                        )
                    ),
                    vol.Required(ATTR_TEXT): selector.TextSelector(
                        selector.TextSelectorConfig(multiline=True)
                    ),
                }
            )
        }
    from .entity_policy import is_source_node

    node_options: list[selector.SelectOptionDict] = [
        {"value": node.id, "label": _node_label(node)}
        for node in sorted(
            (
                node
                for node in source.coordinator.nodes.values()
                if not is_source_node(source, node)
            ),
            key=lambda node: (
                node.is_favorite is not True,
                (node.long_name or node.short_name or node.id).casefold(),
                node.id,
            ),
        )
    ]
    fields: dict[Any, Any] = {
        vol.Required(ATTR_DESTINATION_NODE_ID): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=node_options,
                mode=selector.SelectSelectorMode.DROPDOWN,
                custom_value=False,
            )
        )
    }
    if config[CONF_TYPE] == ACTION_SEND_DIRECT_TO_KNOWN_NODE:
        fields[vol.Required(ATTR_TEXT)] = selector.TextSelector(
            selector.TextSelectorConfig(multiline=True)
        )
    return {
        "extra_fields": vol.Schema(
            fields
        )
    }


async def async_call_action_from_config(
    hass: HomeAssistant,
    config: ConfigType,
    variables: dict[str, Any],
    context: Context | None,
) -> None:
    """Send through the existing guarded service-action contract."""
    source = _source_from_device(hass, config[CONF_DEVICE_ID])
    if source is None:
        raise ServiceValidationError("Select a loaded MeshMonitor source device")
    if config[CONF_TYPE] == ACTION_SEND_TO_KNOWN_CHANNEL:
        channel = int(config[ATTR_CHANNEL])
        current_channels = {
            item.index
            for item in getattr(
                getattr(source.coordinator, "data", None), "channels", ()
            )
            if item.index is not None
        }
        if channel not in current_channels:
            raise ServiceValidationError(
                "The selected channel is not current on this source"
            )
        from .actions import ATTR_CHANNEL as SERVICE_ATTR_CHANNEL
        from .actions import ATTR_SOURCE_DEVICE_ID, SERVICE_SEND_CHANNEL_MESSAGE

        await hass.services.async_call(
            DOMAIN,
            SERVICE_SEND_CHANNEL_MESSAGE,
            {
                ATTR_SOURCE_DEVICE_ID: config[CONF_DEVICE_ID],
                SERVICE_ATTR_CHANNEL: channel,
                ATTR_TEXT: config[ATTR_TEXT],
            },
            blocking=True,
            context=context,
        )
        return
    from .entity_policy import is_source_node

    destination = config[ATTR_DESTINATION_NODE_ID]
    node = source.coordinator.nodes.get(destination)
    if node is None or is_source_node(source, node):
        raise ServiceValidationError(
            "The selected destination is not a current remote node on this source"
        )
    if config[CONF_TYPE] in REQUEST_ACTIONS:
        from .actions import request_meshtastic_node_action

        await request_meshtastic_node_action(
            hass,
            source,
            destination,
            REQUEST_ACTIONS[config[CONF_TYPE]],
            context,
        )
        return
    if config[CONF_TYPE] in {
        ACTION_FAVORITE_NODE,
        ACTION_UNFAVORITE_NODE,
        ACTION_IGNORE_NODE,
        ACTION_UNIGNORE_NODE,
    }:
        await _async_manage_node(hass, source, destination, config[CONF_TYPE], context)
        return
    from .actions import ATTR_RECIPIENT, ATTR_SOURCE_DEVICE_ID, SERVICE_SEND_DIRECT_MESSAGE

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SEND_DIRECT_MESSAGE,
        {
            ATTR_SOURCE_DEVICE_ID: config[CONF_DEVICE_ID],
            ATTR_RECIPIENT: destination,
            ATTR_TEXT: config[ATTR_TEXT],
        },
        blocking=True,
        context=context,
    )


def _node_label(node: Node) -> str:
    """Return a readable, deterministic label with an identity suffix."""
    name = node.long_name or node.short_name or "Unnamed node"
    details = [value for value in (node.short_name, _short_id(node.id)) if value]
    return f"{name} ({' · '.join(dict.fromkeys(details))})"


async def _async_manage_node(
    hass: HomeAssistant,
    source: MeshMonitorSourceRuntime,
    destination: str,
    action_type: str,
    context: Context | None,
) -> None:
    """Apply one explicit server-only node metadata change."""
    user_id = getattr(context, "user_id", None)
    if user_id is not None:
        user = await hass.auth.async_get_user(user_id)
        if user is None or not user.is_admin:
            raise ServiceValidationError(
                "MeshMonitor node actions require an administrator or HA automation context"
            )
    if not source.options.get(CONF_ENABLE_NODE_MANAGEMENT, False):
        raise ServiceValidationError(
            "Automation node-management actions are disabled for this source"
        )
    try:
        if action_type in {ACTION_FAVORITE_NODE, ACTION_UNFAVORITE_NODE}:
            favorite = action_type == ACTION_FAVORITE_NODE
            if source.source_type == SOURCE_TYPE_MESHCORE:
                await source.client.set_meshcore_favorite(source.source_id, destination, favorite)
            else:
                await source.client.set_meshtastic_favorite(source.source_id, destination, favorite)
        else:
            if source.source_type == SOURCE_TYPE_MESHCORE:
                raise ServiceValidationError("Ignore actions require a Meshtastic source")
            await source.client.set_meshtastic_ignored(
                source.source_id, destination, action_type == ACTION_IGNORE_NODE
            )
        await source.coordinator.async_request_refresh()
    except ValueError as exc:
        raise ServiceValidationError(str(exc)) from exc


def _short_id(node_id: str) -> str:
    """Keep Meshtastic IDs whole and shorten long MeshCore public keys."""
    if len(node_id) <= 16:
        return node_id
    return f"{node_id[:8]}…{node_id[-4:]}"


def _source_from_device(
    hass: HomeAssistant, device_id: str
) -> MeshMonitorSourceRuntime | None:
    """Resolve the source directly from its stable device identifier."""
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
            source = getattr(runtime, "sources", {}).get(source_id)
            if source is not None:
                return cast("MeshMonitorSourceRuntime", source)
    return None
