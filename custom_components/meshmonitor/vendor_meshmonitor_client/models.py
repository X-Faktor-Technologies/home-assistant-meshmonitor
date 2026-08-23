"""Typed models for stable MeshMonitor API fields.

Unknown fields are retained in ``raw`` so API additions do not break clients.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

JsonObject = dict[str, Any]


def _first(data: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in data:
            return data[name]
    return None


@dataclass(frozen=True, slots=True)
class ServerHealth:
    """Stable fields from MeshMonitor's read-only health endpoint."""

    status: str
    version: str
    uptime_ms: int | None
    database_type: str | None
    raw: Mapping[str, Any] = field(repr=False)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ServerHealth:
        return cls(
            status=_required_non_empty_str(data, "status", label="server health"),
            version=_required_non_empty_str(data, "version", label="server health"),
            uptime_ms=_as_optional_int(data.get("uptime")),
            database_type=_as_optional_str(data.get("databaseType")),
            raw=dict(data),
        )


@dataclass(frozen=True, slots=True)
class VersionCheck:
    """Cached update-check result; this model cannot initiate an update."""

    update_available: bool
    current_version: str | None
    latest_version: str | None
    release_url: str | None
    release_name: str | None
    published_at: int | float | str | None
    image_ready: bool | None
    error: str | None
    raw: Mapping[str, Any] = field(repr=False)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> VersionCheck:
        return cls(
            update_available=data.get("updateAvailable") is True,
            current_version=_as_optional_str(data.get("currentVersion")),
            latest_version=_as_optional_str(data.get("latestVersion")),
            release_url=_as_optional_str(data.get("releaseUrl")),
            release_name=_as_optional_str(data.get("releaseName")),
            published_at=data.get("publishedAt"),
            image_ready=_as_optional_bool(data.get("imageReady")),
            error=_as_optional_str(data.get("error")),
            raw=dict(data),
        )


@dataclass(frozen=True, slots=True)
class Source:
    id: str
    name: str | None
    type: str | None
    enabled: bool | None
    raw: Mapping[str, Any] = field(repr=False)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Source:
        source_id = _first(data, "id", "sourceId", "source_id")
        if source_id is None:
            raise ValueError("source response has no id")
        enabled = data.get("enabled")
        return cls(
            id=str(source_id),
            name=_as_optional_str(_first(data, "name", "displayName")),
            type=_as_optional_str(_first(data, "type", "sourceType", "protocol")),
            enabled=enabled if isinstance(enabled, bool) else None,
            raw=dict(data),
        )


@dataclass(frozen=True, slots=True)
class AutomationDefinition:
    """Read-only metadata for one global MeshMonitor automation."""

    id: str
    name: str | None
    description: str | None
    enabled: bool | None
    created_by_user_id: int | None
    created_at: int | float | str | None
    updated_at: int | float | str | None
    raw: Mapping[str, Any] = field(repr=False)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> AutomationDefinition:
        return cls(
            id=_required_non_empty_str(data, "id", label="automation definition"),
            name=_as_optional_str(data.get("name")),
            description=_as_optional_str(data.get("description")),
            enabled=data.get("enabled") if isinstance(data.get("enabled"), bool) else None,
            created_by_user_id=_as_optional_int(data.get("createdByUserId")),
            created_at=data.get("createdAt"),
            updated_at=data.get("updatedAt"),
            raw=dict(data),
        )


@dataclass(frozen=True, slots=True)
class AutomationRun:
    """Stable run metadata without projecting serialized execution content."""

    id: str
    automation_id: str
    source_id: str | None
    status: str
    started_at: int | float | str | None
    updated_at: int | float | str | None
    raw: Mapping[str, Any] = field(repr=False)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> AutomationRun:
        return cls(
            id=_required_non_empty_str(data, "id", label="automation run"),
            automation_id=_required_non_empty_str(
                data, "automationId", "automation_id", label="automation run"
            ),
            source_id=_as_optional_str(_first(data, "sourceId", "source_id")),
            status=_required_non_empty_str(data, "status", label="automation run"),
            started_at=_first(data, "startedAt", "started_at"),
            updated_at=_first(data, "updatedAt", "updated_at"),
            raw=dict(data),
        )


@dataclass(frozen=True, slots=True)
class NodeDeleteResult:
    """Counts returned after deleting one Meshtastic node locally."""

    node_num: int
    node_name: str | None
    messages_deleted: int
    traceroutes_deleted: int
    telemetry_deleted: int

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> NodeDeleteResult:
        return cls(
            node_num=_as_optional_int(data.get("nodeNum")) or 0,
            node_name=_as_optional_str(data.get("nodeName")),
            messages_deleted=_as_optional_int(data.get("messagesDeleted")) or 0,
            traceroutes_deleted=_as_optional_int(data.get("traceroutesDeleted")) or 0,
            telemetry_deleted=_as_optional_int(data.get("telemetryDeleted")) or 0,
        )


