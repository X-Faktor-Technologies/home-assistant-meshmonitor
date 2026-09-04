"""Native Home Assistant contract tests for the panel API."""
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from custom_components import meshmonitor as meshmonitor_integration
from custom_components.meshmonitor.automation_coordinator import (
    AutomationCoordinatorData,
    AutomationEndpointState,
    AutomationHistory,
)
from custom_components.meshmonitor.const import (
    CONF_ENABLE_FAVORITES,
    CONF_ENABLE_NODE_MANAGEMENT,
    CONF_ENABLE_TRANSMIT,
    CONF_NODE_DEVICE_POLICY,
    CONF_SERVER_OPTIONS,
    CONF_SOURCE_OPTIONS,
    CONF_SOURCE_TYPE,
    NODE_DEVICE_POLICY_FAVORITES,
)
from custom_components.meshmonitor.server_health_coordinator import (
    ServerCheck,
    ServerCheckState,
)
from custom_components.meshmonitor.vendor_meshmonitor_client import (
    AutomationDefinition,
    AutomationRun,
    NeighborLink,
    Node,
    ReticulumDestination,
    ReticulumIdentity,
    ReticulumSnapshot,
    ReticulumStatus,
    ServerHealth,
    SourceSnapshot,
    SourceStatus,
    Topology,
    UnifiedMessage,
    VersionCheck,
)
from custom_components.meshmonitor.vendor_meshmonitor_client.client import (
    MeshMonitorClient,
    _validate_message_text,
)
from custom_components.meshmonitor.vendor_meshmonitor_client.exceptions import (
    MeshMonitorResponseError,
)
from custom_components.meshmonitor.websocket_api import (
    _loaded_source_entry,
    _meshmonitor_links,
    _message_poll_state,
    _safe_release_url,
    _serialize_automation_groups,
    _serialize_entry,
    _serialize_message,
    _serialize_server_check,
    _snapshot_local_message_id,
    websocket_get_node_history,
    websocket_get_position_history,
    websocket_remove_node,
    websocket_request_node_action,
    websocket_send_message,
    websocket_set_favorite,
    websocket_set_node_ignored,
)


def test_server_version_serialization_is_allowlisted() -> None:
    checked_at = datetime(2026, 8, 20, 22, 0, tzinfo=UTC)
    result = _serialize_server_check(
        ServerCheck(
            state=ServerCheckState.OK,
            value=VersionCheck.from_dict(
                {
                    "updateAvailable": True,
                    "currentVersion": "4.14.1",
                    "latestVersion": "4.14.2",
                    "releaseUrl": (
                        "https://github.com/Yeraze/meshmonitor/releases/tag/v4.14.2"
                        "?secret=drop"
                    ),
                    "private": "drop",
                }
            ),
            last_success_at=checked_at,
            last_attempt_at=checked_at,
        ),
        "version",
    )

    assert result["value"] == {
        "update_available": True,
        "current_version": "4.14.1",
        "latest_version": "4.14.2",
        "release_url": "https://github.com/Yeraze/meshmonitor/releases/tag/v4.14.2",
        "release_name": None,
        "published_at": None,
        "image_ready": None,
    }
    assert "private" not in result["value"]


def test_server_health_serialization_has_no_raw_fields() -> None:
    result = _serialize_server_check(
        ServerCheck(
            state=ServerCheckState.OK,
            value=ServerHealth.from_dict(
                {
                    "status": "ok",
                    "version": "4.14.1",
                    "uptime": 1000,
                    "databaseType": "sqlite",
                    "private": "drop",
                }
            ),
        ),
        "health",
    )

    assert result["value"] == {
        "status": "ok",
        "version": "4.14.1",
        "uptime_ms": 1000,
        "database_type": "sqlite",
    }


def test_release_links_are_restricted_to_meshmonitor_releases() -> None:
    assert _safe_release_url("https://evil.invalid/release") is None
    assert _safe_release_url("http://github.com/Yeraze/meshmonitor/releases/tag/v1") is None
    assert (
        _safe_release_url("https://github.com/Yeraze/meshmonitor/releases/tag/v1?token=x")
        == "https://github.com/Yeraze/meshmonitor/releases/tag/v1"
    )


