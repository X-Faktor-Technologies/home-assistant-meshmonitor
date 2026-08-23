"""Tests for the integration-level configuration contract."""

from __future__ import annotations

from custom_components.meshmonitor import CONFIG_SCHEMA


def test_config_schema_accepts_home_assistant_configuration() -> None:
    """Confirm the integration declares its config-entry-only contract."""
    config = {"homeassistant": {"name": "Test Home"}}

    assert CONFIG_SCHEMA(config) == config