@dataclass(frozen=True, slots=True)
class Node:
    id: str
    long_name: str | None
    short_name: str | None
    last_heard: int | float | str | None
    latitude: float | None
    longitude: float | None
    altitude: float | None
    battery_level: float | None
    voltage: float | None
    channel_utilization: float | None
    air_util_tx: float | None
    snr: float | None
    rssi: float | None
    hops_away: int | None
    role: str | None
    hardware_model: str | None
    firmware_version: str | None
    mobile: bool | None
    is_favorite: bool | None
    raw: Mapping[str, Any] = field(repr=False)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Node:
        node_id = _first(data, "id", "nodeId", "node_id", "num")
        if node_id is None:
            raise ValueError("node response has no stable id")
        raw_position = data.get("position")
        position: Mapping[str, Any] = raw_position if isinstance(raw_position, Mapping) else {}
        metrics = data.get("deviceMetrics")
        if not isinstance(metrics, Mapping):
            legacy_metrics = data.get("device_metrics")
            metrics = legacy_metrics if isinstance(legacy_metrics, Mapping) else {}
        typed_metrics: Mapping[str, Any] = metrics
        return cls(
            id=str(node_id),
            long_name=_as_optional_str(_first(data, "longName", "long_name", "name")),
            short_name=_as_optional_str(_first(data, "shortName", "short_name")),
            last_heard=_first(data, "lastHeard", "last_heard", "updatedAt"),
            latitude=_as_optional_float(
                _first(data, "latitude", "lat")
                if _first(data, "latitude", "lat") is not None
                else _first(position, "latitude", "lat")
            ),
            longitude=_as_optional_float(
                _first(data, "longitude", "lon", "lng")
                if _first(data, "longitude", "lon", "lng") is not None
                else _first(position, "longitude", "lon", "lng")
            ),
            altitude=_as_optional_float(
                _first(data, "altitude", "altitudeMeters", "altitude_meters")
                if _first(data, "altitude", "altitudeMeters", "altitude_meters") is not None
                else _first(position, "altitude", "altitudeMeters", "altitude_meters")
            ),
            battery_level=_as_optional_float(
                _first(data, "batteryLevel", "battery_level")
                if _first(data, "batteryLevel", "battery_level") is not None
                else _first(typed_metrics, "batteryLevel", "battery_level")
            ),
            voltage=_as_optional_float(
                _first(data, "voltage")
                if _first(data, "voltage") is not None
                else _first(typed_metrics, "voltage")
            ),
            channel_utilization=_as_optional_float(
                _first(data, "channelUtilization", "channel_utilization")
                if _first(data, "channelUtilization", "channel_utilization") is not None
                else _first(typed_metrics, "channelUtilization", "channel_utilization")
            ),
            air_util_tx=_as_optional_float(
                _first(data, "airUtilTx", "air_util_tx")
                if _first(data, "airUtilTx", "air_util_tx") is not None
                else _first(typed_metrics, "airUtilTx", "air_util_tx")
            ),
            snr=_as_optional_float(_first(data, "snr", "rxSnr")),
            rssi=_as_optional_float(_first(data, "rssi", "rxRssi")),
            hops_away=_as_optional_int(_first(data, "hopsAway", "hops_away")),
            role=_as_optional_str(data.get("role")),
            hardware_model=_as_optional_str(_first(data, "hwModel", "hardwareModel")),
            firmware_version=_as_optional_str(_first(data, "firmwareVersion", "firmware_version")),
            mobile=data.get("mobile") if isinstance(data.get("mobile"), bool) else None,
            is_favorite=(
                _first(data, "isFavorite", "is_favorite")
                if isinstance(_first(data, "isFavorite", "is_favorite"), bool)
                else None
            ),
            raw=dict(data),
        )

    @classmethod
    def from_meshcore_dict(cls, data: Mapping[str, Any]) -> Node:
        """Adapt a protocol-specific MeshCore contact to common node fields."""
        public_key = data.get("publicKey")
        if not public_key:
            raise ValueError("MeshCore contact response has no public key")
        battery_mv = _as_optional_float(data.get("batteryMv"))
        return cls(
            id=str(public_key),
            long_name=_as_optional_str(data.get("name")),
            short_name=None,
            last_heard=_normalize_timestamp(data.get("lastHeard")),
            latitude=_as_optional_float(data.get("latitude")),
            longitude=_as_optional_float(data.get("longitude")),
            altitude=_as_optional_float(
                _first(data, "altitude", "altitudeMeters", "altitude_meters")
            ),
            battery_level=None,
            voltage=battery_mv / 1000 if battery_mv is not None else None,
            channel_utilization=None,
            air_util_tx=None,
            snr=None,
            rssi=None,
            hops_away=None,
            role=_as_optional_str(data.get("advType")),
            hardware_model=_as_optional_str(data.get("model")),
            firmware_version=_as_optional_str(_first(data, "ver", "firmwareBuild", "firmwareVer")),
            mobile=None,
            is_favorite=(
                data.get("isFavorite") if isinstance(data.get("isFavorite"), bool) else None
            ),
            raw=dict(data),
        )


