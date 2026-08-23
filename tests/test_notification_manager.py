"""Backend notification settings and delivery regression tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.core import HomeAssistant, ServiceCall

from custom_components.meshmonitor.const import EVENT_MESSAGE_RECEIVED
from custom_components.meshmonitor.notification_manager import (
    MeshMonitorNotificationManager,
)


@pytest.fixture
def manager(hass: HomeAssistant) -> MeshMonitorNotificationManager:
    notification_manager = MeshMonitorNotificationManager(hass)
    notification_manager._store = Mock(
        async_load=AsyncMock(return_value=None), async_save=AsyncMock()
    )
    return notification_manager


async def test_targets_are_discovered_and_settings_persist(
    hass: HomeAssistant, manager: MeshMonitorNotificationManager
) -> None:
    hass.states.async_set("notify.eliers_phone", "unknown", {"friendly_name": "Elier's phone"})
    hass.states.async_set("notify.notify", "unknown", {"friendly_name": "Notify"})
    hass.states.async_set(
        "notify.persistent_notification",
        "unknown",
        {"friendly_name": "Persistent Notification"},
    )
    hass.services.async_register("notify", "mobile_app_tablet", Mock())

    presentation = await manager.async_update(
        {
            "enabled": True,
            "target": "entity:notify.eliers_phone",
            "scope": "direct",
            "include_preview": True,
        }
    )

    assert presentation["target_available"] is True
    assert presentation["targets"] == [
        {
            "id": "entity:notify.eliers_phone",
            "label": "Elier's phone",
            "entity_id": "notify.eliers_phone",
            "kind": "entity",
        },
        {
            "id": "persistent_notification",
            "label": "Persistent Notification",
            "entity_id": "Home Assistant",
            "kind": "persistent",
        }
    ]
    manager._store.async_save.assert_awaited_once_with(
        {
            "enabled": True,
            "target": "entity:notify.eliers_phone",
            "scope": "direct",
            "include_preview": True,
        }
    )


async def test_unavailable_target_cannot_be_enabled(
    manager: MeshMonitorNotificationManager,
) -> None:
    with pytest.raises(ValueError, match="unavailable"):
        await manager.async_update(
            {
                "enabled": True,
                "target": "entity:notify.missing",
                "scope": "all",
                "include_preview": False,
            }
        )


async def test_saved_settings_are_restored_before_event_listener_starts(
    hass: HomeAssistant, manager: MeshMonitorNotificationManager
) -> None:
    manager._store.async_load.return_value = {
        "enabled": True,
        "target": "entity:notify.mobile_app_phone",
        "scope": "channel",
        "include_preview": False,
    }

    await manager.async_initialize()

    assert manager.settings == {
        "enabled": True,
        "target": "entity:notify.mobile_app_phone",
        "scope": "channel",
        "include_preview": False,
    }


async def test_legacy_service_target_is_safely_disabled_on_load(
    hass: HomeAssistant, manager: MeshMonitorNotificationManager
) -> None:
    manager._store.async_load.return_value = {
        "enabled": True,
        "target": "service:mobile_app_phone",
        "scope": "channel",
        "include_preview": True,
    }

    await manager.async_initialize()

    assert manager.settings == {
        "enabled": False,
        "target": "",
        "scope": "all",
        "include_preview": False,
    }
    manager._store.async_save.assert_awaited_once_with(manager.settings)


async def test_backend_delivery_filters_scope_and_uses_modern_notify_entity(
    hass: HomeAssistant, manager: MeshMonitorNotificationManager
) -> None:
    hass.states.async_set("notify.eliers_phone", "unknown")
    manager.settings = {
        "enabled": True,
        "target": "entity:notify.eliers_phone",
        "scope": "direct",
        "include_preview": True,
    }
    await manager.async_initialize()

    event = {
        "direction": "incoming",
        "is_direct": True,
        "sender_name": "Remote node",
        "sender_id": "!abc123",
        "message_id": "message-42",
        "protocol": "meshtastic",
        "source_names": ["Attic source"],
        "text": "A private synthetic message",
    }
    calls: list[ServiceCall] = []
    hass.services.async_register("notify", "send_message", calls.append)
    hass.bus.async_fire(EVENT_MESSAGE_RECEIVED, event)
    await hass.async_block_till_done()

    assert len(calls) == 1
    assert calls[0].data == {
        "title": "Direct message from Remote node",
        "message": "A private synthetic message\nMeshtastic via Attic source",
        "data": {
            "url": (
                "/meshmonitor?tab=messages&conversation="
                "direct%3Ameshtastic%3A%21abc123&message=message-42"
            ),
            "clickAction": (
                "/meshmonitor?tab=messages&conversation="
                "direct%3Ameshtastic%3A%21abc123&message=message-42"
            ),
        },
        "entity_id": "notify.eliers_phone",
    }


async def test_backend_delivery_supports_home_assistant_persistent_notification(
    hass: HomeAssistant, manager: MeshMonitorNotificationManager
) -> None:
    manager.settings = {
        "enabled": True,
        "target": "persistent_notification",
        "scope": "all",
        "include_preview": False,
    }
    await manager.async_initialize()

    calls: list[ServiceCall] = []
    hass.services.async_register("persistent_notification", "create", calls.append)
    hass.bus.async_fire(
        EVENT_MESSAGE_RECEIVED,
        {
            "direction": "incoming",
            "is_direct": False,
            "sender_name": "Remote node",
            "message_id": "channel-message-7",
            "channel_name": "Public",
            "channel": 0,
            "protocol": "meshcore",
        },
    )
    await hass.async_block_till_done()

    assert len(calls) == 1
    assert calls[0].data == {
        "title": "New message in Public",
        "message": (
            "Remote node\nMeshCore\n\n"
            "[Open message](/meshmonitor?tab=messages&conversation="
            "channel%3Ameshcore%3A0&message=channel-message-7)"
        ),
    }


async def test_outgoing_replay_and_wrong_scope_never_notify(
    hass: HomeAssistant, manager: MeshMonitorNotificationManager
) -> None:
    hass.states.async_set("notify.mobile_app_phone", "unknown")
    manager.settings = {
        "enabled": True,
        "target": "entity:notify.mobile_app_phone",
        "scope": "channel",
        "include_preview": False,
    }
    await manager.async_initialize()

    calls: list[ServiceCall] = []
    hass.services.async_register("notify", "send_message", calls.append)
    hass.bus.async_fire(
        EVENT_MESSAGE_RECEIVED,
        {"direction": "outgoing", "is_direct": False},
    )
    hass.bus.async_fire(
        EVENT_MESSAGE_RECEIVED,
        {"direction": "incoming", "is_direct": True},
    )
    await hass.async_block_till_done()

    assert calls == []
