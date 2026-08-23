"""Shared MeshMonitor entity helpers."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import MeshMonitorSourceRuntime
from .const import SOURCE_TYPE_MESHCORE, SOURCE_TYPE_RETICULUM
from .coordinator import MeshMonitorCoordinator
from .entity_policy import is_source_node
from .registry import (
    node_device_identifier,
    node_entity_unique_id,
    server_fingerprint,
    source_device_identifier,
)
from .vendor_meshmonitor_client import Node


def source_device_info(source: MeshMonitorSourceRuntime) -> DeviceInfo:
    """Build device registry information for a MeshMonitor source."""
    fingerprint = server_fingerprint(source.data["url"])
    meshcore = source.source_type == SOURCE_TYPE_MESHCORE
    reticulum = source.source_type == SOURCE_TYPE_RETICULUM
    return DeviceInfo(
        identifiers={source_device_identifier(fingerprint, source.source_id)},
        name=source.title,
        manufacturer="MeshMonitor",
        model=(
            "Reticulum source"
            if reticulum
            else "MeshCore source"
            if meshcore
            else "Meshtastic source"
        ),
        configuration_url=source.data["url"],
    )


def node_device_info(source: MeshMonitorSourceRuntime, node: Node) -> DeviceInfo:
    """Build device registry information for a Meshtastic node."""
    if is_source_node(source, node):
        return source_device_info(source)
    fingerprint = server_fingerprint(source.data["url"])
    meshcore = source.source_type == SOURCE_TYPE_MESHCORE
    return DeviceInfo(
        identifiers={node_device_identifier(fingerprint, source.source_id, node.id)},
        name=node.long_name or node.short_name or node.id,
        manufacturer="MeshCore" if meshcore else "Meshtastic",
        model=node.hardware_model or ("MeshCore contact" if meshcore else "Mesh node"),
        sw_version=node.firmware_version,
        via_device=source_device_identifier(fingerprint, source.source_id),
    )


class MeshMonitorNodeEntity(CoordinatorEntity[MeshMonitorCoordinator]):
    """Base class for an entity belonging to a MeshMonitor node."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: MeshMonitorCoordinator,
        source: MeshMonitorSourceRuntime,
        node: Node,
        key: str,
    ) -> None:
        super().__init__(coordinator)
        self.source = source
        self.node_id = node.id
        fingerprint = server_fingerprint(source.data["url"])
        self._attr_unique_id = node_entity_unique_id(fingerprint, source.source_id, node.id, key)
        self._attr_device_info = node_device_info(source, node)

    @property
    def node(self) -> Node | None:
        """Return this entity's node from coordinator memory."""
        return self.coordinator.nodes.get(self.node_id)

    @property
    def available(self) -> bool:
        """Mark a node entity unavailable if it vanishes or refresh fails."""
        return super().available and self.node is not None