@dataclass(frozen=True, slots=True)
class Channel:
    index: int | None
    name: str | None
    role: str | None
    id: str | None
    display_name: str | None
    scope: str | None
    uplink_enabled: bool | None
    downlink_enabled: bool | None
    position_precision: int | None
    has_key: bool | None
    raw: Mapping[str, Any] = field(repr=False)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Channel:
        index = _first(data, "index", "channelIndex", "channel_index")
        # MeshMonitor 4.14.1's Meshtastic channel envelope uses numeric `id`
        # for the slot while the display label lives in `displayName`.
        if index is None:
            index = data.get("id")
        return cls(
            index=_as_optional_int(index),
            name=_as_optional_str(data.get("name")),
            role=_as_optional_str(data.get("role")),
            id=_as_optional_str(data.get("id")),
            display_name=_as_optional_str(data.get("displayName")),
            scope=_as_optional_str(data.get("scope")),
            uplink_enabled=(
                data.get("uplinkEnabled") if isinstance(data.get("uplinkEnabled"), bool) else None
            ),
            downlink_enabled=(
                data.get("downlinkEnabled")
                if isinstance(data.get("downlinkEnabled"), bool)
                else None
            ),
            position_precision=_as_optional_int(data.get("positionPrecision")),
            has_key=(data.get("pskSet") if isinstance(data.get("pskSet"), bool) else None),
            raw=dict(data),
        )


@dataclass(frozen=True, slots=True)
class Capabilities:
    sources: bool = False
    status: bool = False
    nodes: bool = False
    channels: bool = False
    network: bool = False
    topology: bool = False
    telemetry: bool = False
    node_visibility_suspect: bool = False


@dataclass(frozen=True, slots=True)
class SourceStatus:
    connected: bool | None
    node_responsive: bool | None
    local_node_id: str | None
    long_name: str | None
    short_name: str | None
    raw: Mapping[str, Any] = field(repr=False)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SourceStatus:
        return cls(
            connected=data.get("connected") if isinstance(data.get("connected"), bool) else None,
            node_responsive=(
                data.get("nodeResponsive") if isinstance(data.get("nodeResponsive"), bool) else None
            ),
            local_node_id=_as_optional_str(_first(data, "localNodeId", "local_node_id")),
            long_name=_as_optional_str(_first(data, "longName", "long_name")),
            short_name=_as_optional_str(_first(data, "shortName", "short_name")),
            raw=dict(data),
        )

    @classmethod
    def from_meshcore_dict(cls, data: Mapping[str, Any]) -> SourceStatus:
        """Adapt MeshCore connection status to the common status model."""
        local_node = data.get("identity", data.get("localNode"))
        typed_local: Mapping[str, Any] = local_node if isinstance(local_node, Mapping) else {}
        connected = data.get("connected") if isinstance(data.get("connected"), bool) else None
        return cls(
            connected=connected,
            node_responsive=connected,
            local_node_id=_as_optional_str(typed_local.get("publicKey")),
            long_name=_as_optional_str(typed_local.get("name")),
            short_name=None,
            raw=dict(data),
        )


@dataclass(frozen=True, slots=True)
class NetworkSummary:
    total_nodes: int | None
    active_nodes: int | None
    traceroute_count: int | None
    last_updated: int | float | str | None
    raw: Mapping[str, Any] = field(repr=False)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> NetworkSummary:
        return cls(
            total_nodes=_as_optional_int(_first(data, "totalNodes", "total_nodes")),
            active_nodes=_as_optional_int(_first(data, "activeNodes", "active_nodes")),
            traceroute_count=_as_optional_int(_first(data, "tracerouteCount", "traceroute_count")),
            last_updated=_first(data, "lastUpdated", "last_updated"),
            raw=dict(data),
        )


@dataclass(frozen=True, slots=True)
class TopologyNode:
    node_id: str
    node_num: int | None
    long_name: str | None
    short_name: str | None
    role: str | None
    hops_away: int | None
    latitude: float | None
    longitude: float | None
    last_heard: int | float | str | None
    raw: Mapping[str, Any] = field(repr=False)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> TopologyNode:
        node_id = _first(data, "nodeId", "id", "nodeNum")
        if node_id is None:
            raise ValueError("topology node has no stable id")
        return cls(
            node_id=str(node_id),
            node_num=_as_optional_int(data.get("nodeNum")),
            long_name=_as_optional_str(data.get("longName")),
            short_name=_as_optional_str(data.get("shortName")),
            role=_as_optional_str(data.get("role")),
            hops_away=_as_optional_int(data.get("hopsAway")),
            latitude=_as_optional_float(data.get("latitude")),
            longitude=_as_optional_float(data.get("longitude")),
            last_heard=data.get("lastHeard"),
            raw=dict(data),
        )


