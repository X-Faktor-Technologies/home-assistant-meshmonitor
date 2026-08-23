"""Derive bounded node events from an existing source coordinator."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.core import HomeAssistant, callback

from .const import (
    EVENT_NODE_DISCOVERED,
    EVENT_NODE_UPDATED,
    EVENT_POSITION_UPDATED,
    EVENT_TELEMETRY_RECEIVED,
)
from .coordinator import MeshMonitorCoordinator
from .vendor_meshmonitor_client import Node, ReticulumSnapshot, SourceSnapshot, TelemetryRecord

_NODE_INFO_FIELDS = (
    "long_name",
    "short_name",
    "role",
    "hardware_model",
    "firmware_version",
    "mobile",
    "is_favorite",
)
_MAX_TELEMETRY_KEYS = 500


class MeshMonitorNodeEventMonitor:
    """Emit sanitized events only for changes after the loaded baseline."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: MeshMonitorCoordinator,
        source_name: str,
        source_type: str,
    ) -> None:
        self._hass = hass
        self._coordinator = coordinator
        self._source_name = source_name
        self._source_type = source_type
        self._nodes: dict[str, Node] = {}
        self._telemetry_order: list[str] = []
        self._telemetry_seen: set[str] = set()

    def async_initialize(self) -> Callable[[], None]:
        """Baseline the current snapshot and listen for later refreshes."""
        self._baseline(self._coordinator.data)
        return self._coordinator.async_add_listener(self._handle_update)

    def _baseline(self, snapshot: SourceSnapshot | ReticulumSnapshot | None) -> None:
        if snapshot is None or isinstance(snapshot, ReticulumSnapshot):
            return
        self._nodes = {node.id: node for node in snapshot.nodes}
        for record in snapshot.telemetry:
            self._remember_telemetry(_telemetry_key(record))

    @callback
    def _handle_update(self) -> None:
        snapshot = self._coordinator.data
        if snapshot is None or isinstance(snapshot, ReticulumSnapshot):
            return
        current = {node.id: node for node in snapshot.nodes}
        for node_id, node in current.items():
            previous = self._nodes.get(node_id)
            if previous is None:
                self._fire(EVENT_NODE_DISCOVERED, _node_payload(node))
                continue
            changed = [
                field
                for field in _NODE_INFO_FIELDS
                if getattr(previous, field) != getattr(node, field)
            ]
            if changed:
                self._fire(
                    EVENT_NODE_UPDATED,
                    {**_node_payload(node), "changed_fields": changed},
                )
            if _position(previous) != _position(node) and _has_position(node):
                self._fire(EVENT_POSITION_UPDATED, _node_payload(node))

        for record in snapshot.telemetry:
            key = _telemetry_key(record)
            if key in self._telemetry_seen:
                continue
            self._remember_telemetry(key)
            self._fire(EVENT_TELEMETRY_RECEIVED, _telemetry_payload(record, current))
        self._nodes = current

    def _remember_telemetry(self, key: str) -> None:
        if key in self._telemetry_seen:
            return
        self._telemetry_seen.add(key)
        self._telemetry_order.append(key)
        if len(self._telemetry_order) > _MAX_TELEMETRY_KEYS:
            expired = self._telemetry_order.pop(0)
            self._telemetry_seen.discard(expired)

    def _fire(self, event_type: str, data: dict[str, Any]) -> None:
        self._hass.bus.async_fire(
            event_type,
            {
                "source_id": self._coordinator.source_id,
                "source_name": self._source_name,
                "protocol": self._source_type,
                **data,
            },
        )


def _node_payload(node: Node) -> dict[str, Any]:
    values: dict[str, Any] = {
        "node_id": node.id,
        "node_name": node.long_name or node.short_name,
        "short_name": node.short_name,
        "role": node.role,
        "hardware_model": node.hardware_model,
        "firmware_version": node.firmware_version,
        "battery_level": node.battery_level,
        "voltage": node.voltage,
        "rssi": node.rssi,
        "snr": node.snr,
        "hop_count": node.hops_away,
        "latitude": node.latitude,
        "longitude": node.longitude,
        "altitude": node.altitude,
        "is_favorite": node.is_favorite,
    }
    return {key: value for key, value in values.items() if value is not None}


def _telemetry_payload(
    record: TelemetryRecord, nodes: dict[str, Node]
) -> dict[str, Any]:
    node = nodes.get(record.node_id or "")
    values: dict[str, Any] = {
        "telemetry_id": record.id,
        "node_id": record.node_id,
        "node_name": (
            node.long_name or node.short_name if node is not None else None
        ),
        "metric": record.telemetry_type,
        "value": record.value,
        "unit": record.unit,
        "timestamp": record.timestamp,
    }
    return {key: value for key, value in values.items() if value is not None}


def _telemetry_key(record: TelemetryRecord) -> str:
    if record.id:
        return f"id:{record.id}"
    return "|".join(
        str(value)
        for value in (
            record.node_id,
            record.telemetry_type,
            record.timestamp,
            record.value,
            record.unit,
        )
    )


def _position(node: Node) -> tuple[float | None, float | None, float | None]:
    return node.latitude, node.longitude, node.altitude


def _has_position(node: Node) -> bool:
    return node.latitude is not None and node.longitude is not None
