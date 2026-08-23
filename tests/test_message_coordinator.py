"""Native Home Assistant tests for read-only message processing."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.meshmonitor.const import EVENT_MESSAGE_RECEIVED
from custom_components.meshmonitor.message_coordinator import (
    MeshMonitorMessageCoordinator,
    MessageSource,
)
from custom_components.meshmonitor.vendor_meshmonitor_client import (
    MeshMonitorConnectionError,
    UnifiedMessage,
)


def _message(message_id: str, text: str = "private body") -> UnifiedMessage:
    return UnifiedMessage.from_dict(
        {
            "dedupKey": message_id,
            "fromNodeId": "remote-node",
            "fromNodeLongName": "Remote",
            "toNodeId": "^all",
            "channel": 0,
            "channelName": "Public",
            "text": text,
            "timestamp": 1_770_000_000_000,
            "createdAt": 1_770_000_000_100,
            "receptions": [
                {
                    "sourceId": "source-1",
                    "sourceType": "meshtastic_tcp",
                }
            ],
        }
    )


async def test_initial_messages_are_baselined_without_replay(hass: HomeAssistant) -> None:
    coordinator = MeshMonitorMessageCoordinator(hass, (), "http://mesh.test")
    coordinator._store = Mock(async_save=AsyncMock())
    events = []
    hass.bus.async_listen(EVENT_MESSAGE_RECEIVED, events.append)
    coordinator.data = (_message("old"),)

    coordinator._handle_update()
    await hass.async_block_till_done()

    assert events == []
    coordinator.data = (_message("new"), _message("old"))
    coordinator._handle_update()
    await hass.async_block_till_done()
    assert len(events) == 1
    assert events[0].data["message_id"] == "new"
    assert events[0].data["direction"] == "incoming"
    assert events[0].data["source_names"] == []
    assert "text" not in events[0].data


async def test_restart_cursor_persists_only_ids(hass: HomeAssistant) -> None:
    coordinator = MeshMonitorMessageCoordinator(hass, (), "http://mesh.test")
    save = AsyncMock()
    coordinator._store = Mock(async_save=save)
    coordinator._remember(["message-1", "message-2"])

    await coordinator._save_seen()

    save.assert_awaited_once_with({"seen_ids": ["message-1", "message-2"]})


async def test_message_text_privacy_is_scoped_to_matching_server_source(
    hass: HomeAssistant,
) -> None:
    context = Mock(data=Mock(channels=[], nodes=[]))
    sources = (
        MessageSource(Mock(), "source-1", "One", "meshtastic", context, False),
        MessageSource(Mock(), "source-2", "Two", "meshtastic", context, True),
    )
    coordinator = MeshMonitorMessageCoordinator(hass, sources, "http://mesh.test")
    events = []
    hass.bus.async_listen(EVENT_MESSAGE_RECEIVED, events.append)

    coordinator._fire_received_event(_message("private-source-1"))
    await hass.async_block_till_done()
    assert "text" not in events[-1].data

    enabled = UnifiedMessage.from_dict(
        {
            "dedupKey": "private-source-2",
            "fromNodeId": "remote-node",
            "toNodeId": "^all",
            "channel": 0,
            "text": "private body",
            "receptions": [{"sourceId": "source-2", "sourceType": "meshtastic"}],
        }
    )
    coordinator._fire_received_event(enabled)
    await hass.async_block_till_done()
    assert events[-1].data["text"] == "private body"
    assert events[-1].data["source_names"] == ["Two"]


async def test_received_message_includes_available_sanitized_mesh_context(
    hass: HomeAssistant,
) -> None:
    node = SimpleNamespace(
        id="remote-node",
        role="ROUTER",
        hardware_model="HELTEC_V4",
        battery_level=76,
        voltage=4.1,
        latitude=25.1,
        longitude=-80.2,
        altitude=12,
        hops_away=0,
    )
    source = MessageSource(
        Mock(),
        "source-1",
        "One",
        "meshtastic",
        Mock(nodes={"remote-node": node}, data=Mock(status=Mock(local_node_id="local"))),
    )
    coordinator = MeshMonitorMessageCoordinator(hass, (source,), "http://mesh.test")
    events = []
    hass.bus.async_listen(EVENT_MESSAGE_RECEIVED, events.append)
    message = UnifiedMessage.from_dict(
        {
            "dedupKey": "rich",
            "fromNodeId": "remote-node",
            "toNodeId": "local",
            "viaMqtt": False,
            "hopCount": 0,
            "receptions": [
                {
                    "sourceId": "source-1",
                    "sourceType": "meshtastic",
                    "rxRssi": -93,
                    "rxSnr": 7.5,
                }
            ],
        }
    )

    coordinator._fire_received_event(message)
    await hass.async_block_till_done()

    data = events[0].data
    assert data["rssi"] == -93
    assert data["snr"] == 7.5
    assert data["hop_count"] == 0
    assert data["via_mqtt"] is False
    assert data["direct_rf"] is True
    assert data["sender_role"] == "ROUTER"
    assert data["sender_hardware_model"] == "HELTEC_V4"
    assert data["sender_battery_level"] == 76
    assert data["sender_latitude"] == 25.1
    assert "raw" not in data


async def test_message_poll_interval_is_configurable(hass: HomeAssistant) -> None:
    coordinator = MeshMonitorMessageCoordinator(
        hass, (), "http://mesh.test", timedelta(seconds=75)
    )

    assert coordinator.poll_interval == timedelta(seconds=75)
    assert coordinator.update_interval is None


async def test_source_histories_are_enriched_merged_and_ordered(
    hass: HomeAssistant,
) -> None:
    first = replace(
        _message("mt:remote-node:p100", "synthetic one"),
        channel_name=None,
        from_name=None,
    )
    second = _message("mt:remote-node:p101", "synthetic two")
    second = second.__class__.from_dict(
        {
            "dedupKey": second.id,
            "fromNodeId": "remote-node",
            "toNodeId": "^all",
            "channel": 0,
            "text": second.text,
            "timestamp": 1_770_000_001_000,
            "createdAt": 1_770_000_001_100,
            "receptions": [
                {"sourceId": "source-1", "sourceType": "meshtastic"}
            ],
        }
    )
    meshtastic = Mock()
    meshtastic.get_meshtastic_messages = AsyncMock(return_value=[first, second])
    meshcore = Mock()
    meshcore.get_meshcore_messages = AsyncMock(return_value=[])
    snapshot = Mock()
    # Matches MeshMonitor 4.14.1: numeric channel slot in `id`, empty `name`,
    # and the human label in `displayName` after typed normalization.
    snapshot.channels = [
        SimpleNamespace(index=0, name="", display_name="Primary")
    ]
    snapshot.nodes = [
        SimpleNamespace(
            id="remote-node", long_name="Synthetic sender", short_name=None
        )
    ]
    sources = (
        MessageSource(
            meshtastic,
            "source-1",
            "Synthetic Meshtastic",
            "meshtastic",
            Mock(data=snapshot),
        ),
        MessageSource(
            meshcore,
            "meshcore-1",
            "Synthetic MeshCore",
            "meshcore",
            Mock(data=Mock(channels=[], nodes=[])),
        ),
    )
    coordinator = MeshMonitorMessageCoordinator(hass, sources, "http://mesh.test")

    result = await coordinator._async_update_data()

    assert [message.id for message in result] == [second.id, first.id]
    assert all(message.channel_name == "Primary" for message in result)
    assert all(message.from_name == "Synthetic sender" for message in result)
    meshtastic.get_meshtastic_messages.assert_awaited_once_with(
        "source-1", source_name="Synthetic Meshtastic", limit=200
    )
    meshcore.get_meshcore_messages.assert_awaited_once_with(
        "meshcore-1", source_name="Synthetic MeshCore", limit=200
    )


async def test_duplicate_meshtastic_receptions_collapse_to_one_message(
    hass: HomeAssistant,
) -> None:
    left = _message("mt:remote-node:p100")
    right = UnifiedMessage.from_dict(
        {
            "dedupKey": left.id,
            "fromNodeId": "remote-node",
            "toNodeId": "^all",
            "channel": 0,
            "text": "private body",
            "timestamp": 1_770_000_000_000,
            "createdAt": 1_770_000_000_100,
            "receptions": [
                {"sourceId": "source-2", "sourceType": "meshtastic"}
            ],
        }
    )
    sources = []
    for source_id, message in (("source-1", left), ("source-2", right)):
        client = Mock()
        client.get_meshtastic_messages = AsyncMock(return_value=[message])
        sources.append(
            MessageSource(
                client,
                source_id,
                source_id,
                "meshtastic",
                Mock(data=Mock(channels=[], nodes=[])),
            )
        )
    coordinator = MeshMonitorMessageCoordinator(
        hass, tuple(sources), "http://mesh.test"
    )

    result = await coordinator._async_update_data()

    assert len(result) == 1
    assert [reception.source_id for reception in result[0].receptions] == [
        "source-1",
        "source-2",
    ]


async def test_history_failures_distinguish_partial_from_total(
    hass: HomeAssistant,
) -> None:
    good = Mock()
    good.get_meshtastic_messages = AsyncMock(return_value=[])
    failed = Mock()
    failed.get_meshtastic_messages = AsyncMock(
        side_effect=MeshMonitorConnectionError("offline")
    )
    context = Mock(data=Mock(channels=[], nodes=[]))
    sources = (
        MessageSource(good, "source-1", "One", "meshtastic", context),
        MessageSource(failed, "source-2", "Two", "meshtastic", context),
    )
    coordinator = MeshMonitorMessageCoordinator(hass, sources, "http://mesh.test")

    assert await coordinator._async_update_data() == ()
    assert coordinator.partial_failure is True

    all_failed = MeshMonitorMessageCoordinator(
        hass, (sources[1],), "http://mesh.test"
    )
    with pytest.raises(UpdateFailed, match="any source"):
        await all_failed._async_update_data()