@dataclass(frozen=True, slots=True)
class TopologyEdge:
    from_node_id: str | None
    to_node_id: str | None
    route: tuple[int | str, ...]
    snr: tuple[float, ...]
    raw: Mapping[str, Any] = field(repr=False)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> TopologyEdge:
        return cls(
            from_node_id=_as_optional_str(_first(data, "from", "fromNodeId")),
            to_node_id=_as_optional_str(_first(data, "to", "toNodeId")),
            route=_as_scalar_tuple(data.get("route")),
            snr=_as_float_tuple(_first(data, "snr", "snrTowards")),
            raw=dict(data),
        )


@dataclass(frozen=True, slots=True)
class Topology:
    nodes: tuple[TopologyNode, ...]
    edges: tuple[TopologyEdge, ...]
    raw: Mapping[str, Any] = field(repr=False)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Topology:
        raw_nodes = _mapping_sequence(data.get("nodes"))
        raw_edges = _mapping_sequence(data.get("edges"))
        return cls(
            nodes=tuple(TopologyNode.from_dict(item) for item in raw_nodes),
            edges=tuple(TopologyEdge.from_dict(item) for item in raw_edges),
            raw=dict(data),
        )


@dataclass(frozen=True, slots=True)
class NeighborLink:
    node_num: int | None
    neighbor_node_num: int | None
    node_id: str | None
    neighbor_node_id: str | None
    node_name: str | None
    neighbor_name: str | None
    snr: float | None
    reverse_snr: float | None
    last_rx_time: int | float | str | None
    timestamp: int | float | str | None
    reverse_timestamp: int | float | str | None
    bidirectional: bool | None
    transport_class: str | None
    node_latitude: float | None
    node_longitude: float | None
    neighbor_latitude: float | None
    neighbor_longitude: float | None
    raw: Mapping[str, Any] = field(repr=False)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> NeighborLink:
        return cls(
            node_num=_as_optional_int(data.get("nodeNum")),
            neighbor_node_num=_as_optional_int(data.get("neighborNodeNum")),
            node_id=_as_optional_str(data.get("nodeId")),
            neighbor_node_id=_as_optional_str(data.get("neighborNodeId")),
            node_name=_as_optional_str(data.get("nodeName")),
            neighbor_name=_as_optional_str(data.get("neighborName")),
            snr=_as_optional_float(data.get("snr")),
            reverse_snr=_as_optional_float(data.get("reverseSnr")),
            last_rx_time=data.get("lastRxTime"),
            timestamp=data.get("timestamp"),
            reverse_timestamp=data.get("reverseTimestamp"),
            bidirectional=(
                data.get("bidirectional") if isinstance(data.get("bidirectional"), bool) else None
            ),
            transport_class=_as_optional_str(data.get("transportClass")),
            node_latitude=_as_optional_float(data.get("nodeLatitude")),
            node_longitude=_as_optional_float(data.get("nodeLongitude")),
            neighbor_latitude=_as_optional_float(data.get("neighborLatitude")),
            neighbor_longitude=_as_optional_float(data.get("neighborLongitude")),
            raw=dict(data),
        )


@dataclass(frozen=True, slots=True)
class Traceroute:
    id: str | None
    from_node_num: int | None
    to_node_num: int | None
    from_node_id: str | None
    to_node_id: str | None
    route: tuple[int | str, ...]
    route_back: tuple[int | str, ...]
    snr_towards: tuple[float, ...]
    snr_back: tuple[float, ...]
    channel: int | None
    packet_id: int | None
    timestamp: int | float | str | None
    created_at: int | float | str | None
    source_id: str | None
    raw: Mapping[str, Any] = field(repr=False)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Traceroute:
        return cls(
            id=_as_optional_str(data.get("id")),
            from_node_num=_as_optional_int(data.get("fromNodeNum")),
            to_node_num=_as_optional_int(data.get("toNodeNum")),
            from_node_id=_as_optional_str(data.get("fromNodeId")),
            to_node_id=_as_optional_str(data.get("toNodeId")),
            route=_as_scalar_tuple(data.get("route")),
            route_back=_as_scalar_tuple(data.get("routeBack")),
            snr_towards=_as_float_tuple(data.get("snrTowards")),
            snr_back=_as_float_tuple(data.get("snrBack")),
            channel=_as_optional_int(data.get("channel")),
            packet_id=_as_optional_int(data.get("packetId")),
            timestamp=data.get("timestamp"),
            created_at=data.get("createdAt"),
            source_id=_as_optional_str(data.get("sourceId")),
            raw=dict(data),
        )


