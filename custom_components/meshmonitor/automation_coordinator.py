"""Process-shared, read-only coordinator for MeshMonitor automations."""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import AUTOMATION_SCAN_INTERVAL, DOMAIN, EVENT_AUTOMATION_EXECUTED
from .vendor_meshmonitor_client import (
    AutomationDefinition,
    AutomationRun,
    MeshMonitorAuthenticationError,
    MeshMonitorClient,
    MeshMonitorConnectionError,
    MeshMonitorNotFoundError,
    MeshMonitorPermissionError,
    MeshMonitorRateLimitError,
    MeshMonitorResponseError,
    MeshMonitorServerError,
)

_LOGGER = logging.getLogger(__name__)
_MAX_DEFINITIONS = 25
_MAX_HISTORIES_PER_CYCLE = 10
_RUN_HISTORY_LIMIT = 20
_MAX_TERMINAL_IDENTITIES = 500
_CATCH_UP_WINDOW = timedelta(hours=24)
_TERMINAL_STATUSES = frozenset({"completed", "failed"})


class AutomationEndpointState(StrEnum):
    """Explicit read state; an unavailable route is not an empty collection."""

    PENDING = "pending"
    OK = "ok"
    EMPTY = "empty"
    PERMISSION_DENIED = "permission_denied"
    UNSUPPORTED = "unsupported"
    AUTHENTICATION_ERROR = "authentication_error"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class AutomationHistory:
    """One bounded history projection and its independent endpoint state."""

    automation_id: str
    state: AutomationEndpointState
    runs: tuple[AutomationRun, ...] = ()
    may_be_truncated: bool = False
    history_gap: bool = False


@dataclass(frozen=True, slots=True)
class AutomationCoordinatorData:
    """Bounded coordinator memory for future panel and event consumers."""

    list_state: AutomationEndpointState = AutomationEndpointState.PENDING
    definitions: tuple[AutomationDefinition, ...] = ()
    definitions_truncated: bool = False
    histories: tuple[AutomationHistory, ...] = ()


