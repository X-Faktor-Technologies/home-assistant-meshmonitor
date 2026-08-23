"""Process-shared read-only coordinator for unified mesh messages."""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    EVENT_MESSAGE_RECEIVED,
    MESSAGE_SCAN_INTERVAL,
    SOURCE_TYPE_MESHCORE,
    SOURCE_TYPE_RETICULUM,
)
from .coordinator import MeshMonitorCoordinator
from .vendor_meshmonitor_client import (
    MeshMonitorAuthenticationError,
    MeshMonitorClient,
    MeshMonitorConnectionError,
    MeshMonitorPermissionError,
    MeshMonitorRateLimitError,
    MeshMonitorResponseError,
    MeshMonitorServerError,
    UnifiedMessage,
)

_LOGGER = logging.getLogger(__name__)
_MAX_SEEN_IDS = 500


@dataclass(frozen=True, slots=True)
class MessageSource:
    """One configured source and its already-loaded channel context."""

    client: MeshMonitorClient
    source_id: str
    source_name: str | None
    source_type: str
    coordinator: MeshMonitorCoordinator
    expose_message_text: bool = False


class MeshMonitorMessageCoordinator(DataUpdateCoordinator[tuple[UnifiedMessage, ...]]):
    """Poll bounded source-scoped stored history and merge it per server."""

    def __init__(
        self,
        hass: HomeAssistant,
        sources: tuple[MessageSource, ...],
        server_url: str,
        update_interval: timedelta = MESSAGE_SCAN_INTERVAL,
    ) -> None:
        fingerprint = hashlib.sha256(server_url.encode()).hexdigest()[:12]
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_messages_{fingerprint}",
            update_interval=None,
            always_update=True,
        )
        self.sources = sources
        self.server_url = server_url
        self.poll_interval = update_interval
        self.partial_failure = False
        self._store: Store[dict[str, Any]] = Store(
            # Stable IDs changed from the unusable unified route to source-scoped
            # API records. A new cursor silently baselines existing history once.
            hass,
            1,
            f"{DOMAIN}.message_cursor_v2.{fingerprint}",
        )
        self._seen_order: list[str] = []
        self._seen: set[str] = set()
        self._baseline_complete = False

    async def async_initialize(self) -> Callable[[], None]:
        """Load ID-only restart state and begin polling."""
        stored = await self._store.async_load()
        self._baseline_complete = stored is not None
        stored = stored or {}
        ids = stored.get("seen_ids", [])
        if isinstance(ids, list):
            self._seen_order = [str(item) for item in ids[-_MAX_SEEN_IDS:]]
            self._seen = set(self._seen_order)
        unsubscribe_listener = self.async_add_listener(self._handle_update)
        await self.async_refresh()
        unsubscribe_timer = async_track_time_interval(
            self.hass,
            self._async_interval_refresh,
            self.poll_interval,
            cancel_on_shutdown=True,
        )

        def _unsubscribe() -> None:
            unsubscribe_timer()
            unsubscribe_listener()

        return _unsubscribe

    async def _async_interval_refresh(self, _now: datetime) -> None:
        """Refresh from the explicit process-shared polling timer."""
        await self.async_refresh()

    async def _async_update_data(self) -> tuple[UnifiedMessage, ...]:
        if self.hass.is_stopping:
            return self.data or ()
        messages: list[UnifiedMessage] = []
        failures = 0
        for source in self.sources:
            try:
                if source.source_type == SOURCE_TYPE_RETICULUM:
                    conversations = await source.client.get_reticulum_conversations(
                        source.source_id
                    )
                    source_messages = []
                    for conversation in conversations[:32]:
                        source_messages.extend(
                            await source.client.get_reticulum_unified_messages(
                                source.source_id,
                                source.source_name,
                                conversation.peer_hash,
                                limit=200,
                            )
                        )
                elif source.source_type == SOURCE_TYPE_MESHCORE:
                    source_messages = await source.client.get_meshcore_messages(
                        source.source_id, source_name=source.source_name, limit=200
                    )
                else:
                    source_messages = await source.client.get_meshtastic_messages(
                        source.source_id, source_name=source.source_name, limit=200
                    )
                messages.extend(_enrich_messages(source_messages, source))
            except (
                MeshMonitorAuthenticationError,
                MeshMonitorConnectionError,
                MeshMonitorPermissionError,
                MeshMonitorRateLimitError,
                MeshMonitorResponseError,
                MeshMonitorServerError,
            ):
                failures += 1
        if failures == len(self.sources) and self.sources:
            self.partial_failure = False
            raise UpdateFailed("Unable to refresh MeshMonitor messages for any source")
        self.partial_failure = failures > 0
        if failures:
            _LOGGER.warning(
                "MeshMonitor message history was unavailable for %s of %s sources",
                failures,
                len(self.sources),
            )
        return _merge_messages(messages)

    @callback
    def _handle_update(self) -> None:
        messages = self.data or ()
        if not self._baseline_complete:
            self._remember(message.id for message in messages)
            self._baseline_complete = True
            self.hass.async_create_task(self._save_seen())
            return

        new_messages = [message for message in reversed(messages) if message.id not in self._seen]
        if not new_messages:
            return
        for message in new_messages:
            self._fire_received_event(message)
        self._remember(message.id for message in new_messages)
        self.hass.async_create_task(self._save_seen())

    def _remember(self, ids: Any) -> None:
        for message_id in ids:
            if message_id in self._seen:
                continue
            self._seen.add(message_id)
            self._seen_order.append(message_id)
        if len(self._seen_order) > _MAX_SEEN_IDS:
            self._seen_order = self._seen_order[-_MAX_SEEN_IDS:]
            self._seen = set(self._seen_order)

    async def _save_seen(self) -> None:
        await self._store.async_save({"seen_ids": self._seen_order})

    def _fire_received_event(self, message: UnifiedMessage) -> None:
        local_ids = _local_node_ids(self.sources)
        sender = _normalize_id(message.from_id)
        recipient = _normalize_id(message.to_id)
        direction = (
            "outgoing"
            if sender and sender in local_ids
            else "incoming"
            if message.channel not in (None, -1) or (recipient and recipient in local_ids)
            else "unknown"
        )
        if direction == "outgoing":
            return
        data: dict[str, Any] = {
            "message_id": message.id,
            "protocol": message.protocol,
            "source_ids": [reception.source_id for reception in message.receptions],
            "source_names": _source_names(message, self.sources),
            "sender_id": message.from_id,
            "sender_name": message.from_name,
            "recipient_id": message.to_id,
            "channel": message.channel,
            "channel_name": message.channel_name,
            "is_direct": message.channel in (None, -1),
            "timestamp": message.timestamp,
            "direction": direction,
        }
        data.update(_message_mesh_context(message, self.sources))
        if _message_text_enabled(message, self.sources):
            data["text"] = message.text
        self.hass.bus.async_fire(EVENT_MESSAGE_RECEIVED, data)