@dataclass(frozen=True, slots=True)
class TelemetryPoint:
    node_id: str | None
    node_num: int | None
    telemetry_type: str | None
    timestamp: int | float | str | None
    value: float | None
    unit: str | None
    created_at: int | float | str | None
    packet_timestamp: int | float | str | None
    packet_id: int | None
    channel: int | None
    precision_bits: int | None
    gps_accuracy: float | None
    rx_snr: float | None
    hop_start: int | None
    hop_limit: int | None
    raw: Mapping[str, Any] = field(repr=False)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> TelemetryPoint:
        return cls(
            node_id=_as_optional_str(data.get("nodeId")),
            node_num=_as_optional_int(data.get("nodeNum")),
            telemetry_type=_as_optional_str(_first(data, "telemetryType", "type")),
            timestamp=data.get("timestamp"),
            value=_as_optional_float(data.get("value")),
            unit=_as_optional_str(data.get("unit")),
            created_at=data.get("createdAt"),
            packet_timestamp=data.get("packetTimestamp"),
            packet_id=_as_optional_int(data.get("packetId")),
            channel=_as_optional_int(data.get("channel")),
            precision_bits=_as_optional_int(data.get("precisionBits")),
            gps_accuracy=_as_optional_float(data.get("gpsAccuracy")),
            rx_snr=_as_optional_float(data.get("rxSnr")),
            hop_start=_as_optional_int(data.get("hopStart")),
            hop_limit=_as_optional_int(data.get("hopLimit")),
            raw=dict(data),
        )


@dataclass(frozen=True, slots=True)
class LinkQualityPoint:
    timestamp: int | float | str | None
    quality: float | None
    raw: Mapping[str, Any] = field(repr=False)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> LinkQualityPoint:
        return cls(
            timestamp=data.get("timestamp"),
            quality=_as_optional_float(data.get("quality")),
            raw=dict(data),
        )


@dataclass(frozen=True, slots=True)
class PositionFix:
    timestamp: int | float | str | None
    latitude: float | None
    longitude: float | None
    altitude: float | None
    ground_speed: float | None
    ground_track: float | None
    snr: float | None
    hop_start: int | None
    hop_limit: int | None
    packet_id: int | None
    raw: Mapping[str, Any] = field(repr=False)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> PositionFix:
        return cls(
            timestamp=data.get("timestamp"),
            latitude=_as_optional_float(_first(data, "latitude", "lat")),
            longitude=_as_optional_float(_first(data, "longitude", "lon", "lng")),
            altitude=_as_optional_float(_first(data, "altitude", "alt")),
            ground_speed=_as_optional_float(data.get("groundSpeed")),
            ground_track=_as_optional_float(data.get("groundTrack")),
            snr=_as_optional_float(data.get("snr")),
            hop_start=_as_optional_int(data.get("hopStart")),
            hop_limit=_as_optional_int(data.get("hopLimit")),
            packet_id=_as_optional_int(data.get("packetId")),
            raw=dict(data),
        )


@dataclass(frozen=True, slots=True)
class PositionHistoryPage:
    fixes: tuple[PositionFix, ...]
    count: int
    total: int
    offset: int
    limit: int
    raw: Mapping[str, Any] = field(repr=False)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> PositionHistoryPage:
        fixes = tuple(PositionFix.from_dict(item) for item in _mapping_sequence(data.get("data")))
        return cls(
            fixes=fixes,
            count=_as_optional_int(data.get("count")) or 0,
            total=_as_optional_int(data.get("total")) or 0,
            offset=_as_optional_int(data.get("offset")) or 0,
            limit=_as_optional_int(data.get("limit")) or 0,
            raw=dict(data),
        )


@dataclass(frozen=True, slots=True)
class TelemetryRecord:
    id: str | None
    node_id: str | None
    telemetry_type: str | None
    value: float | None
    unit: str | None
    timestamp: int | float | str | None
    raw: Mapping[str, Any] = field(repr=False)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> TelemetryRecord:
        return cls(
            id=_as_optional_str(data.get("id")),
            node_id=_as_optional_str(_first(data, "nodeId", "node_id", "nodeNum")),
            telemetry_type=_as_optional_str(
                _first(data, "telemetryType", "telemetry_type", "type")
            ),
            value=_as_optional_float(data.get("value")),
            unit=_as_optional_str(data.get("unit")),
            timestamp=_first(data, "timestamp", "packetTimestamp", "createdAt"),
            raw=dict(data),
        )