def test_outbound_message_uses_local_identity_without_splitting_direct_thread() -> None:
    message = UnifiedMessage.from_dict(
        {
            "dedupKey": "outbound-1",
            "fromNodeId": "!da539a4c",
            "fromNodeLongName": "Synthetic Meshtastic",
            "toNodeId": "!da5af204",
            "channel": -1,
            "text": "reply test direct from meshmonitor",
            "timestamp": 1_777_000_000_000,
            "receptions": [
                {"sourceId": "source-1", "sourceType": "meshtastic_tcp"}
            ],
        }
    )

    payload = _serialize_message(message, "entry-1", {"da539a4c"})

    assert payload["outgoing"] is True
    assert payload["direction"] == "outbound"
    assert payload["from_id"] == "!da539a4c"
    assert payload["to_id"] == "!da5af204"


def test_reticulum_identity_classifies_outbound_lxmf_history() -> None:
    snapshot = SimpleNamespace(
        status=SimpleNamespace(local_node_id=None),
        identity=SimpleNamespace(
            destination_hash="20914cb776e9d9e60418354ea6986238"
        ),
    )
    message = UnifiedMessage.from_dict(
        {
            "dedupKey": "rns:source-rns:outbound-1",
            "fromNodeId": "20914cb776e9d9e60418354ea6986238",
            "toNodeId": "0123456789abcdef0123456789abcdef",
            "channel": -1,
            "text": "Synthetic LXMF send",
            "timestamp": 1_777_000_000_000,
            "receptions": [{"sourceId": "source-rns", "sourceType": "reticulum"}],
        }
    )

    local_id = _snapshot_local_message_id(snapshot)
    payload = _serialize_message(message, "entry-rns", {local_id} if local_id else set())

    assert payload["outgoing"] is True
    assert payload["direction"] == "outbound"


@pytest.mark.asyncio
async def test_component_setup_keeps_panel_and_websocket_available_offline() -> None:
    hass = Mock()
    hass.data = {}
    hass.config_entries.async_entries.return_value = [SimpleNamespace(options={})]
    register_panel = AsyncMock()
    notification_manager = Mock(async_initialize=AsyncMock())

    with (
        patch.object(meshmonitor_integration, "async_register_panel", register_panel),
        patch.object(
            meshmonitor_integration, "async_register_websocket_commands"
        ) as register_websocket,
        patch.object(
            meshmonitor_integration,
            "MeshMonitorNotificationManager",
            return_value=notification_manager,
        ),
    ):
        assert await meshmonitor_integration.async_setup(hass, {})

    register_websocket.assert_called_once_with(hass)
    register_panel.assert_awaited_once_with(hass)
    notification_manager.async_initialize.assert_awaited_once_with()
    assert hass.data["meshmonitor"]["websocket_registered"] is True
    assert hass.data["meshmonitor"]["panel_registered"] is True


def test_loaded_source_resolution_requires_server_when_ids_collide() -> None:
    first_source = SimpleNamespace(
        entry_id="server-a", data={"source_id": "same-source"}
    )
    second_source = SimpleNamespace(
        entry_id="server-b", data={"source_id": "same-source"}
    )
    entries = [
        SimpleNamespace(runtime_data=SimpleNamespace(sources={"same-source": first_source})),
        SimpleNamespace(runtime_data=SimpleNamespace(sources={"same-source": second_source})),
    ]
    hass = Mock()
    hass.config_entries.async_loaded_entries.return_value = entries

    assert _loaded_source_entry(hass, "same-source") is None
    assert _loaded_source_entry(hass, "same-source", "server-a") is first_source
    assert _loaded_source_entry(hass, "same-source", "server-b") is second_source


@pytest.mark.parametrize(
    ("runtime", "expected"),
    [
        (None, "disabled"),
        (Mock(partial_failure=False, last_update_success=True, data=()), "ready"),
        (Mock(partial_failure=True, last_update_success=True, data=()), "partial"),
        (Mock(partial_failure=False, last_update_success=False, data=None), "error"),
        (Mock(partial_failure=False, last_update_success=False, data=()), "stale"),
    ],
)
def test_message_poll_state_is_honest(runtime: Mock | None, expected: str) -> None:
    runtimes = [] if runtime is None else [{"coordinator": runtime}]

    assert _message_poll_state(runtimes) == expected


