"""Tests for node events derived from existing source snapshots."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import Mock

from homeassistant.core import HomeAssistant

from custom_components.meshmonitor.const import (
    EVENT_NODE_DISCOVERED,
    EVENT_NODE_UPDATED,
    EVENT_POSITION_UPDATED,
    EVENT_TELEMETRY_RECEIVED,
)
from custom_components.meshmonitor.node_event_monitor import MeshMonitorNodeEventMonitor
from custom_components.meshmonitor.vendor_meshmonitor_client import (
    Node,
    SourceSnapshot,
    TelemetryRecord,
)


def _node(node_id: str = "!1234abcd", **changes: object) -> Node:
    values = {
        "id": node_id,
        "longName": "Remote Alpha",
        "shortName": "ALFA",
        "role": "CLIENT",
        "hwModel": "HELTEC_V4",
        "latitude": 25.1,
        "longitude": -80.2,
        "altitude": 12,
        "batteryLevel": 81,
    }
    values.update(changes)
    return Node.from_dict(values)


def _snapshot(
    nodes: tuple[Node, ...], telemetry: tuple[TelemetryRecord, ...] = ()
) -> SourceSnapshot:
    return SourceSnapshot(
        source_id="source-a",
        fetched_at=datetime.now(UTC),
        status=Mock(),
        nodes=nodes,
        network=None,
        telemetry=telemetry,
        errors={},
    )


async def test_baseline_is_silent_and_later_changes_are_distinct(
    hass: HomeAssistant,
) -> None:
    initial_record = TelemetryRecord.from_dict(
        {"id": "old", "nodeId": "!1234abcd", "type": "battery", "value": 81}
    )
    coordinator = Mock(source_id="source-a")
    coordinator.data = _snapshot((_node(),), (initial_record,))
    listener = None

    def add_listener(callback):  # type: ignore[no-untyped-def]
        nonlocal listener
        listener = callback
        return Mock()

    coordinator.async_add_listener.side_effect = add_listener
    events = []
    for event_type in (
        EVENT_NODE_DISCOVERED,
        EVENT_NODE_UPDATED,
        EVENT_POSITION_UPDATED,
        EVENT_TELEMETRY_RECEIVED,
    ):
        hass.bus.async_listen(event_type, events.append)
    MeshMonitorNodeEventMonitor(
        hass, coordinator, "Source A", "meshtastic"
    ).async_initialize()
    assert events == []

    changed = replace(_node(), role="ROUTER", latitude=26.0)
    new_record = TelemetryRecord.from_dict(
        {
            "id": "new",
            "nodeId": "!1234abcd",
            "type": "battery",
            "value": 80,
            "unit": "%",
        }
    )
    coordinator.data = _snapshot((changed, _node("!feedbeef")), (initial_record, new_record))
    assert listener is not None
    listener()
    await hass.async_block_till_done()

    by_type = {event.event_type: event for event in events}
    assert set(by_type) == {
        EVENT_NODE_UPDATED,
        EVENT_POSITION_UPDATED,
        EVENT_NODE_DISCOVERED,
        EVENT_TELEMETRY_RECEIVED,
    }
    assert by_type[EVENT_NODE_UPDATED].data["changed_fields"] == ["role"]
    assert by_type[EVENT_POSITION_UPDATED].data["latitude"] == 26.0
    assert by_type[EVENT_TELEMETRY_RECEIVED].data["metric"] == "battery"
    assert all(event.data["source_id"] == "source-a" for event in events)
    assert all("raw" not in event.data for event in events)
