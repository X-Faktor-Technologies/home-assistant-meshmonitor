"""Authenticated WebSocket API for the MeshMonitor panel."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from time import time
from typing import TYPE_CHECKING, Any
from urllib.parse import quote, urlsplit, urlunsplit

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.components.websocket_api.connection import ActiveConnection
from homeassistant.components.websocket_api.decorators import (
    async_response,
    require_admin,
    websocket_command,
)
from homeassistant.const import CONF_URL
from homeassistant.core import Context, HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr

from .automation_coordinator import (
    AutomationCoordinatorData,
    AutomationEndpointState,
    AutomationHistory,
)
from .const import (
    CONF_ENABLE_FAVORITES,
    CONF_ENABLE_NODE_MANAGEMENT,
    CONF_ENABLE_NODE_REMOVAL,
    CONF_ENABLE_TRANSMIT,
    CONF_NODE_DEVICE_POLICY,
    CONF_SCAN_INTERVAL,
    CONF_SOURCE_ID,
    CONF_SOURCE_NAME,
    CONF_SOURCE_TYPE,
    DEFAULT_NODE_DEVICE_POLICY,
    DOMAIN,
    NODE_DEVICE_POLICY_FAVORITES,
    SOURCE_TYPE_MESHCORE,
    SOURCE_TYPE_MESHTASTIC,
)
from .firmware_updates import update_presentation
from .notification_manager import MeshMonitorNotificationManager
from .registry import node_device_identifier, server_fingerprint
from .server_health_coordinator import ServerCheck, ServerHealthData
from .transmit import (
    TransmitGuardError,
    reserve_advert_send,
    reserve_message_send,
)
from .vendor_meshmonitor_client import (
    LinkQualityPoint,
    MeshMonitorAuthenticationError,
    MeshMonitorConnectionError,
    MeshMonitorNotFoundError,
    MeshMonitorPermissionError,
    MeshMonitorRateLimitError,
    MeshMonitorResponseError,
    MeshMonitorServerError,
    MeshMonitorTransmitDisabledError,
    Node,
    PositionHistoryPage,
    ReticulumSnapshot,
    ServerHealth,
    SourceSnapshot,
    TelemetryPoint,
    UnifiedMessage,
    VersionCheck,
)

if TYPE_CHECKING:
    from . import MeshMonitorConfigEntry, MeshMonitorSourceRuntime

_LOGGER = logging.getLogger(__name__)


def _serialize_node(
    node: Node,
    source_id: str,
    source_type: str,
    entry_id: str | None = None,
    device_id: str | None = None,
    favorites_enabled: bool = False,
    meshmonitor_url: str | None = None,
    local_node_id: str | None = None,
    source_updated_at: str | None = None,
) -> dict[str, Any]:
    """Return the bounded set of fields required by the read-only panel."""
    is_local_source = bool(
        source_type == SOURCE_TYPE_MESHCORE
        and local_node_id
        and node.id.casefold() == local_node_id.casefold()
    )
    local_updated_at = None
    if is_local_source and node.last_heard is None:
        local_updated_at = node.raw.get(
            "updatedAt", node.raw.get("updated_at", source_updated_at)
        )
    return {
        "id": node.id,
        "source_id": source_id,
        "entry_id": entry_id,
        "protocol": source_type,
        "name": node.long_name or node.short_name or node.id,
        "short_name": node.short_name,
        "last_heard": node.last_heard,
        # MeshCore does not RF-hear its own local identity. Keep last_heard
        # semantically honest while exposing its local telemetry/update time
        # separately for presentation and sorting.
        "is_local_source": is_local_source,
        "local_updated_at": local_updated_at,
        "latitude": node.latitude,
        "longitude": node.longitude,
        "altitude": node.altitude,
        "battery": node.battery_level,
        "voltage": node.voltage,
        "snr": node.snr,
        "rssi": node.rssi,
        "hops": node.hops_away,
        "role": node.role,
        "model": node.hardware_model,
        "firmware": node.firmware_version,
        "favorite": bool(node.is_favorite),
        "ignored": bool(node.raw.get("isIgnored", node.raw.get("is_ignored", False))),
        "device_id": device_id,
        "favorites_enabled": favorites_enabled,
        "meshmonitor_url": meshmonitor_url,
    }


def _meshmonitor_links(base_url: str, source_id: str) -> dict[str, str]:
    """Build credential-free links to verified MeshMonitor 4.14.1 UI routes."""
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return {}
    try:
        port = parsed.port
    except ValueError:
        return {}
    hostname = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
    netloc = f"{hostname}:{port}" if port is not None else hostname
    source_path = f"{parsed.path.rstrip('/')}/source/{quote(source_id, safe='')}"

    # Reconstruct the origin/path instead of appending to the configured value:
    # URL userinfo, query strings, and fragments must never reach the browser.
    def page_url(page: str) -> str:
        return urlunsplit((parsed.scheme, netloc, f"{source_path}/{page}", "", ""))

    return {
        "details": page_url("info"),
        "nodes": page_url("nodes"),
        "configuration": page_url("configuration"),
    }


def _intelligence_state(error: str | None, supported: bool) -> str:
    """Keep unsupported routes separate from transient or permission errors."""
    if error and error.startswith("resource not found:"):
        return "not_available"
    if error:
        return "error"
    return "supported" if supported else "not_available"


def _serialize_intelligence(snapshot: SourceSnapshot, source_type: str) -> dict[str, Any]:
    """Expose only bounded display fields from the in-memory link snapshots."""
    topology_error = snapshot.errors.get("topology")
    neighbors_error = snapshot.errors.get("neighbors")
    topology = snapshot.topology
    supported_source = source_type != SOURCE_TYPE_MESHCORE
    return {
        "topology": {
            "state": _intelligence_state(topology_error, topology is not None),
            "nodes": (
                [
                    {
                        "id": node.node_id,
                        "node_num": node.node_num,
                        "latitude": node.latitude,
                        "longitude": node.longitude,
                    }
                    for node in topology.nodes
                ]
                if topology is not None
                else []
            ),
            "edges": (
                [
                    {
                        "from_id": edge.from_node_id,
                        "to_id": edge.to_node_id,
                        "route": list(edge.route),
                        "snr": list(edge.snr),
                    }
                    for edge in topology.edges
                ]
                if topology is not None
                else []
            ),
        },
        "neighbors": {
            "state": _intelligence_state(neighbors_error, supported_source),
            "links": [
                {
                    "from_id": link.node_id,
                    "to_id": link.neighbor_node_id,
                    "from_num": link.node_num,
                    "to_num": link.neighbor_node_num,
                    "from_name": link.node_name,
                    "to_name": link.neighbor_name,
                    "snr": link.snr,
                    "reverse_snr": link.reverse_snr,
                    "timestamp": link.timestamp or link.last_rx_time,
                    "bidirectional": link.bidirectional,
                    "from_latitude": link.node_latitude,
                    "from_longitude": link.node_longitude,
                    "to_latitude": link.neighbor_latitude,
                    "to_longitude": link.neighbor_longitude,
                }
                for link in snapshot.neighbors
            ],
        },
    }


def _source_device_details(snapshot: SourceSnapshot, source_type: str) -> dict[str, Any]:
    """Project the useful local-device fields already cached by MeshMonitor."""
    local_id = str(snapshot.status.local_node_id or "").lower().removeprefix("!")
    local_node = next(
        (node for node in snapshot.nodes if str(node.id).lower().removeprefix("!") == local_id),
        None,
    )
    details: dict[str, Any] = {
        "model": local_node.hardware_model if local_node else None,
        "firmware": local_node.firmware_version if local_node else None,
        "battery_percent": local_node.battery_level if local_node else None,
        "battery_voltage": local_node.voltage if local_node else None,
    }
    if source_type != SOURCE_TYPE_MESHCORE:
        return details

    raw = snapshot.status.raw
    identity = raw.get("identity", raw.get("localNode"))
    identity = identity if isinstance(identity, Mapping) else {}
    latest = raw.get("latest")
    latest = latest if isinstance(latest, Mapping) else {}
    battery_mv = latest.get("batteryMv")
    details.update(
        {
            "device_type": raw.get("deviceTypeName"),
            "model": identity.get("model") or details["model"],
            "firmware": identity.get("ver") or details["firmware"],
            "firmware_build": identity.get("firmwareBuild"),
            "frequency_mhz": identity.get("radioFreq"),
            "bandwidth_khz": identity.get("radioBw"),
            "spreading_factor": identity.get("radioSf"),
            "coding_rate": identity.get("radioCr"),
            "tx_power_dbm": identity.get("txPower"),
            "max_tx_power_dbm": identity.get("maxTxPower"),
            "battery_voltage": (
                battery_mv / 1000
                if isinstance(battery_mv, (int, float)) and not isinstance(battery_mv, bool)
                else details["battery_voltage"]
            ),
            "uptime_seconds": latest.get("uptimeSecs"),
            "tx_queue": latest.get("queueLen"),
            "noise_floor_dbm": latest.get("noiseFloor"),
            "last_rssi_dbm": latest.get("lastRssi"),
            "last_snr_db": latest.get("lastSnr"),
            "packets_received": latest.get("packetsRecv"),
            "receive_errors": latest.get("recvErrors"),
            "rx_airtime_seconds": latest.get("rxAirSecs"),
            "last_poll": latest.get("timestamp"),
        }
    )
    return details


def _serialize_entry(
    entry: MeshMonitorSourceRuntime,
    device_registry: dr.DeviceRegistry | None = None,
    firmware_releases: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Serialize one loaded entry without credentials or raw API payloads."""
    coordinator = entry.runtime_data.coordinator
    snapshot = coordinator.data
    source_id = entry.data[CONF_SOURCE_ID]
    source_type = entry.data.get(CONF_SOURCE_TYPE, "meshtastic")
    scan_interval = int(entry.options.get(CONF_SCAN_INTERVAL, 60))
    meshmonitor_links = _meshmonitor_links(entry.data.get(CONF_URL, ""), source_id)
    if snapshot is None:
        return {
            "entry_id": entry.entry_id,
            "source_id": source_id,
            "name": entry.data.get(CONF_SOURCE_NAME, entry.title),
            "protocol": source_type,
            "available": False,
            "connected": None,
            "local_node_id": None,
            "fetched_at": None,
            "stale_after_seconds": max(300, scan_interval * 3),
            "node_count": 0,
            "positioned_count": 0,
            "errors": [],
            "meshmonitor_links": meshmonitor_links,
            "topology": {"state": "not_available", "nodes": [], "edges": []},
            "neighbors": {"state": "not_available", "links": []},
            "device": {},
            "firmware_update": update_presentation(source_type, None, firmware_releases or {}),
            "transmit_enabled": bool(entry.options.get(CONF_ENABLE_TRANSMIT, False)),
            "favorites_enabled": bool(entry.options.get(CONF_ENABLE_FAVORITES, False)),
            "node_management_enabled": bool(
                entry.options.get(CONF_ENABLE_NODE_MANAGEMENT, False)
            ),
            "node_removal_enabled": bool(entry.options.get(CONF_ENABLE_NODE_REMOVAL, False)),
            "channels": [],
            "nodes": [],
        }
    if isinstance(snapshot, ReticulumSnapshot):
        identity = snapshot.identity
        return {
            "entry_id": entry.entry_id,
            "source_id": source_id,
            "name": entry.data.get(CONF_SOURCE_NAME, entry.title),
            "protocol": source_type,
            "available": coordinator.last_update_success,
            "connected": snapshot.status.connected,
            "local_node_id": None,
            "fetched_at": snapshot.fetched_at.isoformat(),
            "stale_after_seconds": max(300, scan_interval * 3),
            "node_count": 0,
            "positioned_count": 0,
            "errors": sorted(snapshot.errors),
            "meshmonitor_links": meshmonitor_links,
            "topology": {"state": "not_available", "nodes": [], "edges": []},
            "neighbors": {"state": "not_available", "links": []},
            "device": {},
            "reticulum": {
                "interface_count": snapshot.status.interface_count,
                "destination_count": snapshot.status.destination_count,
                "rns_version": snapshot.status.rns_version,
                "bridge_version": snapshot.status.bridge_version,
                "mode": snapshot.status.mode,
                "identity_name": identity.display_name if identity else None,
                "identity_hash": identity.destination_hash if identity else None,
            },
            "firmware_update": update_presentation(
                source_type, None, firmware_releases or {}
            ),
            "transmit_enabled": False,
            "favorites_enabled": False,
            "node_management_enabled": False,
            "node_removal_enabled": False,
            "channels": [],
            "nodes": [],
        }
    source_device = _source_device_details(snapshot, source_type)
    return {
        "entry_id": entry.entry_id,
        "source_id": source_id,
        "name": entry.data.get(CONF_SOURCE_NAME, entry.title),
        "protocol": source_type,
        "available": coordinator.last_update_success,
        "connected": snapshot.status.connected,
        "local_node_id": snapshot.status.local_node_id,
        "fetched_at": snapshot.fetched_at.isoformat(),
        # Three missed configured cycles, with a five-minute floor, is stale.
        # Sending the threshold keeps the browser model correct for 30-3600s
        # custom polling without exposing credentials or coordinator internals.
        "stale_after_seconds": max(300, scan_interval * 3),
        "node_count": len(snapshot.nodes),
        "positioned_count": sum(
            node.latitude is not None and node.longitude is not None for node in snapshot.nodes
        ),
        "errors": sorted(snapshot.errors),
        "meshmonitor_links": meshmonitor_links,
        "device": source_device,
        "firmware_update": update_presentation(
            source_type, source_device.get("firmware"), firmware_releases or {}
        ),
        **_serialize_intelligence(snapshot, source_type),
        "transmit_enabled": bool(entry.options.get(CONF_ENABLE_TRANSMIT, False)),
        "favorites_enabled": bool(entry.options.get(CONF_ENABLE_FAVORITES, False)),
        "node_management_enabled": bool(
            entry.options.get(CONF_ENABLE_NODE_MANAGEMENT, False)
        ),
        "node_removal_enabled": bool(entry.options.get(CONF_ENABLE_NODE_REMOVAL, False)),
        # Channel secrets and raw payloads are deliberately excluded. `has_key`
        # is sufficient for presentation without moving credentials browser-side.
        "channels": [
            {
                "id": channel.id,
                "index": channel.index,
                "name": channel.display_name or channel.name or f"Channel {channel.index}",
                "role": channel.role,
                "scope": channel.scope,
                "uplink_enabled": channel.uplink_enabled,
                "downlink_enabled": channel.downlink_enabled,
                "position_precision": channel.position_precision,
                "has_key": channel.has_key,
            }
            for channel in snapshot.channels
        ],
        "nodes": [
            _serialize_node(
                node,
                source_id,
                source_type,
                entry.entry_id,
                (
                    device.id
                    if device_registry
                    and (
                        device := device_registry.async_get_device(
                            identifiers={
                                node_device_identifier(
                                    server_fingerprint(entry.data.get(CONF_URL, "")),
                                    source_id,
                                    node.id,
                                )
                            }
                        )
                    )
                    else None
                ),
                bool(entry.options.get(CONF_ENABLE_FAVORITES, False)),
                meshmonitor_links.get("nodes"),
                snapshot.status.local_node_id,
                source_device.get("last_poll") or snapshot.fetched_at.isoformat(),
            )
            for node in snapshot.nodes
        ],
    }


