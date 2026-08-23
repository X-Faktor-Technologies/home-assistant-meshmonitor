"""Process-shared source connection transition tracking."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field

from homeassistant.core import HomeAssistant, callback

from .const import EVENT_SOURCE_CONNECTION_CHANGED
from .coordinator import MeshMonitorCoordinator


@dataclass(slots=True)
class _ConnectionState:
    """One shared baseline for duplicate entries observing the same source."""

    source_id: str
    protocol: str
    contributors: set[str] = field(default_factory=set)
    connected: bool | None = None


class MeshMonitorSourceConnectionRegistry:
    """Emit strict API-reported connection transitions without extra reads."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._states: dict[tuple[str, str], _ConnectionState] = {}
        self._entry_keys: dict[str, tuple[str, str]] = {}

    @callback
    def register(
        self,
        entry_id: str,
        server_url: str,
        source_id: str,
        protocol: str,
        coordinator: MeshMonitorCoordinator,
    ) -> Callable[[], None]:
        """Register one loaded entry and observe its existing coordinator only."""
        server_fingerprint = hashlib.sha256(server_url.encode()).hexdigest()
        key = (server_fingerprint, source_id)
        state = self._states.setdefault(
            key,
            _ConnectionState(source_id=source_id, protocol=protocol),
        )
        state.contributors.add(entry_id)
        self._entry_keys[entry_id] = key

        @callback
        def _handle_update() -> None:
            self._handle_update(key, coordinator)

        unsubscribe_listener = coordinator.async_add_listener(_handle_update)
        # Entry setup has already completed its first source refresh. Consume
        # that in-memory result as a silent baseline rather than adding a read.
        _handle_update()
        removed = False

        @callback
        def _unsubscribe() -> None:
            nonlocal removed
            if removed:
                return
            removed = True
            unsubscribe_listener()
            if self._entry_keys.pop(entry_id, None) != key:
                return
            current = self._states.get(key)
            if current is None:
                return
            current.contributors.discard(entry_id)
            if not current.contributors:
                self._states.pop(key, None)

        return _unsubscribe

    @callback
    def _handle_update(
        self,
        key: tuple[str, str],
        coordinator: MeshMonitorCoordinator,
    ) -> None:
        """Compare only explicit booleans from successful source refreshes."""
        state = self._states.get(key)
        if state is None or not coordinator.last_update_success:
            return
        snapshot = coordinator.data
        connected = getattr(getattr(snapshot, "status", None), "connected", None)
        if not isinstance(connected, bool):
            return
        if state.connected is None:
            state.connected = connected
            return
        if connected == state.connected:
            return

        previous = state.connected
        state.connected = connected
        self._hass.bus.async_fire(
            EVENT_SOURCE_CONNECTION_CHANGED,
            {
                "source_id": state.source_id,
                "protocol": state.protocol,
                "previous_connected": previous,
                "connected": connected,
            },
        )
