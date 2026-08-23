"""Privacy-preserving diagnostics for MeshMonitor."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.const import CONF_TOKEN, CONF_URL
from homeassistant.core import HomeAssistant

from . import MeshMonitorConfigEntry, source_runtimes
from .const import (
    CONF_SERVER_OPTIONS,
    CONF_SOURCE_ID,
    CONF_SOURCE_NAME,
    CONF_SOURCE_OPTIONS,
    CONF_SOURCES,
)
from .vendor_meshmonitor_client import ReticulumSnapshot


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: MeshMonitorConfigEntry
) -> dict[str, Any]:
    """Return aggregate diagnostics without node identity or location data."""
    del hass
    redacted_data = dict(entry.data)
    # Connection and source identifiers can expose private infrastructure or
    # mesh identity even when node records are omitted from diagnostics.
    for key in (CONF_URL, CONF_TOKEN, CONF_SOURCE_ID, CONF_SOURCE_NAME, CONF_SOURCES):
        if key in redacted_data:
            redacted_data[key] = "**REDACTED**"
    sources = []
    for source in source_runtimes(entry):
        coordinator = getattr(source, "coordinator", source.runtime_data.coordinator)
        snapshot = coordinator.data
        if isinstance(snapshot, ReticulumSnapshot):
            snapshot_data = {
                "destination_count": snapshot.status.destination_count,
                "interface_count": snapshot.status.interface_count,
                "source_connected": snapshot.status.connected,
                "optional_error_endpoints": sorted(snapshot.errors),
            }
        elif snapshot is not None:
            snapshot_data = {
                "node_count": len(snapshot.nodes),
                "source_connected": snapshot.status.connected,
                "network_available": snapshot.network is not None,
                "telemetry_record_count": len(snapshot.telemetry),
                "optional_error_endpoints": sorted(snapshot.errors),
            }
        else:
            snapshot_data = None
        sources.append(
            {
                "source_id": "**REDACTED**",
                "protocol": source.data.get("source_type", "unknown"),
                "coordinator_success": coordinator.last_update_success,
                "snapshot": snapshot_data,
            }
        )
    result = {
        "entry": redacted_data,
        "options": _redacted_options(entry.options),
        "sources": sources,
    }
    # Preserve the focused legacy helper contract until its test fixture is
    # converted; real v2 entries always expose the source list above.
    if not hasattr(entry.runtime_data, "sources") and sources:
        result["coordinator_success"] = sources[0]["coordinator_success"]
        result["snapshot"] = sources[0]["snapshot"]
        result.pop("sources")
    return result


def _redacted_options(options: Mapping[str, Any]) -> dict[str, Any]:
    """Keep safe option values while removing source-map identifiers."""
    source_options = options.get(CONF_SOURCE_OPTIONS)
    if not isinstance(source_options, Mapping):
        # Legacy flat options contain no source-map keys and remain safe.
        return dict(options)
    server_options = options.get(CONF_SERVER_OPTIONS)
    return {
        CONF_SERVER_OPTIONS: (
            dict(server_options) if isinstance(server_options, Mapping) else {}
        ),
        CONF_SOURCE_OPTIONS: [
            {"source_id": "**REDACTED**", "options": dict(value)}
            for _, value in sorted(source_options.items())
            if isinstance(value, Mapping)
        ],
    }
