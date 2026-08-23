"""Persistent Home Assistant notification delivery for new mesh messages."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlencode

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.storage import Store

from .const import (
    DOMAIN,
    EVENT_MESSAGE_RECEIVED,
    NOTIFICATION_SCOPE_ALL,
    NOTIFICATION_SCOPE_CHANNEL,
    NOTIFICATION_SCOPE_DIRECT,
)

_LOGGER = logging.getLogger(__name__)

_STORAGE_VERSION = 1
_STORAGE_KEY = f"{DOMAIN}.notification_settings"
_VALID_SCOPES = {
    NOTIFICATION_SCOPE_ALL,
    NOTIFICATION_SCOPE_CHANNEL,
    NOTIFICATION_SCOPE_DIRECT,
}
_GENERIC_NOTIFY_ENTITIES = {
    "notify.notify",
    "notify.persistent_notification",
}


class MeshMonitorNotificationManager:
    """Own notification settings and deliver only newly received messages."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._store: Store[dict[str, Any]] = Store(
            hass, _STORAGE_VERSION, _STORAGE_KEY
        )
        self.settings = _default_settings()
        self._unsubscribe: Any = None

    async def async_initialize(self) -> None:
        """Load settings before subscribing to new-message events."""
        stored = await self._store.async_load()
        if isinstance(stored, Mapping):
            try:
                self.settings = _validated_settings(stored)
            except ValueError:
                _LOGGER.warning(
                    "Discarding notification settings that use an unsupported legacy target"
                )
                self.settings = _default_settings()
                await self._store.async_save(self.settings)
        self._unsubscribe = self.hass.bus.async_listen(
            EVENT_MESSAGE_RECEIVED, self._handle_message
        )

    async def async_shutdown(self) -> None:
        """Stop delivery during integration shutdown."""
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None

    async def async_update(self, settings: Mapping[str, Any]) -> dict[str, Any]:
        """Validate and persist a complete settings replacement."""
        updated = _validated_settings(settings)
        if updated["enabled"] and not self._target_exists(updated["target"]):
            raise ValueError("The selected Home Assistant notification target is unavailable")
        self.settings = updated
        await self._store.async_save(updated)
        return self.presentation()

    def presentation(self) -> dict[str, Any]:
        """Return settings plus dynamically discovered HA targets."""
        targets = self.targets()
        selected = self.settings["target"]
        return {
            **self.settings,
            "target_available": not selected
            or any(target["id"] == selected for target in targets),
            "targets": targets,
        }

    def targets(self) -> list[dict[str, str]]:
        """Discover useful modern Home Assistant notify entities."""
        targets: list[dict[str, str]] = [
            {
                "id": "persistent_notification",
                "label": "Persistent Notification",
                "entity_id": "Home Assistant",
                "kind": "persistent",
            }
        ]
        for state in self.hass.states.async_all("notify"):
            if state.entity_id in _GENERIC_NOTIFY_ENTITIES:
                continue
            label = state.attributes.get("friendly_name") or state.entity_id
            targets.append(
                {
                    "id": f"entity:{state.entity_id}",
                    "label": str(label),
                    "entity_id": state.entity_id,
                    "kind": "entity",
                }
            )
        return sorted(targets, key=lambda target: (target["label"].casefold(), target["id"]))

    def _target_exists(self, target: str) -> bool:
        return bool(target) and any(item["id"] == target for item in self.targets())

    @callback
    def _handle_message(self, event: Event) -> None:
        """Schedule one backend notification for an eligible incoming event."""
        data = event.data
        if not self.settings["enabled"] or data.get("direction") != "incoming":
            return
        is_direct = bool(data.get("is_direct"))
        scope = self.settings["scope"]
        if scope == NOTIFICATION_SCOPE_DIRECT and not is_direct:
            return
        if scope == NOTIFICATION_SCOPE_CHANNEL and is_direct:
            return
        self.hass.async_create_task(
            self._async_deliver(data), "MeshMonitor incoming message notification"
        )

    async def _async_deliver(self, data: Mapping[str, Any]) -> None:
        target = self.settings["target"]
        if not self._target_exists(target):
            _LOGGER.warning("MeshMonitor notification target is no longer available")
            return

        sender = str(data.get("sender_name") or data.get("sender_id") or "Unknown sender")
        is_direct = bool(data.get("is_direct"))
        channel_name = str(
            data.get("channel_name") or f"Channel {data.get('channel', '?')}"
        )
        title = (
            f"Direct message from {sender}"
            if is_direct
            else f"New message in {channel_name}"
        )
        protocol_value = str(data.get("protocol") or "mesh")
        protocol = "MeshCore" if protocol_value.lower() == "meshcore" else protocol_value.title()
        source_names = data.get("source_names")
        metadata = protocol
        if isinstance(source_names, list) and source_names:
            metadata = f"{protocol} via {', '.join(str(name) for name in source_names[:3])}"
        body = metadata if is_direct else f"{sender}\n{metadata}"
        text = data.get("text")
        if self.settings["include_preview"] and isinstance(text, str) and text.strip():
            preview = " ".join(text.split())[:160]
            body = (
                f"{preview}\n{metadata}"
                if is_direct
                else f"{sender}: {preview}\n{metadata}"
            )
        message_url = _message_url(data)

        try:
            if target == "persistent_notification":
                await self.hass.services.async_call(
                    "persistent_notification",
                    "create",
                    {
                        "title": title,
                        "message": f"{body}\n\n[Open message]({message_url})",
                    },
                    blocking=False,
                )
                return
            _kind, value = target.split(":", 1)
            await self.hass.services.async_call(
                "notify",
                "send_message",
                {
                    "title": title,
                    "message": body,
                    "data": {"url": message_url, "clickAction": message_url},
                },
                target={"entity_id": value},
                blocking=False,
            )
        except Exception:  # Home Assistant owns target-specific service schemas.
            _LOGGER.exception("MeshMonitor notification delivery failed")


def _message_url(data: Mapping[str, Any]) -> str:
    """Build a local panel deep link without exposing server details or credentials."""
    protocol = str(data.get("protocol") or "mesh").lower()
    if data.get("is_direct"):
        peer = str(data.get("sender_id") or "unknown")
        conversation = f"direct:{protocol}:{peer}"
    else:
        conversation = f"channel:{protocol}:{data.get('channel', '?')}"
    query = urlencode(
        {
            "tab": "messages",
            "conversation": conversation,
            "message": str(data.get("message_id") or ""),
        }
    )
    return f"/meshmonitor?{query}"


def _default_settings() -> dict[str, Any]:
    return {
        "enabled": False,
        "target": "",
        "scope": NOTIFICATION_SCOPE_ALL,
        "include_preview": False,
    }


def _validated_settings(value: Mapping[str, Any]) -> dict[str, Any]:
    scope = str(value.get("scope", NOTIFICATION_SCOPE_ALL))
    if scope not in _VALID_SCOPES:
        raise ValueError("Invalid notification scope")
    target = str(value.get("target", ""))
    if target and target != "persistent_notification" and not target.startswith(
        "entity:notify."
    ):
        raise ValueError("Invalid notification target")
    return {
        "enabled": bool(value.get("enabled", False)),
        "target": target,
        "scope": scope,
        "include_preview": bool(value.get("include_preview", False)),
    }
