"""Asynchronous MeshMonitor API client with narrowly scoped message sending."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote, urlencode

import aiohttp

from .exceptions import (
    MeshMonitorAuthenticationError,
    MeshMonitorConnectionError,
    MeshMonitorError,
    MeshMonitorNotFoundError,
    MeshMonitorPermissionError,
    MeshMonitorRateLimitError,
    MeshMonitorResponseError,
    MeshMonitorServerError,
    MeshMonitorTransmitDisabledError,
)
from .models import (
    AutomationDefinition,
    AutomationRun,
    Capabilities,
    Channel,
    JsonObject,
    LinkQualityPoint,
    NeighborLink,
    NetworkSummary,
    Node,
    NodeDeleteResult,
    PositionHistoryPage,
    ReticulumConversation,
    ReticulumDestination,
    ReticulumIdentity,
    ReticulumInterface,
    ReticulumMessage,
    ReticulumPath,
    ReticulumSnapshot,
    ReticulumStatus,
    SendResult,
    ServerHealth,
    Source,
    SourceSnapshot,
    SourceStatus,
    TelemetryPoint,
    TelemetryRecord,
    Topology,
    Traceroute,
    UnifiedMessage,
    VersionCheck,
)


class MeshMonitorClient:
    """Minimal client with read methods and explicit message-only writes."""

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        session: aiohttp.ClientSession | None = None,
        timeout: float = 10.0,
    ) -> None:
        if not token.strip():
            raise ValueError("token must not be empty")
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._session = session
        self._owns_session = session is None
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        # Radio-backed writes can take longer than ordinary API reads while the
        # server prepares a destination contact and hands the packet to the
        # device. Keep polling bounded at the configured timeout, but allow the
        # write endpoint enough time to return its acceptance receipt.
        self._write_timeout = aiohttp.ClientTimeout(total=max(timeout, 30.0))

    async def __aenter__(self) -> MeshMonitorClient:
        await self._get_session()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def close(self) -> None:
        if self._owns_session and self._session is not None:
            await self._session.close()
            self._session = None

    async def get_sources(self) -> list[Source]:
        payload = await self._get_json("/api/v1/sources")
        return [Source.from_dict(item) for item in _object_list(payload, "sources", "data")]

    async def get_server_health(self) -> ServerHealth:
        """Read server version, uptime, and database reachability without a source."""
        payload = await self._get_object("/api/health")
        try:
            return ServerHealth.from_dict(payload)
        except ValueError as exc:
            raise MeshMonitorResponseError(f"malformed server health response: {exc}") from exc

    async def get_version_check(self) -> VersionCheck:
        """Read MeshMonitor's cached update status; never perform an update."""
        payload = await self._get_object("/api/version/check")
        return VersionCheck.from_dict(payload)

    async def get_automations(self) -> list[AutomationDefinition]:
        """Read global automation metadata without configuration or execution actions."""
        payload = await self._get_json("/api/automations")
        try:
            return [AutomationDefinition.from_dict(item) for item in _object_list(payload, "data")]
        except ValueError as exc:
            raise MeshMonitorResponseError(
                f"malformed automation definition response: {exc}"
            ) from exc

    async def get_automation_runs(
        self, automation_id: str, *, limit: int = 20
    ) -> list[AutomationRun]:
        """Read a bounded newest-first run history for one automation."""
        if not isinstance(automation_id, str) or not automation_id.strip():
            raise ValueError("automation_id must not be empty")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 200:
            raise ValueError("limit must be an integer between 1 and 200")
        automation_path = f"/api/automations/{quote(automation_id, safe='')}/runs"
        path = f"{automation_path}?{urlencode({'limit': limit})}"
        payload = await self._get_json(path)
        try:
            return [AutomationRun.from_dict(item) for item in _object_list(payload, "data")]
        except ValueError as exc:
            raise MeshMonitorResponseError(f"malformed automation run response: {exc}") from exc

    async def get_status(self, source_id: str) -> SourceStatus:
        payload = await self._get_object(self._source_path(source_id, "status"))
        status = SourceStatus.from_dict(_nested_object(payload, "data"))
        if status.local_node_id:
            return status
        # MeshMonitor 4.14.1's source-scoped status can omit the local identity
        # for passive TCP sources even though the canonical status route has it.
        try:
            legacy = await self._get_object(f"/api/status?{urlencode({'sourceId': source_id})}")
        except MeshMonitorError:
            # Identity enrichment is best-effort. A healthy source-scoped
            # snapshot must remain usable on servers without the legacy route.
            return status
        connection = legacy.get("connection")
        local = connection.get("localNode") if isinstance(connection, Mapping) else None
        if not isinstance(local, Mapping):
            return status
        return SourceStatus(
            connected=status.connected,
            node_responsive=status.node_responsive,
            local_node_id=str(local["nodeId"]) if local.get("nodeId") else None,
            long_name=str(local["longName"]) if local.get("longName") else None,
            short_name=str(local["shortName"]) if local.get("shortName") else None,
            raw=status.raw,
        )

    async def get_nodes(self, source_id: str) -> list[Node]:
        payload = await self._get_json(self._source_path(source_id, "nodes"))
        return [Node.from_dict(item) for item in _object_list(payload, "nodes", "data")]

    async def get_channels(self, source_id: str) -> list[Channel]:
        payload = await self._get_json(self._source_path(source_id, "channels"))
        return [Channel.from_dict(item) for item in _object_list(payload, "channels", "data")]

    async def get_network(self, source_id: str) -> NetworkSummary:
        payload = await self._get_object(self._source_path(source_id, "network"))
        return NetworkSummary.from_dict(_nested_object(payload, "data"))

    async def get_topology(self, source_id: str) -> Topology:
        payload = await self._get_object(self._source_path(source_id, "network/topology"))
        topology = _nested_object(payload, "data")
        _validate_mapping_collection(topology, "nodes")
        _validate_mapping_collection(topology, "edges")
        try:
            return Topology.from_dict(topology)
        except ValueError as exc:
            raise MeshMonitorResponseError(f"malformed topology response: {exc}") from exc

    async def get_neighbors(self, source_id: str) -> list[NeighborLink]:
        """Read stored, channel-filtered neighbor links without a radio request."""
        path = f"/api/sources/{quote(source_id, safe='')}/neighbor-info"
        payload = await self._get_json(path)
        return [NeighborLink.from_dict(item) for item in _object_list(payload, "data")]

    async def get_traceroutes(self, source_id: str, *, limit: int = 100) -> list[Traceroute]:
        """Read stored traceroutes; this endpoint never initiates a trace."""
        if isinstance(limit, bool) or not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200")
        path = f"{self._source_path(source_id, 'traceroutes')}?{urlencode({'limit': limit})}"
        payload = await self._get_json(path)
        return [Traceroute.from_dict(item) for item in _object_list(payload, "data")]

    async def get_route_history(
        self,
        source_id: str,
        from_node_num: int,
        to_node_num: int,
        *,
        limit: int = 50,
    ) -> list[Traceroute]:
        """Read bounded stored history for one node pair in either direction."""
        _validate_node_num(from_node_num, "from_node_num")
        _validate_node_num(to_node_num, "to_node_num")
        bounded_limit = _clamp_int(limit, 1, 1000, "limit")
        query = urlencode({"sourceId": source_id, "limit": bounded_limit})
        path = f"/api/traceroutes/history/{from_node_num}/{to_node_num}?{query}"
        payload = await self._get_json(path)
        return [Traceroute.from_dict(item) for item in _object_list(payload, "data")]

    async def get_node_telemetry_history(
        self, source_id: str, node_id: str, *, hours: float = 24
    ) -> list[TelemetryPoint]:
        """Read averaged, bounded history; never request live radio telemetry."""
        if isinstance(hours, bool) or not 0.25 <= hours <= 168:
            raise ValueError("hours must be between 0.25 and 168")
        query = urlencode({"sourceId": source_id, "hours": hours})
        path = f"/api/telemetry/{quote(node_id, safe='')}?{query}"
        payload = await self._get_json(path)
        return [TelemetryPoint.from_dict(item) for item in _object_list(payload, "data")]

    async def get_node_link_quality(
        self, source_id: str, node_id: str, *, hours: int = 24
    ) -> list[LinkQualityPoint]:
        bounded_hours = _clamp_int(hours, 1, 168, "hours")
        query = urlencode({"sourceId": source_id, "hours": bounded_hours})
        path = f"/api/telemetry/{quote(node_id, safe='')}/linkquality?{query}"
        payload = await self._get_json(path)
        return [LinkQualityPoint.from_dict(item) for item in _object_list(payload, "data")]

    async def get_position_history(
        self,
        source_id: str,
        node_id: str,
        *,
        since: int | None = None,
        before: int | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> PositionHistoryPage:
        """Read one bounded position page while preserving privacy denials."""
        bounded_limit = _clamp_int(limit, 1, 10000, "limit")
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise ValueError("offset must be a non-negative integer")
        query: dict[str, str | int] = {"limit": bounded_limit, "offset": offset}
        for name, value in (("since", since), ("before", before)):
            if value is not None:
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise ValueError(f"{name} must be a non-negative integer")
                query[name] = value
        path = self._source_path(
            source_id,
            f"nodes/{quote(node_id, safe='')}/position-history?{urlencode(query)}",
        )
        payload = await self._get_object(path)
        _validate_mapping_collection(payload, "data")
        return PositionHistoryPage.from_dict(payload)

    async def get_telemetry(self, source_id: str) -> list[TelemetryRecord]:
        payload = await self._get_json(self._source_path(source_id, "telemetry"))
        return [
            TelemetryRecord.from_dict(item)
            for item in _object_list(payload, "telemetry", "records", "data")
        ]

    async def get_meshcore_status(self, source_id: str) -> SourceStatus:
        """Read MeshCore identity and cached health without polling the radio."""
        payload = await self._get_object(self._meshcore_path(source_id, "info"))
        return SourceStatus.from_meshcore_dict(_nested_object(payload, "data"))

    async def get_meshcore_nodes(self, source_id: str) -> list[Node]:
        """Read MeshCore contacts through the non-v1 compatibility route."""
        payload = await self._get_json(self._meshcore_path(source_id, "nodes"))
        return [Node.from_meshcore_dict(item) for item in _object_list(payload, "data")]

    async def get_meshcore_snapshot(self, source_id: str) -> SourceSnapshot:
        """Fetch a serialized, read-only MeshCore coordinator snapshot."""
        status = await self.get_meshcore_status(source_id)
        nodes = await self.get_meshcore_nodes(source_id)
        channels: list[Channel] = []
        errors: dict[str, str] = {}
        try:
            channels = await self.get_channels(source_id)
        except MeshMonitorNotFoundError:
            # Older MeshMonitor builds do not expose protocol-neutral channels.
            pass
        except MeshMonitorError as exc:
            errors["channels"] = str(exc)
        return SourceSnapshot.create(source_id, status, nodes, None, [], errors, channels)

    async def get_reticulum_status(self, source_id: str) -> ReticulumStatus:
        """Read bridge connection and inventory state without probing the network."""
        payload = await self._get_object(self._reticulum_path(source_id, "status"))
        return ReticulumStatus.from_dict(_nested_object(payload, "data"))

    async def get_reticulum_identity(self, source_id: str) -> ReticulumIdentity:
        """Read the bridge's public LXMF destination; never expose private identity data."""
        payload = await self._get_object(self._reticulum_path(source_id, "identity"))
        return ReticulumIdentity.from_dict(_nested_object(payload, "data"))

    async def get_reticulum_interfaces(self, source_id: str) -> list[ReticulumInterface]:
        """Read persisted RNS interface observations."""
        payload = await self._get_json(self._reticulum_path(source_id, "interfaces"))
        return [ReticulumInterface.from_dict(item) for item in _object_list(payload, "data")]

    async def get_reticulum_destinations(self, source_id: str) -> list[ReticulumDestination]:
        """Read announced destinations retained by MeshMonitor."""
        payload = await self._get_json(self._reticulum_path(source_id, "destinations"))
        return [ReticulumDestination.from_dict(item) for item in _object_list(payload, "data")]

    async def get_reticulum_conversations(self, source_id: str) -> list[ReticulumConversation]:
        """Read bounded latest-message summaries for LXMF peers."""
        payload = await self._get_json(self._reticulum_path(source_id, "messages"))
        return [ReticulumConversation.from_dict(item) for item in _object_list(payload, "data")]

    async def get_reticulum_messages(
        self, source_id: str, peer_hash: str, *, limit: int = 100
    ) -> list[ReticulumMessage]:
        """Read one bounded LXMF conversation; this method never sends or syncs."""
        if not re.fullmatch(r"[0-9a-fA-F]{32}", peer_hash):
            raise ValueError("peer_hash must contain 32 hexadecimal digits")
        bounded_limit = _clamp_int(limit, 1, 500, "limit")
        suffix = (
            f"messages/{quote(peer_hash.lower(), safe='')}?{urlencode({'limit': bounded_limit})}"
        )
        payload = await self._get_json(self._reticulum_path(source_id, suffix))
        return [ReticulumMessage.from_dict(item) for item in _object_list(payload, "data")]

    async def get_reticulum_unified_messages(
        self,
        source_id: str,
        source_name: str | None,
        peer_hash: str,
        *,
        limit: int = 100,
    ) -> list[UnifiedMessage]:
        """Adapt one LXMF conversation to the protocol-neutral message contract."""
        messages = await self.get_reticulum_messages(source_id, peer_hash, limit=limit)
        return [
            UnifiedMessage.from_dict(
                {
                    "dedupKey": f"rns:{source_id}:{message.id}",
                    "fromNodeId": message.from_hash,
                    "toNodeId": message.to_hash,
                    "channel": -1,
                    "channelName": "LXMF",
                    "text": message.content,
                    "timestamp": message.timestamp,
                    "receivedAt": message.received_at,
                    "replyId": message.reply_to_hash,
                    "receptions": [
                        {
                            "sourceId": source_id,
                            "sourceName": source_name,
                            "sourceType": "reticulum",
                            "rxRssi": message.rssi,
                            "rxSnr": message.snr,
                            "timestamp": message.received_at or message.timestamp,
                        }
                    ],
                    "reticulum": {
                        "messageId": message.id,
                        "title": message.title,
                        "state": message.state,
                        "method": message.method,
                        "signatureValidated": message.signature_validated,
                        "ratcheted": message.ratcheted,
                        "threadHash": message.thread_hash,
                        "quality": message.quality,
                    },
                }
            )
            for message in messages
        ]

    async def send_reticulum_message(
        self,
        source_id: str,
        text: str,
        *,
        to_destination_hash: str,
        title: str | None = None,
        method: str | None = None,
        reply_to_hash: str | None = None,
    ) -> ReticulumMessage:
        """Send one bounded LXMF direct message through a Reticulum source."""
        clean_text = _validate_message_text(text, 4096)
        if not re.fullmatch(r"[0-9a-fA-F]{32}", to_destination_hash):
            raise ValueError("to_destination_hash must contain 32 hexadecimal digits")
        payload: JsonObject = {
            "to": to_destination_hash.lower(),
            "content": clean_text,
        }
        if title is not None:
            payload["title"] = _validate_message_text(title, 256)
        if method is not None:
            if method not in {"opportunistic", "direct", "propagated", "paper"}:
                raise ValueError("unsupported LXMF delivery method")
            payload["method"] = method
        if reply_to_hash is not None:
            if not re.fullmatch(r"[0-9a-fA-F]+", reply_to_hash):
                raise ValueError("reply_to_hash must contain hexadecimal digits")
            payload["replyToHash"] = reply_to_hash.lower()
        response = await self._post_json(self._reticulum_path(source_id, "messages"), payload)
        try:
            return ReticulumMessage.from_dict(_nested_object(response, "data"))
        except ValueError as exc:
            raise MeshMonitorResponseError("invalid Reticulum send response") from exc

    async def get_reticulum_paths(self, source_id: str) -> list[ReticulumPath]:
        """Read stored paths only; unlike the probe API this has no network side effect."""
        payload = await self._get_json(self._reticulum_path(source_id, "paths"))
        return [ReticulumPath.from_dict(item) for item in _object_list(payload, "data")]

    async def get_reticulum_snapshot(self, source_id: str) -> ReticulumSnapshot:
        """Fetch a serialized read-only Reticulum snapshot with optional failures exposed."""
        status = await self.get_reticulum_status(source_id)
        errors: dict[str, str] = {}

        identity: ReticulumIdentity | None = None
        interfaces: list[ReticulumInterface] = []
        destinations: list[ReticulumDestination] = []
        conversations: list[ReticulumConversation] = []
        paths: list[ReticulumPath] = []
        try:
            identity = await self.get_reticulum_identity(source_id)
        except MeshMonitorError as exc:
            errors["identity"] = str(exc)
        try:
            interfaces = await self.get_reticulum_interfaces(source_id)
        except MeshMonitorError as exc:
            errors["interfaces"] = str(exc)
        try:
            destinations = await self.get_reticulum_destinations(source_id)
        except MeshMonitorError as exc:
            errors["destinations"] = str(exc)
        try:
            conversations = await self.get_reticulum_conversations(source_id)
        except MeshMonitorError as exc:
            errors["conversations"] = str(exc)
        try:
            paths = await self.get_reticulum_paths(source_id)
        except MeshMonitorError as exc:
            errors["paths"] = str(exc)
        return ReticulumSnapshot(
            source_id=source_id,
            fetched_at=datetime.now(UTC),
            status=status,
            identity=identity,
            interfaces=tuple(interfaces),
            destinations=tuple(destinations),
            conversations=tuple(conversations),
            paths=tuple(paths),
            errors=errors,
        )

    async def set_meshtastic_favorite(
        self, source_id: str, node_id: str, is_favorite: bool
    ) -> None:
        """Persist a favorite in MeshMonitor without syncing it to the radio."""
        if not re.fullmatch(r"![0-9a-fA-F]{8}", node_id):
            raise ValueError("node_id must be ! followed by 8 hexadecimal digits")
        await self._post_json(
            f"/api/nodes/{quote(node_id, safe='')}/favorite",
            {
                "sourceId": source_id,
                "isFavorite": is_favorite,
                # This invariant is the boundary between harmless server metadata
                # and a Meshtastic device/radio write.
                "syncToDevice": False,
            },
        )

    async def set_meshtastic_ignored(self, source_id: str, node_id: str, is_ignored: bool) -> None:
        """Persist ignored state in MeshMonitor without syncing it to the radio."""
        if not re.fullmatch(r"![0-9a-fA-F]{8}", node_id):
            raise ValueError("node_id must be ! followed by 8 hexadecimal digits")
        await self._post_json(
            f"/api/nodes/{quote(node_id, safe='')}/ignored",
            {
                "sourceId": source_id,
                "isIgnored": is_ignored,
                "syncToDevice": False,
            },
        )

    async def delete_meshtastic_node(self, source_id: str, node_id: str) -> NodeDeleteResult:
        """Delete one Meshtastic node from one exact MeshMonitor source."""
        if not re.fullmatch(r"![0-9a-fA-F]{8}", node_id):
            raise ValueError("node_id must be ! followed by 8 hexadecimal digits")
        node_num = int(node_id[1:], 16)
        payload = await self._delete_json(
            f"/api/nodes/{node_num}?{urlencode({'sourceId': source_id})}"
        )
        return NodeDeleteResult.from_dict(payload)

    async def set_meshcore_favorite(
        self, source_id: str, public_key: str, is_favorite: bool
    ) -> None:
        """Persist MeshCore's server-side-only favorite flag."""
        if not re.fullmatch(r"[0-9a-fA-F]{64}", public_key):
            raise ValueError("public_key must contain 64 hexadecimal digits")
        await self._post_json(
            self._meshcore_path(source_id, f"nodes/{quote(public_key, safe='')}/favorite"),
            {"isFavorite": is_favorite},
        )

    async def get_unified_messages(
        self,
        *,
        limit: int = 100,
        before: int | None = None,
        channel: str | None = None,
    ) -> list[UnifiedMessage]:
        """Read the permission-filtered, cross-protocol unified message feed."""
        if not 1 <= limit <= 500:
            raise ValueError("limit must be between 1 and 500")
        query: dict[str, str | int] = {"limit": limit}
        if before is not None:
            query["before"] = before
        if channel:
            query["channel"] = channel
        payload = await self._get_json(f"/api/unified/messages?{urlencode(query)}")
        return [UnifiedMessage.from_dict(item) for item in _object_list(payload, "data")]

    async def get_meshtastic_messages(
        self,
        source_id: str,
        *,
        source_name: str | None = None,
        limit: int = 100,
    ) -> list[UnifiedMessage]:
        """Read one source's stored Meshtastic history through the token API."""
        if not 1 <= limit <= 500:
            raise ValueError("limit must be between 1 and 500")
        payload = await self._get_json(
            f"{self._source_path(source_id, 'messages')}?{urlencode({'limit': limit})}"
        )
        try:
            return [
                _meshtastic_message(item, source_id, source_name)
                for item in _object_list(payload, "data")
            ]
        except ValueError as exc:
            raise MeshMonitorResponseError("invalid Meshtastic message response") from exc

    async def get_meshcore_messages(
        self,
        source_id: str,
        *,
        source_name: str | None = None,
        limit: int = 100,
    ) -> list[UnifiedMessage]:
        """Read one source's stored MeshCore history without any radio action."""
        if not 1 <= limit <= 500:
            raise ValueError("limit must be between 1 and 500")
        payload = await self._get_json(
            f"{self._meshcore_path(source_id, 'messages')}?{urlencode({'limit': limit})}"
        )
        try:
            return [
                _meshcore_message(item, source_id, source_name)
                for item in _object_list(payload, "data")
            ]
        except ValueError as exc:
            raise MeshMonitorResponseError("invalid MeshCore message response") from exc

    async def send_meshtastic_message(
        self,
        source_id: str,
        text: str,
        *,
        channel: int | None = None,
        to_node_id: str | None = None,
        reply_id: int | None = None,
    ) -> SendResult:
        """Send one unsplit Meshtastic channel message or direct message."""
        clean_text = _validate_message_text(text, 200)
        if (channel is None) == (to_node_id is None):
            raise ValueError("provide exactly one of channel or to_node_id")
        payload: JsonObject = {"text": clean_text}
        if channel is not None:
            if not 0 <= channel <= 7:
                raise ValueError("channel must be between 0 and 7")
            payload["channel"] = channel
        else:
            assert to_node_id is not None
            if not re.fullmatch(r"![0-9a-fA-F]{8}", to_node_id):
                raise ValueError("to_node_id must be ! followed by 8 hexadecimal digits")
            payload["toNodeId"] = to_node_id
        if reply_id is not None:
            if not 0 <= reply_id <= 0xFFFFFFFF:
                raise ValueError("reply_id must be between 0 and 4294967295")
            payload["replyId"] = reply_id
        response = await self._post_json(self._source_path(source_id, "messages"), payload)
        return SendResult.from_dict(response)

    async def request_meshtastic_node_action(
        self,
        source_id: str,
        node_id: str,
        action: str,
        *,
        channel: int | None = None,
    ) -> SendResult:
        """Request one bounded, source-scoped Meshtastic node operation."""
        paths = {
            "traceroute": "traceroute",
            "position": "request-position",
            "nodeinfo": "request-nodeinfo",
            "neighbors": "request-neighbors",
        }
        if action not in paths:
            raise ValueError("unsupported Meshtastic node action")
        if not re.fullmatch(r"![0-9a-fA-F]{8}", node_id):
            raise ValueError("node_id must be ! followed by 8 hexadecimal digits")
        payload: JsonObject = {"destination": node_id}
        if channel is not None:
            if not 0 <= channel <= 7:
                raise ValueError("channel must be between 0 and 7")
            payload["channel"] = channel
        response = await self._post_json(
            self._source_path(source_id, f"actions/{paths[action]}"), payload
        )
        return SendResult.from_dict(response)

    async def send_meshcore_message(
        self,
        source_id: str,
        text: str,
        *,
        channel: int | None = None,
        to_public_key: str | None = None,
    ) -> SendResult:
        """Send one MeshCore channel message or direct message."""
        if (channel is None) == (to_public_key is None):
            raise ValueError("provide exactly one of channel or to_public_key")
        limit = 150 if to_public_key is not None else 130
        payload: JsonObject = {"text": _validate_message_text(text, limit)}
        if channel is not None:
            if not 0 <= channel <= 255:
                raise ValueError("channel must be between 0 and 255")
            payload["channelIdx"] = channel
        else:
            assert to_public_key is not None
            if not re.fullmatch(r"[0-9a-fA-F]{64}", to_public_key):
                raise ValueError("to_public_key must contain 64 hexadecimal digits")
            payload["toPublicKey"] = to_public_key
        response = await self._post_json(self._meshcore_path(source_id, "messages/send"), payload)
        return SendResult.from_dict(response)

    async def send_meshcore_advert(self, source_id: str) -> None:
        """Send exactly one MeshCore flood advert for the selected source."""
        response = await self._post_json(self._meshcore_path(source_id, "advert"), {})
        if response.get("success") is not True:
            raise MeshMonitorResponseError("MeshMonitor did not accept the advert")

    async def get_snapshot(self, source_id: str) -> SourceSnapshot:
        """Fetch the mandatory node state and best-effort supporting data.

        Status and nodes define coordinator availability and therefore fail the
        whole refresh. Network and telemetry failures are recorded so Home
        Assistant can retain the last optional values without hiding an outage.
        Requests are deliberately serialized to avoid bursts against MeshMonitor.
        """
        status = await self.get_status(source_id)
        nodes = await self.get_nodes(source_id)
        errors: dict[str, str] = {}

        network: NetworkSummary | None = None
        try:
            network = await self.get_network(source_id)
        except MeshMonitorError as exc:
            errors["network"] = str(exc)

        topology: Topology | None = None
        try:
            topology = await self.get_topology(source_id)
        except MeshMonitorError as exc:
            errors["topology"] = str(exc)

        neighbors: list[NeighborLink] = []
        try:
            neighbors = await self.get_neighbors(source_id)
        except MeshMonitorError as exc:
            errors["neighbors"] = str(exc)

        telemetry: list[TelemetryRecord] = []
        try:
            telemetry = await self.get_telemetry(source_id)
        except MeshMonitorError as exc:
            errors["telemetry"] = str(exc)

        channels: list[Channel] = []
        try:
            channels = await self.get_channels(source_id)
        except MeshMonitorNotFoundError:
            pass
        except MeshMonitorError as exc:
            errors["channels"] = str(exc)

        return SourceSnapshot.create(
            source_id,
            status,
            nodes,
            network,
            telemetry,
            errors,
            channels,
            topology,
            neighbors,
        )

    async def probe_capabilities(self, source_id: str) -> Capabilities:
        results: dict[str, bool] = {"sources": True}
        nodes: list[Node] = []
        probes = {
            "status": self.get_status,
            "nodes": self.get_nodes,
            "channels": self.get_channels,
            "network": self.get_network,
            "topology": self.get_topology,
            "telemetry": self.get_telemetry,
        }
        for name, method in probes.items():
            try:
                value = await method(source_id)
                results[name] = True
                if name == "nodes" and isinstance(value, list):
                    nodes = value
            except (MeshMonitorPermissionError, MeshMonitorNotFoundError):
                results[name] = False
        return Capabilities(
            **results,
            node_visibility_suspect=results.get("nodes", False) and not nodes,
        )

    async def _get_object(self, path: str) -> JsonObject:
        payload = await self._get_json(path)
        if not isinstance(payload, Mapping):
            raise MeshMonitorResponseError(f"expected JSON object from {path}")
        return dict(payload)

    async def _get_json(self, path: str) -> Any:
        session = await self._get_session()
        headers = {"Authorization": f"Bearer {self._token}", "Accept": "application/json"}
        try:
            async with session.get(
                f"{self._base_url}{path}", headers=headers, timeout=self._timeout
            ) as response:
                if response.status == 401:
                    raise MeshMonitorAuthenticationError("MeshMonitor rejected the API token")
                if response.status == 403:
                    raise MeshMonitorPermissionError(f"permission denied for {path}")
                if response.status == 404:
                    raise MeshMonitorNotFoundError(f"resource not found: {path}")
                if response.status >= 500:
                    raise MeshMonitorServerError(
                        f"MeshMonitor returned HTTP {response.status} for {path}"
                    )
                if response.status >= 400:
                    raise MeshMonitorResponseError(f"unexpected HTTP {response.status} for {path}")
                try:
                    return await response.json(content_type=None)
                except (aiohttp.ContentTypeError, ValueError) as exc:
                    raise MeshMonitorResponseError(f"invalid JSON from {path}") from exc
        except (aiohttp.ClientError, TimeoutError) as exc:
            raise MeshMonitorConnectionError(str(exc)) from exc
        except RuntimeError as exc:
            if str(exc) != "Session is closed":
                raise
            raise MeshMonitorConnectionError(str(exc)) from exc

    async def _post_json(self, path: str, payload: JsonObject) -> JsonObject:
        session = await self._get_session()
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        try:
            async with session.post(
                f"{self._base_url}{path}",
                headers=headers,
                json=payload,
                timeout=self._write_timeout,
            ) as response:
                try:
                    body = await response.json(content_type=None)
                except (aiohttp.ContentTypeError, ValueError) as exc:
                    raise MeshMonitorResponseError(f"invalid JSON from {path}") from exc
                if response.status == 401:
                    raise MeshMonitorAuthenticationError("MeshMonitor rejected the API token")
                if response.status == 403:
                    raise MeshMonitorPermissionError(f"permission denied for {path}")
                if response.status == 404:
                    raise MeshMonitorNotFoundError(f"resource not found: {path}")
                if response.status == 409:
                    raise MeshMonitorTransmitDisabledError(f"transmit disabled for {path}")
                if response.status == 429:
                    raise MeshMonitorRateLimitError(f"rate limited for {path}")
                if response.status >= 500:
                    raise MeshMonitorServerError(
                        f"MeshMonitor returned HTTP {response.status} for {path}"
                    )
                if response.status >= 400:
                    raise MeshMonitorResponseError(f"unexpected HTTP {response.status} for {path}")
                if not isinstance(body, Mapping):
                    raise MeshMonitorResponseError(f"expected JSON object from {path}")
                return dict(body)
        except (aiohttp.ClientError, TimeoutError) as exc:
            raise MeshMonitorConnectionError(str(exc)) from exc
        except RuntimeError as exc:
            if str(exc) != "Session is closed":
                raise
            raise MeshMonitorConnectionError(str(exc)) from exc

    async def _delete_json(self, path: str) -> JsonObject:
        session = await self._get_session()
        headers = {"Authorization": f"Bearer {self._token}", "Accept": "application/json"}
        try:
            async with session.delete(
                f"{self._base_url}{path}", headers=headers, timeout=self._timeout
            ) as response:
                try:
                    body = await response.json(content_type=None)
                except (aiohttp.ContentTypeError, ValueError) as exc:
                    raise MeshMonitorResponseError(f"invalid JSON from {path}") from exc
                if response.status == 401:
                    raise MeshMonitorAuthenticationError("MeshMonitor rejected the API token")
                if response.status == 403:
                    raise MeshMonitorPermissionError(f"permission denied for {path}")
                if response.status == 404:
                    raise MeshMonitorNotFoundError(f"resource not found: {path}")
                if response.status >= 500:
                    raise MeshMonitorServerError(
                        f"MeshMonitor returned HTTP {response.status} for {path}"
                    )
                if response.status >= 400:
                    raise MeshMonitorResponseError(f"unexpected HTTP {response.status} for {path}")
                if not isinstance(body, Mapping):
                    raise MeshMonitorResponseError(f"expected JSON object from {path}")
                return dict(body)
        except (aiohttp.ClientError, TimeoutError) as exc:
            raise MeshMonitorConnectionError(str(exc)) from exc
        except RuntimeError as exc:
            if str(exc) != "Session is closed":
                raise
            raise MeshMonitorConnectionError(str(exc)) from exc

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session

    @staticmethod
    def _source_path(source_id: str, suffix: str) -> str:
        return f"/api/v1/sources/{quote(source_id, safe='')}/{suffix}"

    @staticmethod
    def _meshcore_path(source_id: str, suffix: str) -> str:
        return f"/api/sources/{quote(source_id, safe='')}/meshcore/{suffix}"

    @staticmethod
    def _reticulum_path(source_id: str, suffix: str) -> str:
        return f"/api/sources/{quote(source_id, safe='')}/reticulum/{suffix}"


def _object_list(payload: Any, *keys: str) -> list[JsonObject]:
    candidate = payload
    if isinstance(payload, Mapping):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
                candidate = value
                break
    if not isinstance(candidate, Sequence) or isinstance(candidate, (str, bytes, bytearray)):
        raise MeshMonitorResponseError("expected a JSON array")
    if not all(isinstance(item, Mapping) for item in candidate):
        raise MeshMonitorResponseError("JSON array contains a non-object item")
    return [dict(item) for item in candidate]


def _meshtastic_message(
    data: Mapping[str, Any], source_id: str, source_name: str | None
) -> UnifiedMessage:
    """Project the verified v1 source envelope onto the unified display model."""
    normalized = dict(data)
    row_id = data.get("id")
    if row_id is None:
        raise ValueError("Meshtastic message has no stable id")
    sender = data.get("fromNodeId") or data.get("fromNodeNum") or "unknown"
    match = re.search(r"_(\d+)(?:_(?:dbchan|radio))?$", str(row_id))
    packet_id = int(match.group(1)) if match else None
    normalized["dedupKey"] = (
        f"mt:{sender}:p{packet_id}"
        if packet_id is not None and packet_id <= 0xFFFFFFFF
        else f"mt:{source_id}:{row_id}"
    )
    normalized["receptions"] = [
        {
            "sourceId": source_id,
            "sourceName": source_name,
            "sourceType": "meshtastic",
            "rxRssi": data.get("rxRssi"),
            "rxSnr": data.get("rxSnr"),
            "rxTime": data.get("rxTime") or data.get("timestamp"),
        }
    ]
    return UnifiedMessage.from_dict(normalized)


def _meshcore_message(
    data: Mapping[str, Any], source_id: str, source_name: str | None
) -> UnifiedMessage:
    """Project the verified MeshCore stored-message envelope onto the shared model."""
    normalized = dict(data)
    row_id = data.get("id")
    if row_id is None:
        raise ValueError("MeshCore message has no stable id")
    channel = _meshcore_channel(data)
    normalized.update(
        {
            "dedupKey": f"mc:{source_id}:{row_id}",
            "channel": channel if channel is not None else -1,
            "receptions": [
                {
                    "sourceId": source_id,
                    "sourceName": source_name,
                    "sourceType": "meshcore",
                    "rxRssi": data.get("rssi"),
                    "rxSnr": data.get("snr"),
                    "timestamp": data.get("timestamp"),
                }
            ],
        }
    )
    return UnifiedMessage.from_dict(normalized)


def _meshcore_channel(data: Mapping[str, Any]) -> int | None:
    for value in (data.get("fromPublicKey"), data.get("toPublicKey")):
        if isinstance(value, str) and (match := re.fullmatch(r"channel-(\d+)", value)):
            return int(match.group(1))
    return None


def _nested_object(payload: Mapping[str, Any], key: str) -> JsonObject:
    candidate = payload.get(key, payload)
    if not isinstance(candidate, Mapping):
        raise MeshMonitorResponseError(f"expected '{key}' to contain a JSON object")
    return dict(candidate)


def _validate_mapping_collection(payload: Mapping[str, Any], key: str) -> None:
    """Reject malformed typed collections instead of presenting them as empty."""
    value = payload.get(key)
    if value is None:
        return
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise MeshMonitorResponseError(f"expected '{key}' to contain a JSON array")
    if not all(isinstance(item, Mapping) for item in value):
        raise MeshMonitorResponseError(f"'{key}' contains a non-object item")


def _validate_message_text(text: str, max_bytes: int) -> str:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("message text must not be empty")
    try:
        encoded = text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("message text must contain valid UTF-8") from exc
    if len(encoded) > max_bytes:
        raise ValueError(f"message text must not exceed {max_bytes} UTF-8 bytes")
    # The reviewed body must be byte-for-byte identical to the transmitted
    # body. Whitespace is therefore validated for emptiness but never trimmed.
    return text


def _validate_node_num(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 0xFFFFFFFF:
        raise ValueError(f"{name} must be an integer between 0 and 4294967295")


def _clamp_int(value: int, lower: int, upper: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return max(lower, min(upper, value))


def _validate_limit(value: int, upper: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= upper:
        raise ValueError(f"limit must be an integer between 1 and {upper}")


def _validate_source_id(value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("source_id must not be empty")