def test_automation_panel_projection_is_bounded_sanitized_and_source_labeled() -> None:
    definition = AutomationDefinition.from_dict(
        {
            "id": "automation-fictional",
            "name": "Synthetic nightly check",
            "description": "Read-only synthetic description",
            "enabled": True,
            "createdByUserId": 99,
            "createdAt": "2026-08-16T01:00:00Z",
            "updatedAt": "2026-08-17T01:00:00Z",
            "config": {"secret": "must-not-leak"},
        }
    )
    run = AutomationRun.from_dict(
        {
            "id": "run-fictional",
            "automationId": definition.id,
            "sourceId": "source-fictional",
            "status": "failed",
            "startedAt": "2026-08-17T01:01:00Z",
            "updatedAt": "2026-08-17T01:02:00Z",
            "log": "must-not-leak",
        }
    )
    data = AutomationCoordinatorData(
        list_state=AutomationEndpointState.ERROR,
        definitions=(definition,),
        definitions_truncated=True,
        histories=(
            AutomationHistory(
                definition.id,
                AutomationEndpointState.PERMISSION_DENIED,
                (run,),
                may_be_truncated=True,
                history_gap=True,
            ),
        ),
    )
    entry = Mock()
    entry.entry_id = "entry-fictional"
    entry.title = "Synthetic source"
    entry.data = {
        "url": "https://credential@mesh.invalid/private?token=secret",
        "source_id": "source-fictional",
        "source_name": "Synthetic source",
    }
    hass = Mock()
    hass.data = {
        "meshmonitor": {
            "automation_coordinators": {
                entry.data["url"]: {
                    "coordinator": SimpleNamespace(data=data),
                }
            }
        }
    }

    payload = _serialize_automation_groups(hass, [entry, entry])

    assert payload == [
        {
            "state": "error",
            "entry_ids": ["entry-fictional"],
            "definitions_truncated": True,
            "automations": [
                {
                    "id": "automation-fictional",
                    "name": "Synthetic nightly check",
                    "description": "Read-only synthetic description",
                    "enabled": True,
                    "created_at": "2026-08-16T01:00:00Z",
                    "updated_at": "2026-08-17T01:00:00Z",
                    "history": {
                        "state": "permission_denied",
                        "may_be_truncated": True,
                        "history_gap": True,
                        "runs": [
                            {
                                "id": "run-fictional",
                                "source_id": "source-fictional",
                                "status": "failed",
                                "started_at": "2026-08-17T01:01:00Z",
                                "updated_at": "2026-08-17T01:02:00Z",
                            }
                        ],
                    },
                }
            ],
            "sources": [
                {"id": "source-fictional", "name": "Synthetic source"}
            ],
        }
    ]
    rendered = repr(payload)
    assert "must-not-leak" not in rendered
    assert "created_by" not in rendered
    assert "mesh.invalid" not in rendered
    assert "credential" not in rendered


def test_automation_panel_projection_is_disabled_without_shared_runtime() -> None:
    hass = Mock()
    hass.data = {"meshmonitor": {}}

    assert _serialize_automation_groups(hass, []) == []