def _serialize_message(
    message: UnifiedMessage,
    entry_id: str | None = None,
    local_node_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Serialize normalized message fields without raw protocol payloads."""
    sender = (message.from_id or "").lower().removeprefix("!")
    outgoing = bool(sender and sender in (local_node_ids or set()))
    return {
        "id": message.id,
        "entry_id": entry_id,
        "protocol": message.protocol,
        "from_id": message.from_id,
        "from_name": message.from_name,
        "to_id": message.to_id,
        "channel": message.channel,
        "channel_name": message.channel_name,
        "text": message.text,
        "timestamp": message.timestamp,
        "created_at": message.created_at,
        "emoji": message.emoji,
        "reply_id": message.reply_id,
        "outgoing": outgoing,
        "direction": "outbound" if outgoing else "incoming",
        "receptions": [
            {
                "source_id": reception.source_id,
                "source_name": reception.source_name,
                "source_type": reception.source_type,
                "rssi": reception.rssi,
                "snr": reception.snr,
            }
            for reception in message.receptions
        ],
    }


def _message_poll_state(runtimes: list[dict[str, Any]]) -> str:
    """Summarize stored-history lifecycle without exposing source identity."""
    if not runtimes:
        return "disabled"
    coordinators = [runtime["coordinator"] for runtime in runtimes]
    if any(coordinator.partial_failure for coordinator in coordinators):
        return "partial"
    if any(not coordinator.last_update_success for coordinator in coordinators):
        has_prior_data = any(coordinator.data is not None for coordinator in coordinators)
        return "stale" if has_prior_data else "error"
    return "ready"


def _serialize_automation_history(history: AutomationHistory) -> dict[str, Any]:
    """Project only recent run identity, status, source, and time metadata."""
    return {
        "state": history.state.value,
        "may_be_truncated": history.may_be_truncated,
        "history_gap": history.history_gap,
        "runs": [
            {
                "id": run.id,
                "source_id": run.source_id,
                "status": run.status,
                "started_at": run.started_at,
                "updated_at": run.updated_at,
            }
            for run in history.runs
        ],
    }


def _serialize_automation_data(data: AutomationCoordinatorData) -> dict[str, Any]:
    """Serialize the bounded in-memory projection, never client raw mappings."""
    histories = {history.automation_id: history for history in data.histories}
    automations = []
    for definition in data.definitions:
        history = histories.get(definition.id)
        if history is None:
            history = AutomationHistory(
                definition.id,
                state=AutomationEndpointState.PENDING,
            )
        automations.append(
            {
                "id": definition.id,
                "name": definition.name,
                "description": definition.description,
                "enabled": definition.enabled,
                "created_at": definition.created_at,
                "updated_at": definition.updated_at,
                "history": _serialize_automation_history(history),
            }
        )
    return {
        "state": data.list_state.value,
        "definitions_truncated": data.definitions_truncated,
        "automations": automations,
    }


def _serialize_automation_groups(
    hass: HomeAssistant, entries: list[MeshMonitorSourceRuntime]
) -> list[dict[str, Any]]:
    """Identify server-global data by already-visible sources, never by server URL."""
    groups = []
    runtimes = hass.data.get(DOMAIN, {}).get("automation_coordinators", {})
    for runtime_key, runtime in runtimes.items():
        matching_entries = [
            entry
            for entry in entries
            if entry.entry_id == runtime_key or entry.data.get(CONF_URL) == runtime_key
        ]
        source_pairs = {
            (
                entry.data[CONF_SOURCE_ID],
                entry.data.get(CONF_SOURCE_NAME, entry.title),
            )
            for entry in matching_entries
        }
        sources = [
            {"id": source_id, "name": source_name}
            for source_id, source_name in sorted(
                source_pairs, key=lambda source: (source[1].casefold(), source[0])
            )
        ]
        coordinator = runtime["coordinator"]
        group = _serialize_automation_data(coordinator.data or AutomationCoordinatorData())
        group["entry_ids"] = sorted({entry.entry_id for entry in matching_entries})
        group["sources"] = sources
        groups.append(group)
    return sorted(
        groups,
        key=lambda group: tuple(
            (source["name"].casefold(), source["id"]) for source in group["sources"]
        ),
    )


def _safe_release_url(value: str | None) -> str | None:
    """Allow only the verified upstream project's HTTPS release pages."""
    if not value:
        return None
    parsed = urlsplit(value)
    if (
        parsed.scheme == "https"
        and parsed.hostname == "github.com"
        and parsed.path.startswith("/Yeraze/meshmonitor/releases/")
    ):
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    return None


def _serialize_server_check(check: ServerCheck, kind: str) -> dict[str, Any]:
    """Project one allow-listed health or version result."""
    result: dict[str, Any] = {
        "state": check.state.value,
        "stale": check.stale,
        "last_success_at": (
            check.last_success_at.isoformat()
            if check.last_success_at is not None
            else None
        ),
        "last_attempt_at": (
            check.last_attempt_at.isoformat()
            if check.last_attempt_at is not None
            else None
        ),
        "value": None,
    }
    if kind == "health" and isinstance(check.value, ServerHealth):
        result["value"] = {
            "status": check.value.status,
            "version": check.value.version,
            "uptime_ms": check.value.uptime_ms,
            "database_type": check.value.database_type,
        }
    elif kind == "version" and isinstance(check.value, VersionCheck):
        result["value"] = {
            "update_available": check.value.update_available,
            "current_version": check.value.current_version,
            "latest_version": check.value.latest_version,
            "release_url": _safe_release_url(check.value.release_url),
            "release_name": check.value.release_name,
            "published_at": check.value.published_at,
            "image_ready": check.value.image_ready,
        }
    return result


def _serialize_server_health(
    hass: HomeAssistant, entries: list[MeshMonitorConfigEntry]
) -> list[dict[str, Any]]:
    """Expose one compact exact-server result without URLs, tokens, or raw data."""
    runtimes = hass.data.get(DOMAIN, {}).get("server_health_coordinators", {})
    result = []
    for entry in sorted(entries, key=lambda item: (item.title.casefold(), item.entry_id)):
        runtime = runtimes.get(entry.entry_id)
        data = (
            runtime["coordinator"].data
            if runtime is not None and runtime["coordinator"].data is not None
            else ServerHealthData()
        )
        result.append(
            {
                "entry_id": entry.entry_id,
                "name": entry.title,
                "source_count": len(entry.runtime_data.sources),
                "health": _serialize_server_check(data.health, "health"),
                "version": _serialize_server_check(data.version, "version"),
            }
        )
    return result


def _position_history_result(page: PositionHistoryPage, hours: int, before: int) -> dict[str, Any]:
    """Serialize one bounded history page without exposing raw telemetry fields."""
    return {
        "state": "supported",
        "hours": hours,
        "before": before,
        "count": page.count,
        "total": page.total,
        "limit": page.limit,
        "fixes": [
            {
                "timestamp": fix.timestamp,
                "latitude": fix.latitude,
                "longitude": fix.longitude,
                "altitude": fix.altitude,
                "ground_speed": fix.ground_speed,
                "ground_track": fix.ground_track,
                "snr": fix.snr,
                "hop_start": fix.hop_start,
                "hop_limit": fix.hop_limit,
            }
            for fix in page.fixes
            if fix.latitude is not None and fix.longitude is not None
        ],
    }


def _telemetry_history_result(points: list[TelemetryPoint], *, truncated: bool) -> dict[str, Any]:
    """Project bounded telemetry trends without packet or raw API fields."""
    return {
        "state": "supported",
        "truncated": truncated,
        "points": [
            {
                "type": point.telemetry_type,
                "timestamp": (point.timestamp if point.timestamp is not None else point.created_at),
                "value": point.value,
                "unit": point.unit,
            }
            for point in points
        ],
    }


def _link_quality_result(points: list[LinkQualityPoint], *, truncated: bool) -> dict[str, Any]:
    """Project bounded link-quality trends without exposing raw mappings."""
    return {
        "state": "supported",
        "truncated": truncated,
        "points": [{"timestamp": point.timestamp, "quality": point.quality} for point in points],
    }


def _history_failure_state(error: Exception) -> str:
    """Map optional history failures to honest panel lifecycle states."""
    if isinstance(error, MeshMonitorPermissionError):
        return "permission_denied"
    if isinstance(error, MeshMonitorNotFoundError):
        return "not_available"
    return "error"


def _source_views(
    entries: list[MeshMonitorConfigEntry],
) -> list[MeshMonitorSourceRuntime]:
    """Flatten server entries into their stable source runtime contexts."""
    # Imported lazily because the integration initializer imports this module
    # before defining its runtime helpers.
    from . import source_runtimes

    result: list[MeshMonitorSourceRuntime] = []
    for entry in entries:
        result.extend(source_runtimes(entry))
    return result


def _loaded_source_entry(
    hass: HomeAssistant, source_id: str, entry_id: str | None = None
) -> MeshMonitorSourceRuntime | None:
    """Resolve exactly one loaded source without exposing a generic client lookup."""
    loaded = [
        item
        for item in hass.config_entries.async_loaded_entries(DOMAIN)
        if getattr(item, "runtime_data", None) is not None
    ]
    matches = [
        item
        for item in _source_views(loaded)
        if item.data.get(CONF_SOURCE_ID) == source_id
        and (entry_id is None or item.entry_id == entry_id)
    ]
    return matches[0] if len(matches) == 1 else None


@websocket_command({vol.Required("type"): "meshmonitor/panel"})
@async_response
async def websocket_get_panel_data(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return current in-memory coordinator data; never call MeshMonitor here."""
    server_entries = [
        entry
        for entry in hass.config_entries.async_loaded_entries(DOMAIN)
        if getattr(entry, "runtime_data", None) is not None
    ]
    entries = _source_views(server_entries)
    message_runtimes = list(hass.data.get(DOMAIN, {}).get("message_coordinators", {}).values())
    messages = {
        (entry_id, message.id): (entry_id, message)
        for entry_id, runtime in hass.data.get(DOMAIN, {}).get("message_coordinators", {}).items()
        for message in (runtime["coordinator"].data or ())
    }
    ordered_messages = sorted(
        messages.values(),
        key=lambda item: str(item[1].created_at or ""),
        reverse=True,
    )
    local_ids_by_entry: dict[str, set[str]] = {}
    for source in entries:
        snapshot = source.runtime_data.coordinator.data
        local_id = getattr(getattr(snapshot, "status", None), "local_node_id", None)
        if local_id:
            local_ids_by_entry.setdefault(source.entry_id, set()).add(
                str(local_id).lower().removeprefix("!")
            )
    device_registry = dr.async_get(hass)
    connection.send_result(
        msg["id"],
        {
            "can_send_messages": bool(
                getattr(getattr(connection, "user", None), "is_admin", False)
            ),
            "sources": [
                _serialize_entry(
                    entry,
                    device_registry,
                    hass.data.get(DOMAIN, {}).get("firmware_releases", {}),
                )
                for entry in entries
            ],
            "messages": [
                _serialize_message(message, entry_id, local_ids_by_entry.get(entry_id))
                for entry_id, message in ordered_messages
            ],
            "message_status": _message_poll_state(message_runtimes),
            "automation_groups": _serialize_automation_groups(hass, entries),
            "servers": _serialize_server_health(hass, server_entries),
        },
    )


@websocket_command(
    {
        vol.Required("type"): "meshmonitor/position_history",
        vol.Required("source_id"): str,
        vol.Optional("entry_id"): str,
        vol.Required("node_id"): str,
        vol.Required("hours"): vol.In((1, 6, 24, 72, 168)),
    }
)
@async_response
async def websocket_get_position_history(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Read one fixed-window trail on demand; panel refresh never calls this route."""
    entry = _loaded_source_entry(hass, msg["source_id"], msg.get("entry_id"))
    if entry is None:
        connection.send_error(msg["id"], "not_found", "MeshMonitor source not found")
        return
    if entry.data.get(CONF_SOURCE_TYPE) == SOURCE_TYPE_MESHCORE:
        connection.send_result(msg["id"], {"state": "not_available", "fixes": [], "total": 0})
        return

    # Constrain the path parameter to the coordinator's visible node inventory.
    # This keeps the command a node-trail feature rather than a generic API proxy.
    snapshot = entry.runtime_data.coordinator.data
    if (
        snapshot is None
        or isinstance(snapshot, ReticulumSnapshot)
        or not any(node.id == msg["node_id"] for node in snapshot.nodes)
    ):
        connection.send_error(msg["id"], "not_found", "MeshMonitor node not found")
        return

    before = int(time() * 1000) + 1
    since = before - msg["hours"] * 60 * 60 * 1000
    try:
        page = await entry.runtime_data.client.get_position_history(
            msg["source_id"],
            msg["node_id"],
            since=since,
            before=before,
            limit=1000,
            offset=0,
        )
    except MeshMonitorPermissionError:
        # Private-position nodes may need nodes_private:read in addition to the
        # normal nodes:read grant. Never misrepresent this denial as an empty trail.
        connection.send_result(msg["id"], {"state": "permission_denied", "fixes": [], "total": 0})
        return
    except MeshMonitorNotFoundError:
        connection.send_result(msg["id"], {"state": "not_available", "fixes": [], "total": 0})
        return
    except MeshMonitorAuthenticationError:
        connection.send_error(msg["id"], "invalid_auth", "MeshMonitor rejected the token")
        return
    except MeshMonitorConnectionError:
        connection.send_error(msg["id"], "cannot_connect", "MeshMonitor is unreachable")
        return
    except MeshMonitorRateLimitError:
        connection.send_error(msg["id"], "rate_limited", "MeshMonitor rate limit reached")
        return
    except (MeshMonitorResponseError, MeshMonitorServerError):
        connection.send_error(msg["id"], "history_failed", "Position history read failed")
        return

    connection.send_result(msg["id"], _position_history_result(page, msg["hours"], before))


@websocket_command(
    {
        vol.Required("type"): "meshmonitor/node_history",
        vol.Required("source_id"): str,
        vol.Optional("entry_id"): str,
        vol.Required("node_id"): str,
        vol.Required("hours"): vol.In((1, 6, 24, 72, 168)),
    }
)
@async_response
async def websocket_get_node_history(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Read two fixed-window node trends only after an explicit panel action."""
    entry = _loaded_source_entry(hass, msg["source_id"], msg.get("entry_id"))
    if entry is None:
        connection.send_error(msg["id"], "not_found", "MeshMonitor source not found")
        return
    snapshot = entry.runtime_data.coordinator.data
    if (
        snapshot is None
        or isinstance(snapshot, ReticulumSnapshot)
        or not any(node.id == msg["node_id"] for node in snapshot.nodes)
    ):
        # The visible coordinator inventory is the authorization scope; this
        # command cannot be used as an arbitrary node-history API passthrough.
        connection.send_error(msg["id"], "not_found", "MeshMonitor node not found")
        return

    telemetry: dict[str, Any]
    link_quality: dict[str, Any]
    try:
        telemetry_points = await entry.runtime_data.client.get_node_telemetry_history(
            msg["source_id"], msg["node_id"], hours=msg["hours"]
        )
        telemetry = _telemetry_history_result(
            telemetry_points[:1000], truncated=len(telemetry_points) > 1000
        )
    except (
        MeshMonitorAuthenticationError,
        MeshMonitorConnectionError,
        MeshMonitorNotFoundError,
        MeshMonitorPermissionError,
        MeshMonitorRateLimitError,
        MeshMonitorResponseError,
        MeshMonitorServerError,
    ) as error:
        telemetry = {
            "state": _history_failure_state(error),
            "truncated": False,
            "points": [],
        }

    try:
        link_points = await entry.runtime_data.client.get_node_link_quality(
            msg["source_id"], msg["node_id"], hours=msg["hours"]
        )
        link_quality = _link_quality_result(link_points[:1000], truncated=len(link_points) > 1000)
    except (
        MeshMonitorAuthenticationError,
        MeshMonitorConnectionError,
        MeshMonitorNotFoundError,
        MeshMonitorPermissionError,
        MeshMonitorRateLimitError,
        MeshMonitorResponseError,
        MeshMonitorServerError,
    ) as error:
        link_quality = {
            "state": _history_failure_state(error),
            "truncated": False,
            "points": [],
        }

    connection.send_result(
        msg["id"],
        {
            "hours": msg["hours"],
            "telemetry": telemetry,
            "link_quality": link_quality,
        },
    )


@websocket_command(
    {
        vol.Required("type"): "meshmonitor/send_message",
        vol.Required("source_id"): str,
        vol.Optional("entry_id"): str,
        vol.Required("protocol"): vol.In(("meshtastic", "meshcore")),
        vol.Required("text"): str,
        vol.Required("nonce"): vol.All(str, vol.Length(min=16, max=64)),
        vol.Required("confirm"): "SEND",
        vol.Optional("channel"): vol.Coerce(int),
        vol.Optional("destination"): str,
    }
)
@require_admin
@async_response
async def websocket_send_message(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Send one tightly bounded message after all independent gates pass."""
    entry = _loaded_source_entry(hass, msg["source_id"], msg.get("entry_id"))
    if entry is None:
        connection.send_error(msg["id"], "not_found", "MeshMonitor source not found")
        return
    if not entry.options.get(CONF_ENABLE_TRANSMIT, False):
        connection.send_error(msg["id"], "transmit_disabled", "Outbound messages are disabled")
        return
    source_type = entry.data.get(CONF_SOURCE_TYPE, "meshtastic")
    if msg["protocol"] != source_type:
        connection.send_error(
            msg["id"], "protocol_mismatch", "Source protocol does not match review"
        )
        return
    if ("channel" in msg) == ("destination" in msg):
        connection.send_error(
            msg["id"], "invalid_destination", "Choose exactly one channel or recipient"
        )
        return

    try:
        # Browser controls are a usability layer, not an authorization boundary;
        # panel and automation sends therefore share one backend guard.
        reserve_message_send(hass, f"panel:{msg['nonce']}")
    except TransmitGuardError as exc:
        connection.send_error(msg["id"], exc.code, exc.message)
        return

    async def perform_send() -> None:
        """Finish the one reviewed send independently of the browser socket."""
        client = entry.runtime_data.client
        try:
            if source_type == SOURCE_TYPE_MESHCORE:
                result = await client.send_meshcore_message(
                    msg["source_id"],
                    msg["text"],
                    channel=msg.get("channel"),
                    to_public_key=msg.get("destination"),
                )
            else:
                result = await client.send_meshtastic_message(
                    msg["source_id"],
                    msg["text"],
                    channel=msg.get("channel"),
                    to_node_id=msg.get("destination"),
                )
        except Exception as exc:  # Result is retained without automatic retry.
            _LOGGER.error("Background MeshMonitor send failed: %s", type(exc).__name__)
            return
        _LOGGER.info(
            "Background MeshMonitor send accepted for source %s (%s)",
            msg["source_id"],
            result.delivery_state or "accepted",
        )
        message_runtime = (
            hass.data.get(DOMAIN, {}).get("message_coordinators", {}).get(entry.entry_id)
        )
        if message_runtime:
            await message_runtime["coordinator"].async_request_refresh()

    try:
        hass.async_create_task(perform_send(), "MeshMonitor reviewed radio send")
    except Exception as exc:
        _LOGGER.exception("Unable to schedule reviewed MeshMonitor send")
        connection.send_error(msg["id"], "queue_failed", type(exc).__name__)
        return
    connection.send_result(
        msg["id"],
        {"accepted": True, "message_id": None, "delivery_state": "ha_queued"},
    )


@websocket_command(
    {
        vol.Required("type"): "meshmonitor/send_meshcore_advert",
        vol.Required("source_id"): str,
        vol.Optional("entry_id"): str,
        vol.Required("nonce"): vol.All(str, vol.Length(min=16, max=64)),
        vol.Required("confirm"): "ADVERT",
    }
)
@require_admin
@async_response
async def websocket_send_meshcore_advert(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Send one reviewed MeshCore flood advert with no automatic retry."""
    entry = _loaded_source_entry(hass, msg["source_id"], msg.get("entry_id"))
    if entry is None:
        connection.send_error(msg["id"], "not_found", "MeshMonitor source not found")
        return
    if entry.data.get(CONF_SOURCE_TYPE) != SOURCE_TYPE_MESHCORE:
        connection.send_error(msg["id"], "protocol_mismatch", "Advert requires a MeshCore source")
        return
    if not entry.options.get(CONF_ENABLE_TRANSMIT, False):
        connection.send_error(msg["id"], "transmit_disabled", "Outbound radio actions are disabled")
        return

    try:
        reserve_advert_send(hass, f"panel:{msg['nonce']}")
    except TransmitGuardError as exc:
        connection.send_error(msg["id"], exc.code, exc.message)
        return

    try:
        await entry.runtime_data.client.send_meshcore_advert(msg["source_id"])
    except MeshMonitorPermissionError:
        connection.send_error(
            msg["id"], "permission_denied", "MeshMonitor token lacks connection:write"
        )
        return
    except MeshMonitorAuthenticationError:
        connection.send_error(msg["id"], "invalid_auth", "MeshMonitor rejected the token")
        return
    except MeshMonitorTransmitDisabledError:
        connection.send_error(msg["id"], "transmit_disabled", "MeshMonitor transmit is disabled")
        return
    except MeshMonitorRateLimitError:
        connection.send_error(msg["id"], "rate_limited", "MeshMonitor rate limited the advert")
        return
    except MeshMonitorConnectionError:
        connection.send_error(msg["id"], "cannot_connect", "MeshMonitor is unreachable")
        return
    except (MeshMonitorResponseError, MeshMonitorServerError):
        connection.send_error(msg["id"], "advert_failed", "MeshMonitor rejected the advert")
        return
    connection.send_result(msg["id"], {"accepted": True, "delivery_state": "accepted"})


@websocket_command(
    {
        vol.Required("type"): "meshmonitor/set_favorite",
        vol.Required("source_id"): str,
        vol.Optional("entry_id"): str,
        vol.Required("node_id"): str,
        vol.Required("favorite"): bool,
    }
)
@require_admin
@async_response
async def websocket_set_favorite(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Persist one favorite through an explicit, independently gated route."""
    entry = _loaded_source_entry(hass, msg["source_id"], msg.get("entry_id"))
    if entry is None:
        connection.send_error(msg["id"], "not_found", "MeshMonitor source not found")
        return
    if not entry.options.get(CONF_ENABLE_FAVORITES, False):
        connection.send_error(msg["id"], "favorites_disabled", "Favorite changes are disabled")
        return
    try:
        if entry.source_type == SOURCE_TYPE_MESHCORE:
            await entry.runtime_data.client.set_meshcore_favorite(
                msg["source_id"], msg["node_id"], msg["favorite"]
            )
        else:
            await entry.runtime_data.client.set_meshtastic_favorite(
                msg["source_id"], msg["node_id"], msg["favorite"]
            )
    except ValueError as exc:
        connection.send_error(msg["id"], "invalid_format", str(exc))
        return
    except MeshMonitorPermissionError:
        connection.send_error(msg["id"], "permission_denied", "MeshMonitor token lacks nodes:write")
        return
    except MeshMonitorAuthenticationError:
        connection.send_error(msg["id"], "invalid_auth", "MeshMonitor rejected the token")
        return
    except MeshMonitorConnectionError:
        connection.send_error(msg["id"], "cannot_connect", "MeshMonitor is unreachable")
        return
    except (MeshMonitorResponseError, MeshMonitorServerError):
        connection.send_error(
            msg["id"], "favorite_failed", "MeshMonitor rejected the favorite change"
        )
        return
    await entry.coordinator.async_request_refresh()
    from . import server_options

    if (
        server_options(entry.entry).get(
            CONF_NODE_DEVICE_POLICY, DEFAULT_NODE_DEVICE_POLICY
        )
        == NODE_DEVICE_POLICY_FAVORITES
    ):
        await hass.config_entries.async_reload(entry.entry_id)
    connection.send_result(msg["id"], {"favorite": msg["favorite"]})


@websocket_command(
    {
        vol.Required("type"): "meshmonitor/request_node_action",
        vol.Required("source_id"): str,
        vol.Required("entry_id"): str,
        vol.Required("node_id"): str,
        vol.Required("action"): vol.In(("traceroute", "position", "nodeinfo", "neighbors")),
    }
)
@require_admin
@async_response
async def websocket_request_node_action(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Run one reviewed manual Meshtastic request for a remote node."""
    entry = _loaded_source_entry(hass, msg["source_id"], msg["entry_id"])
    if entry is None:
        connection.send_error(msg["id"], "not_found", "MeshMonitor source not found")
        return
    snapshot = entry.runtime_data.coordinator.data
    if isinstance(snapshot, ReticulumSnapshot):
        connection.send_error(msg["id"], "not_supported", "Node requests require Meshtastic")
        return
    node = next(
        (item for item in (snapshot.nodes if snapshot else ()) if item.id == msg["node_id"]),
        None,
    )
    local_id = str(snapshot.status.local_node_id).lower().removeprefix("!") if snapshot else ""
    if node is None:
        connection.send_error(msg["id"], "not_found", "Node is no longer present")
        return
    if local_id and local_id == str(node.id).lower().removeprefix("!"):
        connection.send_error(
            msg["id"], "local_node", "The monitored source node cannot request itself"
        )
        return
    from .actions import request_meshtastic_node_action

    try:
        await request_meshtastic_node_action(
            hass,
            entry,
            msg["node_id"],
            msg["action"],
            Context(user_id=connection.user.id),
        )
    except ServiceValidationError as exc:
        connection.send_error(msg["id"], "request_failed", str(exc))
        return
    connection.send_result(
        msg["id"],
        {"accepted": True, "action": msg["action"], "delivery_state": "accepted"},
    )


@websocket_command(
    {
        vol.Required("type"): "meshmonitor/set_node_ignored",
        vol.Required("source_id"): str,
        vol.Required("entry_id"): str,
        vol.Required("node_id"): str,
        vol.Required("ignored"): bool,
    }
)
@require_admin
@async_response
async def websocket_set_node_ignored(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Persist one server-only Meshtastic ignore state after confirmation."""
    entry = _loaded_source_entry(hass, msg["source_id"], msg["entry_id"])
    if entry is None:
        connection.send_error(msg["id"], "not_found", "MeshMonitor source not found")
        return
    if entry.source_type != SOURCE_TYPE_MESHTASTIC:
        connection.send_error(msg["id"], "not_supported", "Ignore requires a Meshtastic source")
        return
    if not entry.options.get(CONF_ENABLE_NODE_MANAGEMENT, False):
        connection.send_error(
            msg["id"], "management_disabled", "Node management actions are disabled"
        )
        return
    try:
        await entry.runtime_data.client.set_meshtastic_ignored(
            msg["source_id"], msg["node_id"], msg["ignored"]
        )
        await entry.runtime_data.coordinator.async_request_refresh()
    except ValueError as exc:
        connection.send_error(msg["id"], "invalid_format", str(exc))
        return
    except MeshMonitorPermissionError:
        connection.send_error(msg["id"], "permission_denied", "MeshMonitor token lacks nodes:write")
        return
    except MeshMonitorAuthenticationError:
        connection.send_error(msg["id"], "invalid_auth", "MeshMonitor rejected the token")
        return
    except MeshMonitorConnectionError:
        connection.send_error(msg["id"], "cannot_connect", "MeshMonitor is unreachable")
        return
    except (MeshMonitorResponseError, MeshMonitorServerError):
        connection.send_error(msg["id"], "ignore_failed", "MeshMonitor rejected the ignore change")
        return
    connection.send_result(msg["id"], {"ignored": msg["ignored"]})


@websocket_command(
    {
        vol.Required("type"): "meshmonitor/remove_node",
        vol.Required("source_id"): str,
        vol.Required("entry_id"): str,
        vol.Required("node_id"): str,
    }
)
@require_admin
@async_response
async def websocket_remove_node(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Remove one remote Meshtastic node from one exact MeshMonitor source."""
    entry = _loaded_source_entry(hass, msg["source_id"], msg["entry_id"])
    if entry is None:
        connection.send_error(msg["id"], "not_found", "MeshMonitor source not found")
        return
    if not entry.options.get(CONF_ENABLE_NODE_REMOVAL, False):
        connection.send_error(msg["id"], "node_removal_disabled", "Node removal is disabled")
        return
    if entry.data.get(CONF_SOURCE_TYPE) != SOURCE_TYPE_MESHTASTIC:
        connection.send_error(
            msg["id"], "not_supported", "Local-only node removal is not available for this protocol"
        )
        return
    snapshot = entry.runtime_data.coordinator.data
    if isinstance(snapshot, ReticulumSnapshot):
        connection.send_error(msg["id"], "not_supported", "Node removal requires Meshtastic")
        return
    node = next(
        (item for item in (snapshot.nodes if snapshot else []) if item.id == msg["node_id"]),
        None,
    )
    if node is None:
        connection.send_error(msg["id"], "not_found", "Node is no longer present")
        return
    local_id = str(snapshot.status.local_node_id).lower().removeprefix("!") if snapshot else ""
    if local_id and local_id == str(node.id).lower().removeprefix("!"):
        connection.send_error(
            msg["id"], "local_node", "The monitored source node cannot be removed"
        )
        return
    try:
        result = await entry.runtime_data.client.delete_meshtastic_node(
            msg["source_id"], msg["node_id"]
        )
    except ValueError as exc:
        connection.send_error(msg["id"], "invalid_format", str(exc))
        return
    except MeshMonitorPermissionError:
        connection.send_error(
            msg["id"], "permission_denied", "MeshMonitor token lacks messages:write"
        )
        return
    except MeshMonitorAuthenticationError:
        connection.send_error(msg["id"], "invalid_auth", "MeshMonitor rejected the token")
        return
    except MeshMonitorNotFoundError:
        connection.send_error(msg["id"], "not_found", "Node is no longer present")
        return
    except MeshMonitorConnectionError:
        connection.send_error(msg["id"], "cannot_connect", "MeshMonitor is unreachable")
        return
    except (MeshMonitorResponseError, MeshMonitorServerError):
        connection.send_error(msg["id"], "remove_failed", "MeshMonitor rejected node removal")
        return
    await entry.runtime_data.coordinator.async_request_refresh()
    connection.send_result(
        msg["id"],
        {
            "node_name": result.node_name,
            "messages_deleted": result.messages_deleted,
            "traceroutes_deleted": result.traceroutes_deleted,
            "telemetry_deleted": result.telemetry_deleted,
        },
    )


def _notification_manager(hass: HomeAssistant) -> MeshMonitorNotificationManager | None:
    manager = hass.data.get(DOMAIN, {}).get("notification_manager")
    return manager if isinstance(manager, MeshMonitorNotificationManager) else None


@websocket_command(
    {vol.Required("type"): "meshmonitor/notification_settings"}
)
@require_admin
@async_response
async def websocket_get_notification_settings(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return persistent settings and currently available HA notify targets."""
    manager = _notification_manager(hass)
    if manager is None:
        connection.send_error(msg["id"], "not_ready", "Notification settings are unavailable")
        return
    connection.send_result(msg["id"], manager.presentation())


@websocket_command(
    {
        vol.Required("type"): "meshmonitor/update_notification_settings",
        vol.Required("enabled"): bool,
        vol.Required("target"): str,
        vol.Required("scope"): vol.In(("all", "channel", "direct")),
        vol.Required("include_preview"): bool,
    }
)
@require_admin
@async_response
async def websocket_update_notification_settings(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Persist a complete notification configuration after target validation."""
    manager = _notification_manager(hass)
    if manager is None:
        connection.send_error(msg["id"], "not_ready", "Notification settings are unavailable")
        return
    try:
        result = await manager.async_update(
            {
                "enabled": msg["enabled"],
                "target": msg["target"],
                "scope": msg["scope"],
                "include_preview": msg["include_preview"],
            }
        )
    except ValueError as error:
        connection.send_error(msg["id"], "invalid_settings", str(error))
        return
    connection.send_result(msg["id"], result)


@callback
def async_register_websocket_commands(hass: HomeAssistant) -> None:
    """Register process-global panel commands."""
    websocket_api.async_register_command(hass, websocket_get_panel_data)
    websocket_api.async_register_command(hass, websocket_get_node_history)
    websocket_api.async_register_command(hass, websocket_get_position_history)
    websocket_api.async_register_command(hass, websocket_send_message)
    websocket_api.async_register_command(hass, websocket_send_meshcore_advert)
    websocket_api.async_register_command(hass, websocket_set_favorite)
    websocket_api.async_register_command(hass, websocket_request_node_action)
    websocket_api.async_register_command(hass, websocket_set_node_ignored)
    websocket_api.async_register_command(hass, websocket_remove_node)
    websocket_api.async_register_command(hass, websocket_get_notification_settings)
    websocket_api.async_register_command(hass, websocket_update_notification_settings)