def _source_names(message: UnifiedMessage, sources: tuple[MessageSource, ...]) -> list[str]:
    reception_ids = {reception.source_id for reception in message.receptions}
    return sorted(
        {
            source.source_name or source.source_id
            for source in sources
            if source.source_id in reception_ids
        },
        key=str.casefold,
    )


def _normalize_id(value: str | None) -> str:
    return (value or "").lower().removeprefix("!")


def _local_node_ids(sources: tuple[MessageSource, ...]) -> set[str]:
    """Return local identities only for this exact server coordinator."""
    result: set[str] = set()
    for source in sources:
        snapshot = source.coordinator.data
        local_id = getattr(getattr(snapshot, "status", None), "local_node_id", None)
        if local_id is None:
            local_id = getattr(getattr(snapshot, "identity", None), "destination_hash", None)
        if normalized := _normalize_id(local_id):
            result.add(normalized)
    return result


def _message_text_enabled(message: UnifiedMessage, sources: tuple[MessageSource, ...]) -> bool:
    """Apply event-text privacy only to a reception's exact server sources."""
    reception_ids = {reception.source_id for reception in message.receptions}
    return any(
        source.expose_message_text and source.source_id in reception_ids for source in sources
    )


def _message_mesh_context(
    message: UnifiedMessage, sources: tuple[MessageSource, ...]
) -> dict[str, Any]:
    """Return available sanitized RF and sender facts without raw payloads."""
    reception_ids = {reception.source_id for reception in message.receptions}
    matching_sources = [source for source in sources if source.source_id in reception_ids]
    sender_id = _normalize_id(message.from_id)
    source_nodes = [
        nodes
        for source in matching_sources
        if isinstance((nodes := source.coordinator.nodes), Mapping)
    ]
    sender_node = next(
        (
            node
            for nodes in source_nodes
            for node in nodes.values()
            if _normalize_id(node.id) == sender_id
        ),
        None,
    )
    receptions = [
        reception
        for reception in message.receptions
        if reception.source_id in {source.source_id for source in matching_sources}
    ]
    best = max(
        receptions,
        key=lambda reception: (
            reception.snr if reception.snr is not None else float("-inf"),
            reception.rssi if reception.rssi is not None else float("-inf"),
        ),
        default=None,
    )
    via_mqtt = _optional_bool(message.raw.get("viaMqtt", message.raw.get("via_mqtt")))
    packet_hops = _packet_hop_count(message.raw)
    hop_count = (
        packet_hops
        if packet_hops is not None
        else (sender_node.hops_away if sender_node is not None else None)
    )
    values: dict[str, Any] = {
        "rssi": best.rssi if best is not None else None,
        "snr": best.snr if best is not None else None,
        "hop_count": hop_count,
        "via_mqtt": via_mqtt,
        "direct_rf": (
            packet_hops == 0 and via_mqtt is not True if packet_hops is not None else None
        ),
        "sender_role": sender_node.role if sender_node is not None else None,
        "sender_hardware_model": (sender_node.hardware_model if sender_node is not None else None),
        "sender_battery_level": (sender_node.battery_level if sender_node is not None else None),
        "sender_voltage": sender_node.voltage if sender_node is not None else None,
        "sender_latitude": sender_node.latitude if sender_node is not None else None,
        "sender_longitude": sender_node.longitude if sender_node is not None else None,
        "sender_altitude": sender_node.altitude if sender_node is not None else None,
    }
    reticulum = message.raw.get("reticulum")
    if isinstance(reticulum, Mapping):
        values.update(
            {
                "delivery_state": reticulum.get("state"),
                "delivery_method": reticulum.get("method"),
                "signature_validated": reticulum.get("signatureValidated"),
                "ratcheted": reticulum.get("ratcheted"),
                "quality": reticulum.get("quality"),
            }
        )
    return {key: value for key, value in values.items() if value is not None}