@dataclass(frozen=True, slots=True)
class SourceSnapshot:
    source_id: str
    fetched_at: datetime
    status: SourceStatus
    nodes: tuple[Node, ...]
    network: NetworkSummary | None
    telemetry: tuple[TelemetryRecord, ...]
    errors: Mapping[str, str]
    channels: tuple[Channel, ...] = ()
    topology: Topology | None = None
    neighbors: tuple[NeighborLink, ...] = ()

    @classmethod
    def create(
        cls,
        source_id: str,
        status: SourceStatus,
        nodes: list[Node],
        network: NetworkSummary | None,
        telemetry: list[TelemetryRecord],
        errors: Mapping[str, str],
        channels: list[Channel] | None = None,
        topology: Topology | None = None,
        neighbors: list[NeighborLink] | None = None,
    ) -> SourceSnapshot:
        return cls(
            source_id=source_id,
            fetched_at=datetime.now(UTC),
            status=status,
            nodes=tuple(nodes),
            network=network,
            telemetry=tuple(telemetry),
            errors=dict(errors),
            channels=tuple(channels or ()),
            topology=topology,
            neighbors=tuple(neighbors or ()),
        )


@dataclass(frozen=True, slots=True)
class ReticulumStatus:
    """Connection and inventory summary for one Reticulum source."""

    connected: bool | None
    mode: str | None
    interface_count: int | None
    destination_count: int | None
    rns_version: str | None
    bridge_version: str | None
    raw: Mapping[str, Any] = field(repr=False)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ReticulumStatus:
        return cls(
            connected=data.get("connected") if isinstance(data.get("connected"), bool) else None,
            mode=_as_optional_str(data.get("mode")),
            interface_count=_as_optional_int(data.get("interfaceCount")),
            destination_count=_as_optional_int(data.get("destinationCount")),
            rns_version=_as_optional_str(data.get("rnsVersion")),
            bridge_version=_as_optional_str(data.get("bridgeVersion")),
            raw=dict(data),
        )


@dataclass(frozen=True, slots=True)
class ReticulumIdentity:
    """Public LXMF destination owned by the MeshMonitor bridge."""

    destination_hash: str
    display_name: str | None
    raw: Mapping[str, Any] = field(repr=False)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ReticulumIdentity:
        return cls(
            destination_hash=_required_non_empty_str(
                data, "destinationHash", label="Reticulum identity"
            ),
            display_name=_as_optional_str(data.get("displayName")),
            raw=dict(data),
        )


@dataclass(frozen=True, slots=True)
class ReticulumInterface:
    """Stored bridge observation for one RNS interface."""

    id: str | None
    name: str
    type: str | None
    interface_hash: str | None
    mode: str | None
    status: str | None
    online: bool | None
    bitrate: float | None
    tx_bytes: int | None
    rx_bytes: int | None
    last_seen_at: int | float | str | None
    frequency: float | None
    bandwidth: float | None
    spreading_factor: int | None
    coding_rate: int | None
    tx_power: float | None
    raw: Mapping[str, Any] = field(repr=False)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ReticulumInterface:
        return cls(
            id=_as_optional_str(data.get("id")),
            name=_required_non_empty_str(data, "interfaceName", label="Reticulum interface"),
            type=_as_optional_str(data.get("interfaceType")),
            interface_hash=_as_optional_str(data.get("interfaceHash")),
            mode=_as_optional_str(data.get("mode")),
            status=_as_optional_str(data.get("status")),
            online=data.get("online") if isinstance(data.get("online"), bool) else None,
            bitrate=_as_optional_float(data.get("bitrate")),
            tx_bytes=_as_optional_int(data.get("txBytes")),
            rx_bytes=_as_optional_int(data.get("rxBytes")),
            last_seen_at=data.get("lastSeenAt"),
            frequency=_as_optional_float(data.get("frequency")),
            bandwidth=_as_optional_float(data.get("bandwidth")),
            spreading_factor=_as_optional_int(data.get("spreadingFactor")),
            coding_rate=_as_optional_int(data.get("codingRate")),
            tx_power=_as_optional_float(data.get("txPower")),
            raw=dict(data),
        )


@dataclass(frozen=True, slots=True)
class ReticulumDestination:
    """Announced Reticulum destination retained by MeshMonitor."""

    destination_hash: str
    identity_hash: str | None
    app_name: str | None
    aspects: str | None
    display_name: str | None
    hops: int | None
    next_hop_interface: str | None
    rssi: float | None
    snr: float | None
    quality: float | None
    announce_count: int | None
    first_seen: int | float | str | None
    last_seen: int | float | str | None
    last_announce_at: int | float | str | None
    is_favorite: bool | None
    latitude: float | None
    longitude: float | None
    altitude: float | None
    raw: Mapping[str, Any] = field(repr=False)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ReticulumDestination:
        return cls(
            destination_hash=_required_non_empty_str(
                data, "destinationHash", label="Reticulum destination"
            ),
            identity_hash=_as_optional_str(data.get("identityHash")),
            app_name=_as_optional_str(data.get("appName")),
            aspects=_as_optional_str(data.get("aspects")),
            display_name=_as_optional_str(data.get("displayName")),
            hops=_as_optional_int(data.get("hops")),
            next_hop_interface=_as_optional_str(data.get("nextHopInterface")),
            rssi=_as_optional_float(data.get("rssi")),
            snr=_as_optional_float(data.get("snr")),
            quality=_as_optional_float(data.get("quality")),
            announce_count=_as_optional_int(data.get("announceCount")),
            first_seen=data.get("firstSeen"),
            last_seen=data.get("lastSeen"),
            last_announce_at=data.get("lastAnnounceAt"),
            is_favorite=(
                data.get("isFavorite") if isinstance(data.get("isFavorite"), bool) else None
            ),
            latitude=_as_optional_float(data.get("latitude")),
            longitude=_as_optional_float(data.get("longitude")),
            altitude=_as_optional_float(data.get("altitude")),
            raw=dict(data),
        )