def test_panel_payload_is_bounded_and_contains_no_credentials() -> None:
    """The browser receives typed display data, never entry credentials/raw data."""
    node = Node.from_dict(
        {
            "id": "42",
            "longName": "Test Node",
            "latitude": 27.9,
            "longitude": -82.5,
            "altitude": 14.25,
            "hideFromMap": True,
            "secret": "must-not-leak",
        }
    )
    snapshot = SourceSnapshot(
        source_id="source-1",
        fetched_at=datetime(2026, 8, 15, tzinfo=UTC),
        status=SourceStatus.from_dict({"connected": True}),
        nodes=(node,),
        network=None,
        telemetry=(),
        errors={},
        topology=Topology.from_dict(
            {
                "nodes": [{"id": "42", "nodeNum": 42, "latitude": 27.9, "longitude": -82.5}],
                "edges": [
                    {
                        "from": "42",
                        "to": "43",
                        "route": [42, 43],
                        "snr": [8.25],
                        "secret": "must-not-leak",
                    }
                ],
            }
        ),
        neighbors=(
            NeighborLink.from_dict(
                {
                    "nodeId": "42",
                    "neighborNodeId": "43",
                    "snr": 7.5,
                    "reverseSnr": 6.25,
                    "nodeLatitude": 27.9,
                    "nodeLongitude": -82.5,
                    "neighborLatitude": 28.0,
                    "neighborLongitude": -82.6,
                    "apiToken": "must-not-leak",
                }
            ),
        ),
    )
    entry = Mock()
    entry.entry_id = "entry-1"
    entry.title = "Test Source"
    entry.data = {
        "source_id": "source-1",
        "source_name": "Test Source",
        "source_type": "meshtastic",
        "url": "http://meshmonitor.invalid",
        "token": "must-not-leak",
    }
    entry.runtime_data = SimpleNamespace(
        coordinator=SimpleNamespace(data=snapshot, last_update_success=True)
    )
    entry.options = {}

    payload = _serialize_entry(entry)
    rendered = repr(payload)
    assert payload["node_count"] == 1
    assert payload["positioned_count"] == 0
    assert payload["stale_after_seconds"] == 300
    assert payload["nodes"][0]["name"] == "Test Node"
    assert payload["nodes"][0]["altitude"] == 14.25
    assert payload["nodes"][0]["hidden_from_map"] is True
    assert payload["topology"]["state"] == "supported"
    assert payload["topology"]["edges"] == [
        {"from_id": "42", "to_id": "43", "route": [42, 43], "snr": [8.25]}
    ]
    assert payload["neighbors"]["state"] == "supported"
    assert payload["neighbors"]["links"][0]["snr"] == 7.5
    assert "must-not-leak" not in rendered
    assert "secret" not in rendered
    assert "url" not in payload
    assert payload["meshmonitor_links"] == {
        "details": "http://meshmonitor.invalid/source/source-1/info",
        "nodes": "http://meshmonitor.invalid/source/source-1/nodes",
        "configuration": "http://meshmonitor.invalid/source/source-1/configuration",
    }
    assert payload["nodes"][0]["meshmonitor_url"].endswith("/source/source-1/nodes")
    assert payload["transmit_enabled"] is False


def test_panel_stale_threshold_tracks_configured_polling_interval() -> None:
    """A custom interval gets a three-cycle grace instead of a fixed timeout."""
    snapshot = SourceSnapshot(
        source_id="source-1",
        fetched_at=datetime(2026, 8, 15, tzinfo=UTC),
        status=SourceStatus.from_dict({"connected": True}),
        nodes=(),
        network=None,
        telemetry=(),
        errors={},
    )
    entry = Mock()
    entry.entry_id = "entry-1"
    entry.title = "Test Source"
    entry.data = {
        "source_id": "source-1",
        "source_name": "Test Source",
        "source_type": "meshtastic",
    }
    entry.runtime_data = SimpleNamespace(
        coordinator=SimpleNamespace(data=snapshot, last_update_success=True)
    )
    entry.options = {"scan_interval": 600}

    assert _serialize_entry(entry)["stale_after_seconds"] == 1800