class MeshMonitorAutomationCoordinator(DataUpdateCoordinator[AutomationCoordinatorData]):
    """Own one global automation request budget per exact stored server URL."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: MeshMonitorClient,
        server_url: str,
        update_interval: timedelta = AUTOMATION_SCAN_INTERVAL,
    ) -> None:
        fingerprint = hashlib.sha256(server_url.encode()).hexdigest()
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_automations_{fingerprint[:12]}",
            update_interval=None,
            always_update=True,
        )
        self.client = client
        self.server_url = server_url
        self.poll_interval = update_interval
        self._round_robin_index = 0
        self._store: Store[dict[str, Any]] = Store(
            hass,
            1,
            f"{DOMAIN}.automation_cursor.{fingerprint}",
        )
        self._seen_order: list[str] = []
        self._seen: set[str] = set()
        self._baseline_complete = False
        self._baseline_observed: set[str] = set()
        self._restored_cursor = False
        self._catch_up_pending: set[str] | None = None

    async def async_initialize(self) -> Callable[[], None]:
        """Restore the ID-only cursor, then start the shared bounded polling."""
        self._restore_cursor(await self._store.async_load())
        await self.async_refresh()
        return async_track_time_interval(
            self.hass,
            self._async_interval_refresh,
            self.poll_interval,
            cancel_on_shutdown=True,
        )

    async def _async_interval_refresh(self, _now: datetime) -> None:
        await self.async_refresh()

    async def _async_update_data(self) -> AutomationCoordinatorData:
        previous = self.data or AutomationCoordinatorData()
        if self.hass.is_stopping:
            return previous

        try:
            all_definitions = await self.client.get_automations()
        except _AUTOMATION_READ_ERRORS as exc:
            return AutomationCoordinatorData(
                list_state=_state_for_exception(exc),
                definitions=previous.definitions,
                definitions_truncated=previous.definitions_truncated,
                histories=previous.histories,
            )

        definitions = tuple(
            _safe_definition(item)
            for item in sorted(all_definitions, key=lambda item: item.id)[:_MAX_DEFINITIONS]
        )
        if not definitions:
            self._round_robin_index = 0
            if not self._baseline_complete:
                self._baseline_complete = True
                await self._save_cursor()
            return AutomationCoordinatorData(list_state=AutomationEndpointState.EMPTY)

        retained_ids = {definition.id for definition in definitions}
        self._baseline_observed.intersection_update(retained_ids)
        if self._restored_cursor:
            if self._catch_up_pending is None:
                self._catch_up_pending = set(retained_ids)
            else:
                self._catch_up_pending.intersection_update(retained_ids)
        histories = {
            history.automation_id: history
            for history in previous.histories
            if history.automation_id in retained_ids
        }
        for definition in definitions:
            histories.setdefault(
                definition.id,
                AutomationHistory(definition.id, AutomationEndpointState.PENDING),
            )

        start = self._round_robin_index % len(definitions)
        count = min(len(definitions), _MAX_HISTORIES_PER_CYCLE)
        selected = [definitions[(start + offset) % len(definitions)] for offset in range(count)]
        self._round_robin_index = (start + count) % len(definitions)
        successful: list[AutomationHistory] = []

        for definition in selected:
            prior = histories[definition.id]
            try:
                received_runs = await self.client.get_automation_runs(
                    definition.id, limit=_RUN_HISTORY_LIMIT
                )
                runs = tuple(_safe_run(item) for item in received_runs[:_RUN_HISTORY_LIMIT])
            except _AUTOMATION_READ_ERRORS as exc:
                histories[definition.id] = AutomationHistory(
                    definition.id,
                    _state_for_exception(exc),
                    prior.runs,
                    prior.may_be_truncated,
                    prior.history_gap,
                )
            else:
                history = AutomationHistory(
                    definition.id,
                    AutomationEndpointState.OK if runs else AutomationEndpointState.EMPTY,
                    runs,
                    len(received_runs) >= _RUN_HISTORY_LIMIT,
                )
                histories[definition.id] = history
                successful.append(history)

        gap_ids = await self._async_process_terminal_runs(successful, retained_ids)
        for automation_id in gap_ids:
            histories[automation_id] = replace(
                histories[automation_id], history_gap=True
            )

        return AutomationCoordinatorData(
            list_state=AutomationEndpointState.OK,
            definitions=definitions,
            definitions_truncated=len(all_definitions) > _MAX_DEFINITIONS,
            histories=tuple(histories[item.id] for item in definitions),
        )

    async def _async_process_terminal_runs(
        self,
        histories: list[AutomationHistory],
        retained_ids: set[str],
    ) -> set[str]:
        """Baseline or emit eligible terminal rows without replaying unknown gaps."""
        terminal_by_history = {
            history.automation_id: [
                run for run in history.runs if run.status in _TERMINAL_STATUSES
            ]
            for history in histories
        }

        identities: dict[str, tuple[str, str]] = {}
        collision = False
        for runs in terminal_by_history.values():
            for run in runs:
                identity = _terminal_identity(run)
                pair = (run.automation_id, run.id)
                if identity in identities and identities[identity] != pair:
                    collision = True
                identities[identity] = pair

        if not self._baseline_complete:
            self._remember(identities)
            self._baseline_observed.update(terminal_by_history)
            if retained_ids.issubset(self._baseline_observed):
                self._baseline_complete = True
                await self._save_cursor()
            return set(terminal_by_history) if collision else set()

        if collision:
            # A collision makes the stored cursor ambiguous. Silently absorb the
            # bounded pages instead of risking duplicate execution events.
            self._remember(identities)
            await self._save_cursor()
            return set(terminal_by_history)

        now = datetime.now(UTC)
        gap_ids: set[str] = set()
        candidates: list[tuple[AutomationRun, datetime | None, str]] = []
        for history in histories:
            runs = terminal_by_history[history.automation_id]
            page_identities = {_terminal_identity(run): run for run in runs}
            unseen = [
                (identity, run)
                for identity, run in page_identities.items()
                if identity not in self._seen
            ]
            has_seen_terminal = any(identity in self._seen for identity in page_identities)
            catch_up = bool(
                self._catch_up_pending is not None
                and history.automation_id in self._catch_up_pending
            )
            stale_or_unprovable = any(
                (updated := _normalize_datetime(run.updated_at)) is not None
                and now - updated > _CATCH_UP_WINDOW
                or catch_up and updated is None
                for _identity, run in unseen
            )
            truncated_gap = history.may_be_truncated and not has_seen_terminal
            if stale_or_unprovable or truncated_gap:
                gap_ids.add(history.automation_id)
                self._remember(page_identities)
            else:
                candidates.extend(
                    (run, _normalize_datetime(run.updated_at), identity)
                    for identity, run in unseen
                )
            if self._catch_up_pending is not None:
                self._catch_up_pending.discard(history.automation_id)

        candidates.sort(
            key=lambda item: (
                item[1] is None,
                item[1] or datetime.max.replace(tzinfo=UTC),
                item[0].id,
                item[0].automation_id,
            )
        )
        for run, _updated, identity in candidates:
            self.hass.bus.async_fire(EVENT_AUTOMATION_EXECUTED, _event_data(run))
            self._remember((identity,))

        if candidates or gap_ids:
            await self._save_cursor()
        if self._catch_up_pending == set():
            self._catch_up_pending = None
            self._restored_cursor = False
        return gap_ids

    def _restore_cursor(self, stored: Any) -> None:
        """Accept only one complete bounded cursor; malformed data rebaselines."""
        if not isinstance(stored, dict) or stored.get("baseline_complete") is not True:
            return
        identities = stored.get("terminal_identities")
        if (
            not isinstance(identities, list)
            or len(identities) > _MAX_TERMINAL_IDENTITIES
            or any(
                not isinstance(item, str)
                or len(item) != 64
                or any(character not in "0123456789abcdef" for character in item)
                for item in identities
            )
            or len(set(identities)) != len(identities)
        ):
            return
        self._seen_order = list(identities)
        self._seen = set(identities)
        self._baseline_complete = True
        self._restored_cursor = True

    def _remember(self, identities: Any) -> None:
        for identity in identities:
            if identity in self._seen:
                continue
            self._seen.add(identity)
            self._seen_order.append(identity)
        if len(self._seen_order) > _MAX_TERMINAL_IDENTITIES:
            self._seen_order = self._seen_order[-_MAX_TERMINAL_IDENTITIES:]
            self._seen = set(self._seen_order)

    async def _save_cursor(self) -> None:
        await self._store.async_save(
            {
                "baseline_complete": True,
                "terminal_identities": self._seen_order,
            }
        )


_AUTOMATION_READ_ERRORS = (
    MeshMonitorAuthenticationError,
    MeshMonitorConnectionError,
    MeshMonitorNotFoundError,
    MeshMonitorPermissionError,
    MeshMonitorRateLimitError,
    MeshMonitorResponseError,
    MeshMonitorServerError,
)


def _state_for_exception(exc: Exception) -> AutomationEndpointState:
    if isinstance(exc, MeshMonitorPermissionError):
        return AutomationEndpointState.PERMISSION_DENIED
    if isinstance(exc, MeshMonitorNotFoundError):
        return AutomationEndpointState.UNSUPPORTED
    if isinstance(exc, MeshMonitorAuthenticationError):
        return AutomationEndpointState.AUTHENTICATION_ERROR
    return AutomationEndpointState.ERROR


def _safe_definition(item: AutomationDefinition) -> AutomationDefinition:
    """Drop the raw response so serialized configuration cannot enter HA state."""
    return AutomationDefinition(
        id=item.id,
        name=item.name,
        description=item.description,
        enabled=item.enabled,
        created_by_user_id=item.created_by_user_id,
        created_at=item.created_at,
        updated_at=item.updated_at,
        raw={},
    )


def _safe_run(item: AutomationRun) -> AutomationRun:
    """Retain stable run metadata but never serialized trigger, state, or logs."""
    return AutomationRun(
        id=item.id,
        automation_id=item.automation_id,
        source_id=item.source_id,
        status=item.status,
        started_at=item.started_at,
        updated_at=item.updated_at,
        raw={},
    )


def _terminal_identity(run: AutomationRun) -> str:
    """Persist no raw IDs while retaining an unambiguous pair identity."""
    encoded = json.dumps(
        [run.automation_id, run.id], ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(encoded.encode()).hexdigest()


def _normalize_datetime(value: int | float | str | None) -> datetime | None:
    """Parse verified numeric or ISO timestamps into UTC, rejecting ambiguity."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            numeric = float(stripped)
        except ValueError:
            try:
                parsed = datetime.fromisoformat(stripped.replace("Z", "+00:00"))
            except ValueError:
                return None
            if parsed.tzinfo is None:
                return None
            return parsed.astimezone(UTC)
    else:
        numeric = float(value)
    if abs(numeric) >= 100_000_000_000:
        numeric /= 1000
    try:
        return datetime.fromtimestamp(numeric, UTC)
    except (OverflowError, OSError, ValueError):
        return None


def _normalize_timestamp(value: int | float | str | None) -> str | None:
    parsed = _normalize_datetime(value)
    return parsed.isoformat().replace("+00:00", "Z") if parsed is not None else None


def _event_data(run: AutomationRun) -> dict[str, str | None]:
    """Return the exact six-field privacy-reviewed event projection."""
    return {
        "run_id": run.id,
        "automation_id": run.automation_id,
        "source_id": run.source_id,
        "status": run.status,
        "started_at": _normalize_timestamp(run.started_at),
        "updated_at": _normalize_timestamp(run.updated_at),
    }
