"""Deterministic exact-server health and update-check tests."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock

from homeassistant.core import HomeAssistant

from custom_components.meshmonitor.server_health_coordinator import (
    MeshMonitorServerHealthCoordinator,
    ServerCheckState,
)
from custom_components.meshmonitor.vendor_meshmonitor_client import (
    MeshMonitorConnectionError,
    MeshMonitorNotFoundError,
    ServerHealth,
    VersionCheck,
)


def _health() -> ServerHealth:
    return ServerHealth.from_dict(
        {
            "status": "ok",
            "version": "4.14.1",
            "uptime": 86_400_000,
            "databaseType": "sqlite",
        }
    )


def _version() -> VersionCheck:
    return VersionCheck.from_dict(
        {
            "updateAvailable": True,
            "currentVersion": "4.14.1",
            "latestVersion": "4.14.2",
            "releaseUrl": "https://github.com/Yeraze/meshmonitor/releases/tag/v4.14.2",
        }
    )


async def test_server_checks_are_serialized(hass: HomeAssistant) -> None:
    client = Mock(
        get_server_health=AsyncMock(return_value=_health()),
        get_version_check=AsyncMock(return_value=_version()),
    )
    coordinator = MeshMonitorServerHealthCoordinator(hass, client, "entry-1")

    result = await coordinator._async_update_data()

    assert result.health.state is ServerCheckState.OK
    assert result.version.state is ServerCheckState.OK
    assert result.health.value == _health()
    assert result.version.value == _version()
    client.get_server_health.assert_awaited_once_with()
    client.get_version_check.assert_awaited_once_with()


async def test_version_endpoint_is_cached_for_six_hours(hass: HomeAssistant) -> None:
    client = Mock(
        get_server_health=AsyncMock(return_value=_health()),
        get_version_check=AsyncMock(return_value=_version()),
    )
    coordinator = MeshMonitorServerHealthCoordinator(hass, client, "entry-1")
    coordinator.data = await coordinator._async_update_data()

    await coordinator._async_update_data()

    assert client.get_server_health.await_count == 2
    client.get_version_check.assert_awaited_once_with()


async def test_failures_retain_only_explicit_stale_evidence(
    hass: HomeAssistant,
) -> None:
    client = Mock(
        get_server_health=AsyncMock(return_value=_health()),
        get_version_check=AsyncMock(return_value=_version()),
    )
    coordinator = MeshMonitorServerHealthCoordinator(hass, client, "entry-1")
    coordinator.data = await coordinator._async_update_data()
    coordinator.data = replace(
        coordinator.data,
        version=replace(
            coordinator.data.version,
            last_attempt_at=datetime.now(UTC) - timedelta(hours=7),
        ),
    )
    client.get_server_health.side_effect = MeshMonitorConnectionError("offline")
    client.get_version_check.side_effect = MeshMonitorNotFoundError("disabled")

    result = await coordinator._async_update_data()

    assert result.health.state is ServerCheckState.ERROR
    assert result.health.stale is True
    assert result.version.state is ServerCheckState.NOT_CHECKED
    assert result.version.stale is True


async def test_error_shaped_version_result_is_not_current(
    hass: HomeAssistant,
) -> None:
    client = Mock(
        get_server_health=AsyncMock(return_value=_health()),
        get_version_check=AsyncMock(
            return_value=VersionCheck.from_dict(
                {"updateAvailable": False, "error": "Unable to check for updates"}
            )
        ),
    )
    coordinator = MeshMonitorServerHealthCoordinator(hass, client, "entry-1")

    result = await coordinator._async_update_data()

    assert result.version.state is ServerCheckState.ERROR
    assert result.version.value is None