def test_reticulum_source_serialization_has_no_node_contract() -> None:
    snapshot = ReticulumSnapshot(
        source_id="source-rns",
        fetched_at=datetime(2026, 8, 22, tzinfo=UTC),
        status=ReticulumStatus.from_dict(
            {
                "connected": True,
                "interfaceCount": 4,
                "destinationCount": 3,
                "rnsVersion": "1.4.2",
                "bridgeVersion": "0.1.0",
                "mode": "attach",
            }
        ),
        identity=ReticulumIdentity.from_dict(
            {
                "destinationHash": "20914cb776e9d9e60418354ea6986238",
                "displayName": "MeshMonitor Synthetic RNS",
            }
        ),
        interfaces=(),
        destinations=(
            ReticulumDestination.from_dict(
                {
                    "destinationHash": "0123456789abcdef0123456789abcdef",
                    "displayName": "Synthetic LXMF peer",
                    "appName": "lxmf",
                    "lastSeen": 1770000000000,
                    "latitude": 35.1,
                    "longitude": -80.2,
                    "altitude": 245,
                    "rssi": -91,
                    "snr": 7.5,
                    "hops": 2,
                    "isFavorite": True,
                }
            ),
        ),
        conversations=(),
        paths=(),
        errors={},
    )
    entry = Mock(
        entry_id="entry-rns",
        title="RNS",
        data={
            "source_id": "source-rns",
            "source_name": "Synthetic RNS",
            "source_type": "reticulum",
        },
        options={CONF_ENABLE_TRANSMIT: True},
        runtime_data=SimpleNamespace(
            coordinator=SimpleNamespace(data=snapshot, last_update_success=True)
        ),
    )

    payload = _serialize_entry(entry)

    assert payload["connected"] is True
    assert payload["local_node_id"] is None
    assert payload["nodes"] == []
    assert payload["channels"] == []
    assert payload["transmit_enabled"] is True
    assert payload["reticulum"] == {
        "interface_count": 4,
        "destination_count": 3,
        "rns_version": "1.4.2",
        "bridge_version": "0.1.0",
        "mode": "attach",
        "identity_name": "MeshMonitor Synthetic RNS",
        "identity_hash": "20914cb776e9d9e60418354ea6986238",
        "peers": [
            {
                "id": "0123456789abcdef0123456789abcdef",
                "name": "Synthetic LXMF peer",
                "app_name": "lxmf",
                "last_seen": 1770000000000,
                "latitude": 35.1,
                "longitude": -80.2,
                "altitude": 245.0,
                "rssi": -91.0,
                "snr": 7.5,
                "hops": 2,
                "favorite": True,
            }
        ],
    }


def test_meshmonitor_links_strip_credentials_and_encode_source_id() -> None:
    """Only a credential-free verified UI origin/path may reach the browser."""
    links = _meshmonitor_links(
        "https://user:password@mesh.example:8443/base/?token=secret#fragment",
        "source/a b",
    )

    assert links == {
        "details": "https://mesh.example:8443/base/source/source%2Fa%20b/info",
        "nodes": "https://mesh.example:8443/base/source/source%2Fa%20b/nodes",
        "configuration": (
            "https://mesh.example:8443/base/source/source%2Fa%20b/configuration"
        ),
    }
    assert not _meshmonitor_links("javascript:alert(1)", "source-1")


@pytest.mark.parametrize(
    ("errors", "topology", "source_type", "topology_state", "neighbor_state"),
    [
        (
            {},
            Topology.from_dict({"nodes": [], "edges": []}),
            "meshtastic",
            "supported",
            "supported",
        ),
        ({"topology": "denied", "neighbors": "denied"}, None, "meshtastic", "error", "error"),
        (
            {
                "topology": "resource not found: topology",
                "neighbors": "resource not found: neighbors",
            },
            None,
            "meshtastic",
            "not_available",
            "not_available",
        ),
        ({}, None, "meshcore", "not_available", "not_available"),
    ],
)
def test_panel_intelligence_states_are_explicit(
    errors: dict[str, str],
    topology: Topology | None,
    source_type: str,
    topology_state: str,
    neighbor_state: str,
) -> None:
    snapshot = SourceSnapshot(
        source_id="source-1",
        fetched_at=datetime(2026, 8, 15, tzinfo=UTC),
        status=SourceStatus.from_dict({"connected": True}),
        nodes=(),
        network=None,
        telemetry=(),
        errors=errors,
        topology=topology,
    )
    entry = Mock()
    entry.entry_id = "entry-1"
    entry.title = "Test Source"
    entry.data = {
        "source_id": "source-1",
        "source_name": "Test Source",
        "source_type": source_type,
    }
    entry.runtime_data = SimpleNamespace(
        coordinator=SimpleNamespace(data=snapshot, last_update_success=True)
    )
    entry.options = {}

    payload = _serialize_entry(entry)

    assert payload["topology"] == {
        "state": topology_state,
        "nodes": [],
        "edges": [],
    }
    assert payload["neighbors"] == {"state": neighbor_state, "links": []}


def _raw_send_handler():  # type: ignore[no-untyped-def]
    return websocket_send_message.__wrapped__.__wrapped__


def _raw_favorite_handler():  # type: ignore[no-untyped-def]
    return websocket_set_favorite.__wrapped__.__wrapped__


def _raw_request_node_handler():  # type: ignore[no-untyped-def]
    return websocket_request_node_action.__wrapped__.__wrapped__


def _raw_ignore_handler():  # type: ignore[no-untyped-def]
    return websocket_set_node_ignored.__wrapped__.__wrapped__


