"""Deterministic tests for source connection transition events."""

from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace

from homeassistant.core import HomeAssistant

from custom_components.meshmonitor.const import EVENT_SOURCE_CONNECTION_CHANGED
from custom_components.meshmonitor.source_connection import (
    MeshMonitorSourceConnectionRegistry,
)


class _Coordinator:
    """Minimal source-coordinator listener surface with no fetch method."""

    def __init__(self, connected: bool | None) -> None:
        self.last_update_success = True
        self.data = SimpleNamespace(status=SimpleNamespace(connected=connected))
        self._listener: Callable[[], None] | None = None

    def async_add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listener = listener

        def _unsubscribe() -> None:
            self._listener = None

        return _unsubscribe

    def notify(self) -> None:
        assert self._listener is not None
        self._listener()


async def test_strict_transitions_preserve_baseline_and_exact_payload(
    hass: HomeAssistant,
) -> None:
    registry = MeshMonitorSourceConnectionRegistry(hass)
    coordinator = _Coordinator(True)
    events = []
    hass.bus.async_listen(EVENT_SOURCE_CONNECTION_CHANGED, events.append)

    registry.register(
        "entry-1", "http://mesh.test", "source-1", "meshtastic", coordinator
    )
    await hass.async_block_till_done()
    assert events == []

    coordinator.data.status.connected = False
    coordinator.notify()
    await hass.async_block_till_done()
    assert [event.data for event in events] == [
        {
            "source_id": "source-1",
            "protocol": "meshtastic",
            "previous_connected": True,
            "connected": False,
        }
    ]

    coordinator.notify()
    coordinator.data.status.connected = None
    coordinator.notify()
    coordinator.last_update_success = False
    coordinator.data.status.connected = True
    coordinator.notify()
    await hass.async_block_till_done()
    assert len(events) == 1

    coordinator.last_update_success = True
    coordinator.notify()
    await hass.async_block_till_done()
    assert events[-1].data == {
        "source_id": "source-1",
        "protocol": "meshtastic",
        "previous_connected": False,
        "connected": True,
    }


async def test_duplicate_entries_reload_and_last_unload_lifecycle(
    hass: HomeAssistant,
) -> None:
    registry = MeshMonitorSourceConnectionRegistry(hass)
    first = _Coordinator(True)
    duplicate = _Coordinator(True)
    events = []
    hass.bus.async_listen(EVENT_SOURCE_CONNECTION_CHANGED, events.append)

    unload_first = registry.register(
        "entry-1", "http://mesh.test", "source-1", "meshtastic", first
    )
    unload_duplicate = registry.register(
        "entry-2", "http://mesh.test", "source-1", "meshtastic", duplicate
    )
    first.data.status.connected = False
    first.notify()
    duplicate.data.status.connected = False
    duplicate.notify()
    await hass.async_block_till_done()
    assert len(events) == 1

    unload_first()
    duplicate.data.status.connected = True
    duplicate.notify()
    await hass.async_block_till_done()
    assert len(events) == 2

    # Reloading one of several contributors consumes the retained shared
    # baseline, so its repeated value remains silent.
    reloaded = _Coordinator(True)
    unload_reloaded = registry.register(
        "entry-1-reloaded",
        "http://mesh.test",
        "source-1",
        "meshtastic",
        reloaded,
    )
    await hass.async_block_till_done()
    assert len(events) == 2

    unload_duplicate()
    unload_reloaded()
    after_last_unload = _Coordinator(False)
    registry.register(
        "entry-3", "http://mesh.test", "source-1", "meshtastic", after_last_unload
    )
    await hass.async_block_till_done()
    assert len(events) == 2

    after_last_unload.data.status.connected = True
    after_last_unload.notify()
    await hass.async_block_till_done()
    assert len(events) == 3
