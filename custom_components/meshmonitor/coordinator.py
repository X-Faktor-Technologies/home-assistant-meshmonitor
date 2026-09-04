"""Data coordinator for MeshMonitor."""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    SOURCE_TYPE_MESHCORE,
    SOURCE_TYPE_RETICULUM,
)
from .vendor_meshmonitor_client import (
    MeshMonitorAuthenticationError,
    MeshMonitorClient,
    MeshMonitorConnectionError,
    MeshMonitorResponseError,
    MeshMonitorServerError,
    Node,
    ReticulumSnapshot,
    SourceSnapshot,
)

_LOGGER = logging.getLogger(__name__)


class MeshMonitorCoordinator(DataUpdateCoordinator[SourceSnapshot | ReticulumSnapshot]):
    """Coordinate a controlled, shared refresh for all MeshMonitor entities."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: MeshMonitorClient,
        source_id: str,
        source_type: str,
        update_interval: timedelta = DEFAULT_SCAN_INTERVAL,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{source_id}",
            update_interval=update_interval,
            always_update=False,
        )
        self.client = client
        self.source_id = source_id
        self.source_type = source_type

    @property
    def nodes(self) -> dict[str, Node]:
        """Return nodes keyed by stable MeshMonitor node ID."""
        if self.data is None:
            return {}
        nodes = getattr(self.data, "nodes", ())
        return {node.id: node for node in nodes}

    def async_set_node_favorite(self, node_id: str, favorite: bool) -> None:
        """Publish one confirmed favorite write without waiting for API cache expiry."""
        snapshot = self.data
        if not isinstance(snapshot, SourceSnapshot):
            return
        nodes = tuple(
            replace(
                node,
                is_favorite=favorite,
                raw={**node.raw, "isFavorite": favorite},
            )
            if node.id == node_id
            else node
            for node in snapshot.nodes
        )
        if not any(node.id == node_id for node in snapshot.nodes):
            return
        self.async_set_updated_data(replace(snapshot, nodes=nodes))

    async def _async_update_data(self) -> SourceSnapshot | ReticulumSnapshot:
        snapshot: SourceSnapshot | ReticulumSnapshot
        try:
            if self.source_type == SOURCE_TYPE_RETICULUM:
                snapshot = await self.client.get_reticulum_snapshot(self.source_id)
            elif self.source_type == SOURCE_TYPE_MESHCORE:
                snapshot = await self.client.get_meshcore_snapshot(self.source_id)
            else:
                snapshot = await self.client.get_snapshot(self.source_id)
        except MeshMonitorAuthenticationError as exc:
            raise ConfigEntryAuthFailed("MeshMonitor rejected the API token") from exc
        except (
            MeshMonitorConnectionError,
            MeshMonitorResponseError,
            MeshMonitorServerError,
        ) as exc:
            raise UpdateFailed(f"Unable to refresh MeshMonitor: {exc}") from exc

        if snapshot.errors:
            _LOGGER.debug("MeshMonitor optional endpoint errors: %s", sorted(snapshot.errors))
        return snapshot