def _raw_remove_handler():  # type: ignore[no-untyped-def]
    return websocket_remove_node.__wrapped__.__wrapped__


@pytest.mark.asyncio
async def test_saved_node_removal_option_cannot_reenable_unavailable_route() -> None:
    entry = SimpleNamespace(
        options={"enable_node_removal": True},
        runtime_data=SimpleNamespace(client=Mock()),
    )
    connection = Mock()
    message = {
        "id": 87,
        "entry_id": "entry-1",
        "source_id": "source-1",
        "node_id": "!0000002a",
    }

    with patch(
        "custom_components.meshmonitor.websocket_api._loaded_source_entry",
        return_value=entry,
    ):
        await _raw_remove_handler()(Mock(), connection, message)

    connection.send_error.assert_called_once_with(
        87,
        "node_removal_unavailable",
        "Node removal is unavailable with MeshMonitor 4.15.1 API-token authentication",
    )
    assert not entry.runtime_data.client.mock_calls


@pytest.mark.asyncio
async def test_reticulum_panel_send_uses_supported_lxmf_route() -> None:
    peer_hash = "0123456789abcdef0123456789abcdef"
    client = SimpleNamespace(
        send_reticulum_message=AsyncMock(
            return_value=SimpleNamespace(id="lxmf-message", state="sending")
        )
    )
    entry = SimpleNamespace(
        entry_id="entry-rns",
        data={CONF_SOURCE_TYPE: "reticulum"},
        options={CONF_ENABLE_TRANSMIT: True},
        runtime_data=SimpleNamespace(client=client),
    )
    hass = Mock()
    hass.data = {}
    hass.async_create_task = Mock()
    connection = Mock()
    message = {
        "id": 88,
        "entry_id": "entry-rns",
        "source_id": "source-rns",
        "protocol": "reticulum",
        "text": "Hello over LXMF",
        "nonce": "0123456789abcdef0123456789abcdef",
        "confirm": "SEND",
        "destination": peer_hash,
    }

    with (
        patch(
            "custom_components.meshmonitor.websocket_api._loaded_source_entry",
            return_value=entry,
        ),
        patch("custom_components.meshmonitor.websocket_api.reserve_message_send"),
    ):
        await _raw_send_handler()(hass, connection, message)

    client.send_reticulum_message.assert_awaited_once_with(
        "source-rns", "Hello over LXMF", to_destination_hash=peer_hash
    )
    connection.send_result.assert_called_once_with(
        88,
        {"accepted": True, "message_id": "lxmf-message", "delivery_state": "sending"},
    )


@pytest.mark.asyncio
async def test_reticulum_client_rejects_unsuccessful_2xx_receipt() -> None:
    client = MeshMonitorClient("http://mesh.invalid", "token")
    with patch.object(
        client,
        "_post_json",
        AsyncMock(return_value={"success": False, "data": {"id": "rejected"}}),
    ):
        with pytest.raises(
            MeshMonitorResponseError,
            match="did not accept the Reticulum message",
        ):
            await client.send_reticulum_message(
                "source-rns",
                "Hello over LXMF",
                to_destination_hash="a" * 32,
            )


@pytest.mark.asyncio
async def test_panel_send_reports_meshmonitor_rejection_instead_of_queued() -> None:
    client = SimpleNamespace(
        send_meshcore_message=AsyncMock(side_effect=MeshMonitorResponseError("rejected"))
    )
    entry = SimpleNamespace(
        entry_id="entry-meshcore",
        data={CONF_SOURCE_TYPE: "meshcore"},
        options={CONF_ENABLE_TRANSMIT: True},
        runtime_data=SimpleNamespace(client=client),
    )
    hass = Mock()
    hass.data = {}
    connection = Mock()
    message = {
        "id": 89,
        "entry_id": "entry-meshcore",
        "source_id": "source-meshcore",
        "protocol": "meshcore",
        "text": "Hello",
        "nonce": "1123456789abcdef0123456789abcdef",
        "confirm": "SEND",
        "destination": "a" * 64,
    }
    with (
        patch(
            "custom_components.meshmonitor.websocket_api._loaded_source_entry",
            return_value=entry,
        ),
        patch("custom_components.meshmonitor.websocket_api.reserve_message_send"),
    ):
        await _raw_send_handler()(hass, connection, message)

    connection.send_result.assert_not_called()
    connection.send_error.assert_called_once_with(
        89, "send_failed", "MeshMonitor rejected the send"
    )


