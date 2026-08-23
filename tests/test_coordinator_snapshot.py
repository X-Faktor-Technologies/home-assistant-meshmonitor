"""Deterministic tests for the serialized source coordinator snapshot."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, Mock

from homeassistant.core import HomeAssistant

from custom_components.meshmonitor.coordinator import MeshMonitorCoordinator
from custom_components.meshmonitor.vendor_meshmonitor_client import (
    MeshMonitorClient,
    SourceSnapshot,
    SourceStatus,
)


class _FakeResponse:
    def __init__(self, status: int, payload: Any) -> None:
        self.status = status
        self._payload = payload

    async def __aenter__(self) -> _FakeResponse:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def json(self, *, content_type: str | None = None) -> Any:
        del content_type
        return json.loads(json.dumps(self._payload))


class _FakeSession:
    def __init__(self, routes: Mapping[str, tuple[int, Any]]) -> None:
        self.routes = routes
        self.requests: list[str] = []
        self.closed = False

    def get(self, url: str, **_: Any) -> _FakeResponse:
        self.requests.append(url)
        path = "/" + url.split("/", 3)[-1]
        status, payload = self.routes.get(path, (404, {"error": "not found"}))
        return _FakeResponse(status, payload)


async def test_passive_tcp_status_recovers_local_identity_from_canonical_route() -> None:
    base = "/api/v1/sources/source-1"
    session = _FakeSession(
        {
            f"{base}/status": (200, {"data": {"connected": True}}),
            "/api/status?sourceId=source-1": (
                200,
                {
                    "connection": {
                        "localNode": {
                            "nodeId": "!da539a4c",
                            "longName": "Synthetic Meshtastic",
                            "shortName": "x02",
                        }
                    }
                },
            ),
        }
    )
    client = MeshMonitorClient(
        "http://mesh.test", "secret", session=session  # type: ignore[arg-type]
    )

    status = await client.get_status("source-1")

    assert status.connected is True
    assert status.local_node_id == "!da539a4c"
    assert status.long_name == "Synthetic Meshtastic"
    assert status.short_name == "x02"


async def test_snapshot_serializes_topology_and_neighbor_reads() -> None:
    base = "/api/v1/sources/source-1"
    session = _FakeSession(
        {
            f"{base}/status": (200, {"data": {"connected": True}}),
            f"{base}/nodes": (200, {"data": [{"nodeId": "!00000001"}]}),
            f"{base}/network": (200, {"data": {"totalNodes": 1}}),
            f"{base}/network/topology": (
                200,
                {"data": {"nodes": [{"nodeId": "!00000001"}], "edges": []}},
            ),
            "/api/sources/source-1/neighbor-info": (200, {"data": []}),
            f"{base}/telemetry": (200, {"data": []}),
            f"{base}/channels": (200, {"data": []}),
        }
    )
    client = MeshMonitorClient(
        "http://mesh.test", "secret", session=session  # type: ignore[arg-type]
    )

    snapshot = await client.get_snapshot("source-1")

    assert snapshot.topology is not None
    assert snapshot.topology.nodes[0].node_id == "!00000001"
    assert snapshot.topology.edges == ()
    assert snapshot.neighbors == ()
    assert snapshot.errors == {}
    assert session.requests == [
        f"http://mesh.test{base}/status",
        "http://mesh.test/api/status?sourceId=source-1",
        f"http://mesh.test{base}/nodes",
        f"http://mesh.test{base}/network",
        f"http://mesh.test{base}/network/topology",
        "http://mesh.test/api/sources/source-1/neighbor-info",
        f"http://mesh.test{base}/telemetry",
        f"http://mesh.test{base}/channels",
    ]


async def test_snapshot_distinguishes_errors_from_supported_empty_data() -> None:
    base = "/api/v1/sources/source-1"
    session = _FakeSession(
        {
            f"{base}/status": (200, {"data": {"connected": True}}),
            f"{base}/nodes": (200, {"data": [{"nodeId": "!00000001"}]}),
            f"{base}/network": (200, {"data": {}}),
            f"{base}/network/topology": (404, {"error": "unsupported"}),
            "/api/sources/source-1/neighbor-info": (403, {"error": "denied"}),
            f"{base}/telemetry": (200, {"data": []}),
            f"{base}/channels": (200, {"data": []}),
        }
    )
    client = MeshMonitorClient(
        "http://mesh.test", "secret", session=session  # type: ignore[arg-type]
    )

    snapshot = await client.get_snapshot("source-1")

    assert snapshot.topology is None
    assert snapshot.neighbors == ()
    assert snapshot.errors["topology"].startswith("resource not found:")
    assert snapshot.errors["neighbors"].startswith("permission denied for")


async def test_snapshot_rejects_malformed_intelligence_as_endpoint_errors() -> None:
    base = "/api/v1/sources/source-1"
    session = _FakeSession(
        {
            f"{base}/status": (200, {"data": {"connected": True}}),
            f"{base}/nodes": (200, {"data": [{"nodeId": "!00000001"}]}),
            f"{base}/network": (200, {"data": {}}),
            f"{base}/network/topology": (
                200,
                {"data": {"nodes": "not-a-list", "edges": []}},
            ),
            "/api/sources/source-1/neighbor-info": (200, {"data": "not-a-list"}),
            f"{base}/telemetry": (200, {"data": []}),
            f"{base}/channels": (200, {"data": []}),
        }
    )
    client = MeshMonitorClient(
        "http://mesh.test", "secret", session=session  # type: ignore[arg-type]
    )

    snapshot = await client.get_snapshot("source-1")

    assert snapshot.topology is None
    assert snapshot.neighbors == ()
    assert snapshot.errors["topology"].startswith("expected 'nodes'")
    assert snapshot.errors["neighbors"] == "expected a JSON array"


async def test_coordinator_uses_configured_interval_for_one_snapshot_refresh(
    hass: HomeAssistant,
) -> None:
    snapshot = SourceSnapshot.create(
        "source-1",
        SourceStatus.from_dict({"connected": True}),
        [],
        None,
        [],
        {},
    )
    client = Mock()
    client.get_snapshot = AsyncMock(return_value=snapshot)
    interval = timedelta(seconds=75)
    coordinator = MeshMonitorCoordinator(
        hass, client, "source-1", "meshtastic", interval
    )

    result = await coordinator._async_update_data()

    assert coordinator.update_interval == interval
    assert result is snapshot
    client.get_snapshot.assert_awaited_once_with("source-1")
