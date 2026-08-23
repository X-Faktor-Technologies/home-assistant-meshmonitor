"""Deterministic tests for bounded, read-only automation polling."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.core import HomeAssistant, callback

from custom_components.meshmonitor import _async_reconcile_shared_runtime
from custom_components.meshmonitor.automation_coordinator import (
    AutomationCoordinatorData,
    AutomationEndpointState,
    AutomationHistory,
    MeshMonitorAutomationCoordinator,
    _terminal_identity,
)
from custom_components.meshmonitor.const import DOMAIN, EVENT_AUTOMATION_EXECUTED
from custom_components.meshmonitor.vendor_meshmonitor_client import (
    AutomationDefinition,
    AutomationRun,
    MeshMonitorAuthenticationError,
    MeshMonitorConnectionError,
    MeshMonitorNotFoundError,
    MeshMonitorPermissionError,
    MeshMonitorRateLimitError,
    MeshMonitorResponseError,
    MeshMonitorServerError,
)


def _definition(automation_id: str) -> AutomationDefinition:
    return AutomationDefinition.from_dict(
        {"id": automation_id, "name": "Synthetic", "config": "private config"}
    )


def _run(
    automation_id: str,
    index: int,
    *,
    status: str = "completed",
    started_at: str | None = None,
    updated_at: str | None = None,
) -> AutomationRun:
    return AutomationRun.from_dict(
        {
            "id": f"run-{automation_id}-{index:02d}",
            "automationId": automation_id,
            "sourceId": "fictional-source",
            "status": status,
            "startedAt": started_at,
            "updatedAt": updated_at,
            "log": "private execution output",
        }
    )


async def test_empty_list_is_supported_and_skips_history(hass: HomeAssistant) -> None:
    client = Mock(
        get_automations=AsyncMock(return_value=[]),
        get_automation_runs=AsyncMock(),
    )
    coordinator = MeshMonitorAutomationCoordinator(hass, client, "http://mesh.test")

    result = await coordinator._async_update_data()

    assert result == AutomationCoordinatorData(list_state=AutomationEndpointState.EMPTY)
    client.get_automations.assert_awaited_once_with()
    client.get_automation_runs.assert_not_awaited()


@pytest.mark.parametrize(
    ("error", "state"),
    [
        (MeshMonitorPermissionError("denied"), AutomationEndpointState.PERMISSION_DENIED),
        (MeshMonitorNotFoundError("missing"), AutomationEndpointState.UNSUPPORTED),
        (
            MeshMonitorAuthenticationError("unauthorized"),
            AutomationEndpointState.AUTHENTICATION_ERROR,
        ),
        (MeshMonitorConnectionError("offline"), AutomationEndpointState.ERROR),
        (MeshMonitorRateLimitError("limited"), AutomationEndpointState.ERROR),
        (MeshMonitorResponseError("malformed"), AutomationEndpointState.ERROR),
        (MeshMonitorServerError("failed"), AutomationEndpointState.ERROR),
    ],
)
async def test_list_failures_are_explicit_and_skip_history(
    hass: HomeAssistant, error: Exception, state: AutomationEndpointState
) -> None:
    client = Mock(
        get_automations=AsyncMock(side_effect=error),
        get_automation_runs=AsyncMock(),
    )
    coordinator = MeshMonitorAutomationCoordinator(hass, client, "http://mesh.test")

    result = await coordinator._async_update_data()

    assert result.list_state is state
    assert result.definitions == ()
    client.get_automation_runs.assert_not_awaited()


async def test_caps_truncation_and_stable_round_robin(hass: HomeAssistant) -> None:
    definitions = [_definition(f"automation-{index:02d}") for index in reversed(range(30))]

    async def histories(automation_id: str, *, limit: int) -> list[AutomationRun]:
        assert limit == 20
        count = 20 if automation_id == "automation-00" else 1
        return [_run(automation_id, index) for index in range(count)]

    client = Mock(
        get_automations=AsyncMock(return_value=definitions),
        get_automation_runs=AsyncMock(side_effect=histories),
    )
    coordinator = MeshMonitorAutomationCoordinator(hass, client, "http://mesh.test")

    first = await coordinator._async_update_data()
    coordinator.data = first
    second = await coordinator._async_update_data()
    coordinator.data = second
    third = await coordinator._async_update_data()

    assert [item.id for item in first.definitions] == [
        f"automation-{index:02d}" for index in range(25)
    ]
    assert first.definitions_truncated is True
    assert first.definitions[0].raw == {}
    assert first.histories[0].runs[0].raw == {}
    assert first.histories[0].may_be_truncated is True
    assert [call.args[0] for call in client.get_automation_runs.await_args_list] == [
        *(f"automation-{index:02d}" for index in range(25)),
        *(f"automation-{index:02d}" for index in range(5)),
    ]
    assert client.get_automations.await_count == 3
    assert client.get_automation_runs.await_count == 30
    assert all(history.state is not AutomationEndpointState.PENDING for history in third.histories)


async def test_history_failures_are_independent_and_preserve_prior_data(
    hass: HomeAssistant,
) -> None:
    definitions = [_definition(f"automation-{index}") for index in range(3)]
    prior_run = _run("automation-0", 0)

    async def histories(automation_id: str, *, limit: int) -> list[AutomationRun]:
        assert limit == 20
        if automation_id == "automation-0":
            raise MeshMonitorPermissionError("denied")
        if automation_id == "automation-1":
            raise MeshMonitorNotFoundError("missing")
        return []

    client = Mock(
        get_automations=AsyncMock(return_value=definitions),
        get_automation_runs=AsyncMock(side_effect=histories),
    )
    coordinator = MeshMonitorAutomationCoordinator(hass, client, "http://mesh.test")
    coordinator.data = AutomationCoordinatorData(
        list_state=AutomationEndpointState.OK,
        definitions=tuple(definitions),
        histories=(
            AutomationHistory(
                "automation-0",
                AutomationEndpointState.OK,
                (prior_run,),
            ),
        ),
    )

    result = await coordinator._async_update_data()

    assert [history.state for history in result.histories] == [
        AutomationEndpointState.PERMISSION_DENIED,
        AutomationEndpointState.UNSUPPORTED,
        AutomationEndpointState.EMPTY,
    ]
    assert result.histories[0].runs == (prior_run,)
    assert client.get_automation_runs.await_count == 3


async def test_reconcile_owns_one_automation_timer_per_server_entry(
    hass: HomeAssistant,
) -> None:
    client = Mock(name="server_client")
    source = SimpleNamespace(
        client=client,
        source_id="source-1",
        source_name="Synthetic source",
        source_type="meshtastic",
        coordinator=Mock(),
        options={"enable_message_polling": False},
    )
    entries = [
        SimpleNamespace(
            entry_id="server-entry",
            data={"url": "http://mesh.test"},
            options={
                "server": {
                    "enable_sidebar_panel": False,
                    "enable_automation_visibility": True,
                }
            },
            runtime_data=SimpleNamespace(client=client, sources={"source-1": source}),
        ),
    ]
    unsubscribe = Mock()
    coordinator = Mock(async_initialize=AsyncMock(return_value=unsubscribe))
    factory = Mock(return_value=coordinator)
    health_unsubscribe = Mock()
    health_coordinator = Mock(
        async_initialize=AsyncMock(return_value=health_unsubscribe)
    )
    health_factory = Mock(return_value=health_coordinator)

    with (
        patch("custom_components.meshmonitor._active_entries", return_value=entries),
        patch("custom_components.meshmonitor.MeshMonitorAutomationCoordinator", factory),
        patch(
            "custom_components.meshmonitor.MeshMonitorServerHealthCoordinator",
            health_factory,
        ),
    ):
        await _async_reconcile_shared_runtime(hass)
        await _async_reconcile_shared_runtime(hass)

    factory.assert_called_once_with(hass, client, "http://mesh.test")
    health_factory.assert_called_once_with(hass, client, "server-entry")
    unsubscribe.assert_not_called()
    health_unsubscribe.assert_not_called()
    assert list(hass.data[DOMAIN]["automation_coordinators"]) == ["server-entry"]
    assert hass.data[DOMAIN]["message_coordinators"] == {}
    health_unsubscribe()


async def test_first_complete_sweep_is_silent_and_nonterminal_can_progress(
    hass: HomeAssistant,
) -> None:
    now = datetime.now(UTC)
    old = _run("automation-1", 1, updated_at=(now - timedelta(minutes=3)).isoformat())
    pending = _run("automation-1", 2, status="waiting")
    client = Mock(
        get_automations=AsyncMock(return_value=[_definition("automation-1")]),
        get_automation_runs=AsyncMock(return_value=[pending, old]),
    )
    coordinator = MeshMonitorAutomationCoordinator(hass, client, "http://mesh.test")
    save = AsyncMock()
    coordinator._store = Mock(async_save=save)
    events = []
    hass.bus.async_listen(EVENT_AUTOMATION_EXECUTED, events.append)

    coordinator.data = await coordinator._async_update_data()
    assert events == []
    save.assert_awaited_once()
    stored = save.await_args.args[0]
    assert stored["baseline_complete"] is True
    assert stored["terminal_identities"] == [_terminal_identity(old)]
    assert "automation-1" not in str(stored)

    completed = _run(
        "automation-1",
        2,
        status="failed",
        started_at="2026-08-17T04:00:00+00:00",
        updated_at=(now - timedelta(minutes=1)).isoformat(),
    )
    client.get_automation_runs.return_value = [completed, old]
    coordinator.data = await coordinator._async_update_data()
    await hass.async_block_till_done()

    assert [event.data for event in events] == [
        {
            "run_id": completed.id,
            "automation_id": "automation-1",
            "source_id": "fictional-source",
            "status": "failed",
            "started_at": "2026-08-17T04:00:00Z",
            "updated_at": completed.updated_at.replace("+00:00", "Z"),
        }
    ]

    coordinator.data = await coordinator._async_update_data()
    await hass.async_block_till_done()
    assert len(events) == 1


async def test_valid_restart_cursor_catches_up_oldest_first(hass: HomeAssistant) -> None:
    now = datetime.now(UTC)
    seen = _run("automation-1", 1, updated_at=(now - timedelta(hours=3)).isoformat())
    older = _run("automation-1", 2, updated_at=(now - timedelta(hours=2)).isoformat())
    newer = _run("automation-1", 3, updated_at=(now - timedelta(hours=1)).isoformat())
    client = Mock(
        get_automations=AsyncMock(return_value=[_definition("automation-1")]),
        get_automation_runs=AsyncMock(return_value=[newer, older, seen]),
    )
    coordinator = MeshMonitorAutomationCoordinator(hass, client, "http://mesh.test")
    coordinator._restore_cursor(
        {
            "baseline_complete": True,
            "terminal_identities": [_terminal_identity(seen)],
        }
    )
    coordinator._store = Mock(async_save=AsyncMock())
    events = []

    @callback
    def capture(event) -> None:
        events.append(event)

    hass.bus.async_listen(EVENT_AUTOMATION_EXECUTED, capture)
    await coordinator._async_update_data()
    payloads = [event.data for event in events]
    assert [payload["run_id"] for payload in payloads] == [older.id, newer.id]
    assert all(set(payload) == {
        "run_id", "automation_id", "source_id", "status", "started_at", "updated_at"
    } for payload in payloads)


async def test_truncated_unknown_prefix_is_silently_absorbed(hass: HomeAssistant) -> None:
    now = datetime.now(UTC)
    runs = [
        _run("automation-1", index, updated_at=(now - timedelta(minutes=index)).isoformat())
        for index in range(20)
    ]
    client = Mock(
        get_automations=AsyncMock(return_value=[_definition("automation-1")]),
        get_automation_runs=AsyncMock(return_value=runs),
    )
    coordinator = MeshMonitorAutomationCoordinator(hass, client, "http://mesh.test")
    unrelated = _run("automation-other", 1)
    coordinator._restore_cursor(
        {
            "baseline_complete": True,
            "terminal_identities": [_terminal_identity(unrelated)],
        }
    )
    save = AsyncMock()
    coordinator._store = Mock(async_save=save)
    events = []
    hass.bus.async_listen(EVENT_AUTOMATION_EXECUTED, events.append)

    result = await coordinator._async_update_data()
    await hass.async_block_till_done()

    assert events == []
    assert result.histories[0].may_be_truncated is True
    assert result.histories[0].history_gap is True
    assert len(save.await_args.args[0]["terminal_identities"]) == 21


@pytest.mark.parametrize("updated_at", [None, "not-a-time", "2020-01-01T00:00:00Z"])
async def test_restart_rejects_unbounded_or_unprovable_catch_up(
    hass: HomeAssistant, updated_at: str | None
) -> None:
    seen = _run("automation-1", 1)
    candidate = _run("automation-1", 2, updated_at=updated_at)
    client = Mock(
        get_automations=AsyncMock(return_value=[_definition("automation-1")]),
        get_automation_runs=AsyncMock(return_value=[candidate, seen]),
    )
    coordinator = MeshMonitorAutomationCoordinator(hass, client, "http://mesh.test")
    coordinator._restore_cursor(
        {
            "baseline_complete": True,
            "terminal_identities": [_terminal_identity(seen)],
        }
    )
    coordinator._store = Mock(async_save=AsyncMock())
    events = []
    hass.bus.async_listen(EVENT_AUTOMATION_EXECUTED, events.append)

    result = await coordinator._async_update_data()
    await hass.async_block_till_done()

    assert events == []
    assert result.histories[0].history_gap is True


async def test_invalid_cursor_rebaselines_and_cursor_is_bounded(
    hass: HomeAssistant,
) -> None:
    runs = [_run("automation-1", index) for index in range(510)]
    client = Mock(
        get_automations=AsyncMock(return_value=[_definition("automation-1")]),
        get_automation_runs=AsyncMock(return_value=runs),
    )
    coordinator = MeshMonitorAutomationCoordinator(hass, client, "http://mesh.test")
    coordinator._restore_cursor(
        {"baseline_complete": True, "terminal_identities": ["raw-run-id"]}
    )
    save = AsyncMock()
    coordinator._store = Mock(async_save=save)
    events = []
    hass.bus.async_listen(EVENT_AUTOMATION_EXECUTED, events.append)

    await coordinator._async_update_data()
    await hass.async_block_till_done()

    assert events == []
    stored = save.await_args.args[0]
    assert len(stored["terminal_identities"]) == 20
    assert all(len(identity) == 64 for identity in stored["terminal_identities"])

    coordinator._remember(f"{index:064x}" for index in range(510))
    await coordinator._save_cursor()
    bounded = save.await_args.args[0]["terminal_identities"]
    assert len(bounded) == 500
    assert bounded[-1] == f"{509:064x}"