@pytest.mark.asyncio
async def test_panel_send_rejects_unsuccessful_2xx_receipt() -> None:
    client = SimpleNamespace(
        send_meshcore_message=AsyncMock(
            return_value=SimpleNamespace(
                success=False,
                message_id=None,
                delivery_state=None,
            )
        )
    )
    entry = SimpleNamespace(
        entry_id="entry-meshcore",
        data={CONF_SOURCE_TYPE: "meshcore"},
        options={CONF_ENABLE_TRANSMIT: True},
        runtime_data=SimpleNamespace(client=client),
    )
    hass = Mock()
    hass.data = {}
    connection = Mock()
    message = {
        "id": 90,
        "entry_id": "entry-meshcore",
        "source_id": "source-meshcore",
        "protocol": "meshcore",
        "text": "Hello",
        "nonce": "2123456789abcdef0123456789abcdef",
        "confirm": "SEND",
        "destination": "a" * 64,
    }

    with (
        patch(
            "custom_components.meshmonitor.websocket_api._loaded_source_entry",
            return_value=entry,
        ),
        patch("custom_components.meshmonitor.websocket_api.reserve_message_send"),
    ):
        await _raw_send_handler()(hass, connection, message)

    connection.send_result.assert_not_called()
    connection.send_error.assert_called_once_with(
        90, "send_failed", "MeshMonitor rejected the send"
    )


@pytest.mark.asyncio
async def test_panel_send_validates_before_reserving_transmit_guard() -> None:
    client = SimpleNamespace(send_meshcore_message=AsyncMock())
    entry = SimpleNamespace(
        entry_id="entry-meshcore",
        data={CONF_SOURCE_TYPE: "meshcore"},
        options={CONF_ENABLE_TRANSMIT: True},
        runtime_data=SimpleNamespace(client=client),
    )
    hass = Mock()
    hass.data = {}
    connection = Mock()
    message = {
        "id": 91,
        "entry_id": "entry-meshcore",
        "source_id": "source-meshcore",
        "protocol": "meshcore",
        "text": "Hello",
        "nonce": "3123456789abcdef0123456789abcdef",
        "confirm": "SEND",
        "destination": "not-a-public-key",
    }

    with (
        patch(
            "custom_components.meshmonitor.websocket_api._loaded_source_entry",
            return_value=entry,
        ),
        patch(
            "custom_components.meshmonitor.websocket_api.reserve_message_send"
        ) as reserve,
    ):
        await _raw_send_handler()(hass, connection, message)

    reserve.assert_not_called()
    client.send_meshcore_message.assert_not_awaited()
    connection.send_error.assert_called_once_with(
        91, "invalid_format", "Message or destination failed validation"
    )


@pytest.mark.asyncio
async def test_unfavorite_refreshes_and_reconciles_without_entry_reload() -> None:
    client = Mock()
    client.set_meshtastic_favorite = AsyncMock(return_value=None)
    coordinator = SimpleNamespace(
        async_request_refresh=AsyncMock(), async_set_node_favorite=Mock()
    )
    server_entry = SimpleNamespace(
        entry_id="entry-1",
        data={"url": "http://mesh.invalid"},
        options={
            CONF_SERVER_OPTIONS: {
                CONF_NODE_DEVICE_POLICY: NODE_DEVICE_POLICY_FAVORITES
            },
            CONF_SOURCE_OPTIONS: {"source-1": {CONF_ENABLE_FAVORITES: True}},
        },
    )
    source = meshmonitor_integration.MeshMonitorSourceRuntime(
        server_entry,
        client,
        coordinator,
        "source-1",
        "Source",
        "meshtastic",
    )
    server_entry.runtime_data = SimpleNamespace(
        fingerprint="fingerprint", sources={"source-1": source}
    )
    hass = Mock()
    hass.config_entries.async_loaded_entries.return_value = [server_entry]
    hass.config_entries.async_reload = AsyncMock(return_value=True)
    connection = Mock()

    with patch(
        "custom_components.meshmonitor.entity_policy.async_reconcile_node_registries"
    ) as reconcile, patch(
        "custom_components.meshmonitor.entity.async_wait_node_entity_removals",
        new=AsyncMock(),
    ) as wait_for_removal:
        await _raw_favorite_handler()(
            hass,
            connection,
            {
                "id": 8,
                "source_id": "source-1",
                "node_id": "remote",
                "favorite": False,
            },
        )

    client.set_meshtastic_favorite.assert_awaited_once_with(
        "source-1", "remote", False
    )
    coordinator.async_request_refresh.assert_awaited_once_with()
    coordinator.async_set_node_favorite.assert_called_once_with("remote", False)
    reconcile.assert_called_once_with(hass, server_entry, source_ids={"source-1"})
    wait_for_removal.assert_awaited_once_with(
        hass,
        "fingerprint",
        "source-1",
        "remote",
    )
    hass.config_entries.async_reload.assert_not_awaited()
    connection.send_result.assert_called_once_with(8, {"favorite": False})