@dataclass(frozen=True, slots=True)
class ReticulumMessage:
    """One stored LXMF message and its verified delivery metadata."""

    id: str
    source_id: str | None
    from_hash: str | None
    to_hash: str | None
    title: str | None
    content: str
    timestamp: int | float | str | None
    received_at: int | float | str | None
    state: str | None
    method: str | None
    signature_validated: bool | None
    ratcheted: bool | None
    reply_to_hash: str | None
    thread_hash: str | None
    rssi: float | None
    snr: float | None
    quality: float | None
    raw: Mapping[str, Any] = field(repr=False)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ReticulumMessage:
        return cls(
            id=_required_non_empty_str(data, "id", label="Reticulum message"),
            source_id=_as_optional_str(data.get("sourceId")),
            from_hash=_as_optional_str(data.get("fromHash")),
            to_hash=_as_optional_str(data.get("toHash")),
            title=_as_optional_str(data.get("title")),
            content=_as_optional_str(data.get("content")) or "",
            timestamp=data.get("timestamp"),
            received_at=data.get("receivedAt"),
            state=_as_optional_str(data.get("state")),
            method=_as_optional_str(data.get("method")),
            signature_validated=(
                data.get("signatureValidated")
                if isinstance(data.get("signatureValidated"), bool)
                else None
            ),
            ratcheted=(data.get("ratcheted") if isinstance(data.get("ratcheted"), bool) else None),
            reply_to_hash=_as_optional_str(data.get("replyToHash")),
            thread_hash=_as_optional_str(data.get("threadHash")),
            rssi=_as_optional_float(data.get("rssi")),
            snr=_as_optional_float(data.get("snr")),
            quality=_as_optional_float(data.get("quality")),
            raw=dict(data),
        )


@dataclass(frozen=True, slots=True)
class ReticulumConversation:
    """Latest-message summary for one LXMF peer."""

    peer_hash: str
    last_message: ReticulumMessage
    message_count: int
    raw: Mapping[str, Any] = field(repr=False)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ReticulumConversation:
        message = data.get("lastMessage")
        if not isinstance(message, Mapping):
            raise ValueError("Reticulum conversation has no last message")
        return cls(
            peer_hash=_required_non_empty_str(data, "peerHash", label="Reticulum conversation"),
            last_message=ReticulumMessage.from_dict(message),
            message_count=_as_optional_int(data.get("messageCount")) or 0,
            raw=dict(data),
        )


@dataclass(frozen=True, slots=True)
class ReticulumPath:
    """One observed Reticulum path; reading it never performs a probe."""

    destination_hash: str
    via_hash: str | None
    hops: int | None
    interface_name: str | None
    expires_at: int | float | str | None
    updated_at: int | float | str | None
    raw: Mapping[str, Any] = field(repr=False)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ReticulumPath:
        return cls(
            destination_hash=_required_non_empty_str(
                data, "destinationHash", label="Reticulum path"
            ),
            via_hash=_as_optional_str(data.get("viaHash")),
            hops=_as_optional_int(data.get("hops")),
            interface_name=_as_optional_str(data.get("interfaceName")),
            expires_at=data.get("expiresAt"),
            updated_at=data.get("updatedAt"),
            raw=dict(data),
        )


@dataclass(frozen=True, slots=True)
class ReticulumSnapshot:
    """Serialized read-only snapshot for one Reticulum coordinator refresh."""

    source_id: str
    fetched_at: datetime
    status: ReticulumStatus
    identity: ReticulumIdentity | None
    interfaces: tuple[ReticulumInterface, ...]
    destinations: tuple[ReticulumDestination, ...]
    conversations: tuple[ReticulumConversation, ...]
    paths: tuple[ReticulumPath, ...]
    errors: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class MessageReception:
    """One source's reception metadata for a unified message."""

    source_id: str
    source_name: str | None
    source_type: str | None
    rssi: float | None
    snr: float | None
    timestamp: int | float | str | None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> MessageReception:
        source_id = _first(data, "sourceId", "source_id")
        if source_id is None:
            raise ValueError("message reception has no source id")
        return cls(
            source_id=str(source_id),
            source_name=_as_optional_str(_first(data, "sourceName", "source_name")),
            source_type=_as_optional_str(_first(data, "sourceType", "source_type")),
            rssi=_as_optional_float(_first(data, "rxRssi", "rssi")),
            snr=_as_optional_float(_first(data, "rxSnr", "snr")),
            timestamp=_first(data, "rxTime", "timestamp"),
        )


