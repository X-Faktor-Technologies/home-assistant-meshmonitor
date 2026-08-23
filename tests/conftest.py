"""Home Assistant custom-component test support."""

from __future__ import annotations

import sys
from collections.abc import Generator
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

pytest_plugins = ["pytest_homeassistant_custom_component"]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Allow Home Assistant to load the local integration in native flow tests."""


@pytest.fixture(autouse=True)
def block_firmware_release_network() -> Generator[None]:
    """Keep the test suite deterministic and free of external release checks."""
    with (
        patch("custom_components.meshmonitor.async_refresh_releases", new=AsyncMock()),
        patch("custom_components.meshmonitor.async_get_clientsession", return_value=Mock()),
    ):
        yield