@pytest.mark.asyncio
async def test_manual_node_request_uses_guarded_action_contract() -> None:
    client = Mock()
    client.request_meshtastic_node_action = AsyncMock(return_value=None)
    snapshot = SimpleNamespace(
        nodes=(Node.from_dict({"id": "!1234abcd"}),),
        status=SimpleNamespace(local_node_id="!ffffffff"),
    )
    source = SimpleNamespace(
        entry_id="entry-1",
        source_id="source-1",
        source_type="meshtastic",
        options={"enable_transmit": True},
        client=client,
        coordinator=SimpleNamespace(data=snapshot),
    )
    source.runtime_data = source
    hass = Mock()
    connection = Mock(user=SimpleNamespace(id="admin"))
    with patch(
        "custom_components.meshmonitor.websocket_api._loaded_source_entry",
        return_value=source,
    ):
        # The handler imports lazily, so patch the canonical helper instead.
        with patch(
            "custom_components.meshmonitor.actions.request_meshtastic_node_action",
            new=AsyncMock(),
        ) as guarded:
            await _raw_request_node_handler()(
                hass,
                connection,
                {
                    "id": 9,
                    "entry_id": "entry-1",
                    "source_id": "source-1",
                    "node_id": "!1234abcd",
                    "action": "position",
                },
            )
    guarded.assert_awaited_once()
    connection.send_result.assert_called_once_with(
        9,
        {"accepted": True, "action": "position", "delivery_state": "accepted"},
    )


@pytest.mark.asyncio
async def test_manual_ignore_requires_gate_and_refreshes_server_only_state() -> None:
    source = SimpleNamespace(
        source_type="meshtastic",
        options={CONF_ENABLE_NODE_MANAGEMENT: True},
        client=SimpleNamespace(set_meshtastic_ignored=AsyncMock()),
        coordinator=SimpleNamespace(async_request_refresh=AsyncMock()),
    )
    source.runtime_data = source
    hass = Mock()
    connection = Mock()
    with patch(
        "custom_components.meshmonitor.websocket_api._loaded_source_entry",
        return_value=source,
    ):
        await _raw_ignore_handler()(
            hass,
            connection,
            {
                "id": 10,
                "entry_id": "entry-1",
                "source_id": "source-1",
                "node_id": "!1234abcd",
                "ignored": True,
            },
        )
    source.client.set_meshtastic_ignored.assert_awaited_once_with(
        "source-1", "!1234abcd", True
    )
    source.coordinator.async_request_refresh.assert_awaited_once_with()
    connection.send_result.assert_called_once_with(10, {"ignored": True})


def test_typed_send_validation_preserves_reviewed_body_and_utf8_boundaries() -> None:
    body = "  reviewed body  "

    assert _validate_message_text(body, len(body.encode())) == body
    assert _validate_message_text("é" * 75, 150) == "é" * 75
    with pytest.raises(ValueError, match="150 UTF-8 bytes"):
        _validate_message_text("é" * 76, 150)
    with pytest.raises(ValueError, match="valid UTF-8"):
        _validate_message_text("broken\ud800", 200)


def _raw_position_handler():  # type: ignore[no-untyped-def]
    return websocket_get_position_history.__wrapped__


def _raw_node_history_handler():  # type: ignore[no-untyped-def]
    return websocket_get_node_history.__wrapped__