def _optional_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _packet_hop_count(raw: Mapping[str, Any]) -> int | None:
    explicit = _optional_int(raw.get("hopCount", raw.get("hopsAway")))
    if explicit is not None:
        return explicit
    hop_start = _optional_int(raw.get("hopStart"))
    hop_limit = _optional_int(raw.get("hopLimit"))
    if hop_start is None or hop_limit is None or hop_limit > hop_start:
        return None
    return hop_start - hop_limit


def _enrich_messages(messages: list[UnifiedMessage], source: MessageSource) -> list[UnifiedMessage]:
    """Join source-scoped history to sanitized channel and node metadata."""
    snapshot = source.coordinator.data
    channels = {
        channel.index: channel.display_name or channel.name
        for channel in (getattr(snapshot, "channels", ()) if snapshot is not None else ())
        if channel.index is not None and (channel.display_name or channel.name)
    }
    nodes = {
        _normalize_id(node.id): node.long_name or node.short_name
        for node in (getattr(snapshot, "nodes", ()) if snapshot is not None else ())
        if node.long_name or node.short_name
    }
    return [
        replace(
            message,
            channel_name=message.channel_name or channels.get(message.channel),
            from_name=message.from_name or nodes.get(_normalize_id(message.from_id)),
        )
        for message in messages
    ]


def _merge_messages(messages: list[UnifiedMessage]) -> tuple[UnifiedMessage, ...]:
    """Merge duplicate Meshtastic receptions and retain deterministic ordering."""
    merged: dict[str, UnifiedMessage] = {}
    for message in messages:
        existing = merged.get(message.id)
        if existing is None:
            merged[message.id] = message
            continue
        receptions = {
            (reception.source_id, str(reception.timestamp)): reception
            for reception in (*existing.receptions, *message.receptions)
        }
        merged[message.id] = replace(
            existing,
            from_name=existing.from_name or message.from_name,
            channel_name=existing.channel_name or message.channel_name,
            receptions=tuple(
                receptions[key] for key in sorted(receptions, key=lambda item: (item[1], item[0]))
            ),
        )
    return tuple(
        sorted(
            merged.values(),
            key=lambda message: (_message_time(message.created_at), message.id),
            reverse=True,
        )
    )


def _message_time(value: int | float | str | None) -> float:
    if isinstance(value, bool) or value is None:
        return 0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0
