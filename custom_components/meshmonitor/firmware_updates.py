"""Small, failure-tolerant cache of official firmware releases."""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import Any

import aiohttp

from .const import SOURCE_TYPE_MESHCORE, SOURCE_TYPE_MESHTASTIC

_LOGGER = logging.getLogger(__name__)

RELEASE_ENDPOINTS = {
    SOURCE_TYPE_MESHTASTIC: "https://api.github.com/repos/meshtastic/firmware/releases/latest",
    SOURCE_TYPE_MESHCORE: "https://api.github.com/repos/meshcore-dev/MeshCore/releases/latest",
}


def version_numbers(value: str | None) -> tuple[int, ...]:
    """Extract a comparable stable release tuple from a firmware label."""
    if not value:
        return ()
    match = re.search(r"(?<!\d)(\d+)\.(\d+)\.(\d+)(?!\d)", value)
    return tuple(int(part) for part in match.groups()) if match else ()


def update_presentation(
    protocol: str, installed: str | None, releases: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    """Return an honest comparison state; missing internet data stays unknown."""
    release = releases.get(protocol)
    installed_version = version_numbers(installed)
    latest_version = version_numbers(str(release.get("version"))) if release else ()
    if not release or not installed_version or not latest_version:
        state = "unknown"
    elif latest_version > installed_version:
        state = "available"
    else:
        state = "current"
    return {
        "state": state,
        "latest_version": release.get("version") if release else None,
        "release_url": release.get("url") if release else None,
    }


async def async_refresh_releases(
    session: aiohttp.ClientSession, cache: dict[str, dict[str, Any]]
) -> None:
    """Refresh stable release metadata without clearing known-good cache entries."""
    headers = {"Accept": "application/vnd.github+json"}
    for protocol, endpoint in RELEASE_ENDPOINTS.items():
        try:
            async with session.get(
                endpoint, headers=headers, timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                response.raise_for_status()
                payload = await response.json()
            if not isinstance(payload, Mapping):
                continue
            version = payload.get("tag_name")
            url = payload.get("html_url")
            if isinstance(version, str) and isinstance(url, str):
                cache[protocol] = {"version": version, "url": url}
        except Exception:  # noqa: BLE001 - an update lookup must never affect local health
            _LOGGER.debug(
                "Unable to refresh %s firmware release metadata", protocol, exc_info=True
            )
