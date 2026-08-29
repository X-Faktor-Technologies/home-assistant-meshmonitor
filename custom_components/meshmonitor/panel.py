"""Register the read-only MeshMonitor sidebar panel."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components.frontend import (
    async_register_built_in_panel,
)
from homeassistant.components.frontend import (
    async_remove_panel as frontend_async_remove_panel,
)
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import PANEL_URL_PATH

PANEL_STATIC_URL = "/meshmonitor_panel"
PANEL_URL = f"{PANEL_STATIC_URL}/meshmonitor-panel.js?v=20260829-0748"
PANEL_ELEMENT = "meshmonitor-panel-20260829-0748"
PANEL_PATH = str(Path(__file__).parent / "frontend")

_static_path_registered = False


async def async_register_panel(hass: HomeAssistant) -> None:
    """Serve and register the panel once per Home Assistant process."""
    global _static_path_registered
    if not _static_path_registered:
        await hass.http.async_register_static_paths(
            [StaticPathConfig(PANEL_STATIC_URL, PANEL_PATH, cache_headers=False)]
        )
        _static_path_registered = True

    async_register_built_in_panel(
        hass,
        component_name="custom",
        sidebar_title="MeshMonitor",
        sidebar_icon="mdi:radio-tower",
        frontend_url_path=PANEL_URL_PATH,
        config={
            "_panel_custom": {
                "name": PANEL_ELEMENT,
                "module_url": PANEL_URL,
            }
        },
        require_admin=False,
    )


def async_remove_panel(hass: HomeAssistant) -> None:
    """Remove only the sidebar registration; static routes are process-lived."""
    frontend_async_remove_panel(hass, PANEL_URL_PATH)
