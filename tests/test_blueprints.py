"""Validate the importable MeshMonitor automation blueprints."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from homeassistant.components.automation.config import (
    AUTOMATION_BLUEPRINT_SCHEMA,
    PLATFORM_SCHEMA,
)
from homeassistant.components.blueprint.models import Blueprint, BlueprintInputs
from homeassistant.util.yaml import load_yaml_dict

BLUEPRINT_DIR = (
    Path(__file__).parents[1] / "blueprints" / "automation" / "meshmonitor"
)

SAMPLE_INPUTS: dict[str, dict[str, Any]] = {
    "channel-bridge.yaml": {
        "incoming_source": "source-a",
        "incoming_channel": 0,
        "outgoing_source": "source-b",
        "outgoing_channel": 1,
        "marker": "[HA bridge]",
    },
    "automation-failure-to-mobile-notification.yaml": {
        "source_device": "source-device",
        "notify_device": "mobile-device",
    },
    "channel-message-to-mobile-notification.yaml": {
        "source_device": "source-device",
        "channel": 0,
        "notify_device": "mobile-device",
    },
    "direct-message-to-tts.yaml": {
        "source_device": "source-device",
        "tts_entity": "tts.home_assistant_cloud",
        "media_player": "media_player.kitchen",
    },
    "direct-message-responder.yaml": {
        "source_device": "source-device",
        "command": "ping",
        "response": "pong",
    },
    "entity-alert-to-mesh.yaml": {
        "monitored_entity": "binary_sensor.alert",
        "target_state": "on",
        "source_device": "source-device",
        "delivery": "direct",
        "recipient": "!12345678",
        "channel": 0,
        "message": "Alert",
    },
    "low-battery-to-mesh.yaml": {
        "battery_entity": "sensor.test_battery",
        "threshold": 20,
        "source_device": "source-device",
        "channel": 0,
    },
    "new-node-welcome.yaml": {
        "source_device": "source-device",
        "message": "Welcome",
    },
    "range-test-responder.yaml": {
        "source_device": "source-device",
        "command": "range",
    },
    "source-outage-to-mobile-notification.yaml": {
        "source_device": "source-device",
        "outage_duration": {"hours": 0, "minutes": 2, "seconds": 0},
        "notify_device": "mobile-device",
    },
    "weather-alert-to-mesh.yaml": {
        "alert_entity": "binary_sensor.weather_alert",
        "active_state": "on",
        "source_device": "source-device",
        "channel": 0,
    },
    "zone-exit-to-mesh.yaml": {
        "tracker": "device_tracker.test",
        "zone": "zone.home",
        "source_device": "source-device",
        "channel": 0,
    },
}


@pytest.mark.parametrize("path", sorted(BLUEPRINT_DIR.glob("*.yaml")))
def test_blueprint_loads_substitutes_and_validates(path: Path) -> None:
    """Exercise Home Assistant's real blueprint and automation schemas."""
    data = load_yaml_dict(path)
    blueprint = Blueprint(
        data,
        path=path.name,
        expected_domain="automation",
        schema=AUTOMATION_BLUEPRINT_SCHEMA,
    )
    inputs = BlueprintInputs(
        blueprint,
        {
            "use_blueprint": {
                "path": f"meshmonitor/{path.name}",
                "input": SAMPLE_INPUTS[path.name],
            }
        },
    )

    inputs.validate()
    PLATFORM_SCHEMA(inputs.async_substitute())
    assert blueprint.validate() is None


def test_message_blueprints_warn_about_content_retention() -> None:
    """Keep the privacy consequence visible in both message recipes."""
    for filename in (
        "channel-bridge.yaml",
        "channel-message-to-mobile-notification.yaml",
        "direct-message-responder.yaml",
        "direct-message-to-tts.yaml",
        "range-test-responder.yaml",
    ):
        description = load_yaml_dict(BLUEPRINT_DIR / filename)["blueprint"][
            "description"
        ]
        assert "automation traces" in description
        if filename in (
            "channel-message-to-mobile-notification.yaml",
            "direct-message-to-tts.yaml",
        ):
            assert "Expose message text in events" in description


def test_outbound_blueprint_does_not_retry_radio_actions() -> None:
    """One entity transition must produce at most one radio action."""
    data = load_yaml_dict(BLUEPRINT_DIR / "entity-alert-to-mesh.yaml")
    rendered = str(data["actions"])

    assert rendered.count("meshmonitor.send_direct_message") == 1
    assert rendered.count("meshmonitor.send_channel_message") == 1
    assert "repeat" not in rendered
    assert data["mode"] == "queued"
    assert data["max"] == 3
