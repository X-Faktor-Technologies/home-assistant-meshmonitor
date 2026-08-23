"""Bounded exact-server health and cached update-check coordinator."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, SERVER_HEALTH_SCAN_INTERVAL
from .vendor_meshmonitor_client import (
    MeshMonitorAuthenticationError,
    MeshMonitorClient,
    MeshMonitorConnectionError,
    MeshMonitorNotFoundError,
    MeshMonitorPermissionError,
    MeshMonitorRateLimitError,
    MeshMonitorResponseError,
    MeshMonitorServerError,
    ServerHealth,
    VersionCheck,
)

_LOGGER = logging.getLogger(__name__)
_VERSION_CHECK_INTERVAL = timedelta(hours=6)


class ServerCheckState(StrEnum):
    """Honest outcome for one independently refreshed server check."""

    PENDING = "pending"
    OK = "ok"
    NOT_CHECKED = "not_checked"
    AUTHENTICATION_ERROR = "authentication_error"
    ERROR = "error"


ServerValue = ServerHealth | VersionCheck


@dataclass(frozen=True, slots=True)
class ServerCheck:
    """One server result, retaining older evidence only as explicitly stale."""

    state: ServerCheckState = ServerCheckState.PENDING
    value: ServerValue | None = None
    stale: bool = False
    last_success_at: datetime | None = None
    last_attempt_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ServerHealthData:
    """Exact-server evidence shared by the panel."""

    health: ServerCheck = ServerCheck()
    version: ServerCheck = ServerCheck()


class MeshMonitorServerHealthCoordinator(DataUpdateCoordinator[ServerHealthData]):
    """Own one fixed, browser-independent health timer per config entry."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: MeshMonitorClient,
        entry_id: str,
        update_interval: timedelta = SERVER_HEALTH_SCAN_INTERVAL,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_server_health_{entry_id}",
            update_interval=None,
            always_update=True,
        )
        self.client = client
        self.poll_interval = update_interval

    async def async_initialize(self) -> Callable[[], None]:
        """Read once after source setup, then use one fixed shared timer."""
        await self.async_refresh()
        return async_track_time_interval(
            self.hass,
            self._async_interval_refresh,
            self.poll_interval,
            cancel_on_shutdown=True,
        )

    async def _async_interval_refresh(self, _now: datetime) -> None:
        await self.async_refresh()

    async def _async_update_data(self) -> ServerHealthData:
        previous = self.data or ServerHealthData()
        if self.hass.is_stopping:
            return previous
        health = await _read_server_check(previous.health, self.client.get_server_health)
        now = datetime.now(UTC)
        version = previous.version
        if (
            version.last_attempt_at is None
            or now - version.last_attempt_at >= _VERSION_CHECK_INTERVAL
        ):
            version = await _read_server_check(
                previous.version,
                self.client.get_version_check,
                version_check=True,
            )
        return ServerHealthData(health=health, version=version)


async def _read_server_check[ValueT: ServerValue](
    previous: ServerCheck,
    read: Callable[[], Awaitable[ValueT]],
    *,
    version_check: bool = False,
) -> ServerCheck:
    attempted_at = datetime.now(UTC)
    try:
        value = await read()
    except MeshMonitorNotFoundError:
        return _failed_server_check(previous, ServerCheckState.NOT_CHECKED, attempted_at)
    except MeshMonitorAuthenticationError:
        return _failed_server_check(
            previous, ServerCheckState.AUTHENTICATION_ERROR, attempted_at
        )
    except (
        MeshMonitorConnectionError,
        MeshMonitorPermissionError,
        MeshMonitorRateLimitError,
        MeshMonitorResponseError,
        MeshMonitorServerError,
    ):
        return _failed_server_check(previous, ServerCheckState.ERROR, attempted_at)
    if version_check and isinstance(value, VersionCheck) and value.error:
        return _failed_server_check(previous, ServerCheckState.ERROR, attempted_at)
    return ServerCheck(
        state=ServerCheckState.OK,
        value=value,
        last_success_at=attempted_at,
        last_attempt_at=attempted_at,
    )


def _failed_server_check(
    previous: ServerCheck, state: ServerCheckState, attempted_at: datetime
) -> ServerCheck:
    return ServerCheck(
        state=state,
        value=previous.value,
        stale=previous.value is not None,
        last_success_at=previous.last_success_at,
        last_attempt_at=attempted_at,
    )