@dataclass(frozen=True, slots=True)
class UnifiedMessage:
    """Protocol-neutral message returned by MeshMonitor's unified feed."""

    id: str
    from_id: str | None
    from_name: str | None
    to_id: str | None
    channel: int | None
    channel_name: str | None
    text: str
    timestamp: int | float | str | None
    created_at: int | float | str | None
    emoji: int | str | None
    reply_id: int | str | None
    receptions: tuple[MessageReception, ...]
    raw: Mapping[str, Any] = field(repr=False)

    @property
    def protocol(self) -> str:
        """Infer the protocol from reception source types."""
        source_types = {
            reception.source_type.lower() for reception in self.receptions if reception.source_type
        }
        if any("reticulum" in source_type for source_type in source_types):
            return "reticulum"
        if any("meshcore" in source_type for source_type in source_types):
            return "meshcore"
        return "meshtastic"

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> UnifiedMessage:
        message_id = _first(data, "dedupKey", "id", "packetId", "requestId")
        if message_id is None:
            raise ValueError("unified message has no stable id")
        raw_receptions = data.get("receptions")
        receptions = (
            tuple(
                MessageReception.from_dict(item)
                for item in raw_receptions
                if isinstance(item, Mapping)
            )
            if isinstance(raw_receptions, Sequence)
            and not isinstance(raw_receptions, (str, bytes, bytearray))
            else ()
        )
        channel = _as_optional_int(data.get("channel"))
        return cls(
            id=str(message_id),
            from_id=_as_optional_str(_first(data, "fromNodeId", "fromPublicKey", "fromNodeNum")),
            from_name=_as_optional_str(
                _first(data, "fromNodeLongName", "fromName", "fromNodeShortName")
            ),
            to_id=_as_optional_str(_first(data, "toNodeId", "toPublicKey", "toNodeNum")),
            channel=channel,
            channel_name=_as_optional_str(data.get("channelName")),
            text=_as_optional_str(data.get("text")) or "",
            timestamp=data.get("timestamp"),
            created_at=_first(data, "createdAt", "receivedAt"),
            emoji=data.get("emoji") if isinstance(data.get("emoji"), (int, str)) else None,
            reply_id=(data.get("replyId") if isinstance(data.get("replyId"), (int, str)) else None),
            receptions=receptions,
            raw=dict(data),
        )


@dataclass(frozen=True, slots=True)
class SendResult:
    """Bounded acknowledgement returned after MeshMonitor accepts a send."""

    success: bool
    message_id: str | None
    request_id: int | None
    delivery_state: str | None
    message_count: int
    raw: Mapping[str, Any] = field(repr=False)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SendResult:
        nested = data.get("data")
        result = nested if isinstance(nested, Mapping) else data
        return cls(
            success=data.get("success") is not False,
            message_id=_as_optional_str(_first(result, "messageId", "message_id")),
            request_id=_as_optional_int(_first(result, "requestId", "request_id")),
            delivery_state=_as_optional_str(_first(result, "deliveryState", "delivery_state")),
            message_count=_as_optional_int(_first(result, "messageCount", "message_count")) or 1,
            raw=dict(data),
        )


def _as_optional_str(value: Any) -> str | None:
    return str(value) if value is not None else None


def _as_optional_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _required_non_empty_str(data: Mapping[str, Any], *names: str, label: str) -> str:
    value = _first(data, *names)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} response has no valid {'/'.join(names)}")
    return value


def _as_optional_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_optional_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_timestamp(value: Any) -> int | float | str | None:
    """Normalize mixed MeshCore seconds/milliseconds and reject uptime values."""
    number = _as_optional_float(value)
    if number is None:
        return value if isinstance(value, str) else None
    if number > 100_000_000_000:
        number /= 1000
    if number < 946_684_800:  # Earlier than 2000-01-01 is not a wall-clock value.
        return None
    return int(number) if number.is_integer() else number


def _decoded_sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return ()
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _mapping_sequence(value: Any) -> tuple[Mapping[str, Any], ...]:
    return tuple(item for item in _decoded_sequence(value) if isinstance(item, Mapping))


def _as_scalar_tuple(value: Any) -> tuple[int | str, ...]:
    return tuple(
        item
        for item in _decoded_sequence(value)
        if isinstance(item, (int, str)) and not isinstance(item, bool)
    )


def _as_float_tuple(value: Any) -> tuple[float, ...]:
    return tuple(
        number
        for item in _decoded_sequence(value)
        if (number := _as_optional_float(item)) is not None
    )
