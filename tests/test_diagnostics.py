"""Tests for privacy-preserving config-entry diagnostics."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest
from homeassistant.const import CONF_TOKEN, CONF_URL

from custom_components.meshmonitor.const import (
    CONF_SERVER_OPTIONS,
    CONF_SOURCE_ID,
    CONF_SOURCE_NAME,
    CONF_SOURCE_OPTIONS,
    CONF_SOURCE_TYPE,
    CONF_SOURCES,
)
from custom_components.meshmonitor.diagnostics import (
    _redacted_options,
    async_get_config_entry_diagnostics,
)


@pytest.mark.asyncio
async def test_diagnostics_redact_connection_and_source_identity() -> None:
    """Diagnostics retain useful aggregate state but no connection identity."""
    snapshot = SimpleNamespace(
        nodes=[object(), object()],
        status=SimpleNamespace(connected=True),
        network=None,
        telemetry=[object()],
        errors={"topology": "private endpoint detail"},
    )
    entry = SimpleNamespace(
        data={
            CONF_URL: "https://private-mesh.example",
            CONF_TOKEN: "secret-token",
            CONF_SOURCE_ID: "private-source-id",
            CONF_SOURCE_NAME: "Private source name",
            CONF_SOURCE_TYPE: "meshtastic",
        },
        options={"scan_interval": 60},
        runtime_data=SimpleNamespace(
            coordinator=SimpleNamespace(data=snapshot, last_update_success=True)
        ),
    )

    result = await async_get_config_entry_diagnostics(
        cast(Any, None), cast(Any, entry)
    )

    assert result["entry"] == {
        CONF_URL: "**REDACTED**",
        CONF_TOKEN: "**REDACTED**",
        CONF_SOURCE_ID: "**REDACTED**",
        CONF_SOURCE_NAME: "**REDACTED**",
        CONF_SOURCE_TYPE: "meshtastic",
    }
    assert result["snapshot"] == {
        "node_count": 2,
        "source_connected": True,
        "network_available": False,
        "telemetry_record_count": 1,
        "optional_error_endpoints": ["topology"],
    }
    assert "private endpoint detail" not in str(result)


def test_server_options_redact_source_map_keys_but_keep_safe_values() -> None:
    options = {
        CONF_SERVER_OPTIONS: {"enable_sidebar_panel": True},
        CONF_SOURCE_OPTIONS: {
            "private-source-b": {"scan_interval": 120},
            "private-source-a": {"scan_interval": 60},
        },
    }
    assert _redacted_options(options) == {
        CONF_SERVER_OPTIONS: {"enable_sidebar_panel": True},
        CONF_SOURCES: [
            {"source_id": "**REDACTED**", "options": {"scan_interval": 60}},
            {"source_id": "**REDACTED**", "options": {"scan_interval": 120}},
        ],
    }
    assert "private-source" not in str(_redacted_options(options))
