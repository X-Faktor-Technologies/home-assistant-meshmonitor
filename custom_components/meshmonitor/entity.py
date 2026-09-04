"""Shared MeshMonitor entity helpers."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import MeshMonitorSourceRuntime
from .const import DOMAIN, SOURCE_TYPE_MESHCORE, SOURCE_TYPE_RETICULUM
from .coordinator import MeshMonitorCoordinator
from .entity_policy import is_source_node, node_entities_enabled
from .registry import (
    node_device_identifier,
    node_entity_unique_id,
    server_fingerprint,
    source_device_identifier,
)
from .vendor_meshmonitor_client import Node

_NODE_ENTITY_REMOVALS = "node_entity_removals"
_NODE_ENTITY_REMOVAL_IDENTITIES = "node_entity_removal_identities"


def async_add_node_entities(
    hass: HomeAssistant,
    async_add_entities: AddEntitiesCallback,
    entities: Iterable[Entity],
    is_current: Callable[[Entity], bool] | None = None,
    on_stale: Callable[[Entity], None] | None = None,
) -> None:
    """Add entities only after matching in-flight removals have completed."""
    batch = tuple(entities)

    def current_batch() -> tuple[Entity, ...]:
        if is_current is None:
            return batch
        current: list[Entity] = []
        for entity in batch:
            if is_current(entity):
                current.append(entity)
            elif on_stale is not None:
                on_stale(entity)
        return tuple(current)

    removals: dict[str, asyncio.Task[None]] = hass.data.setdefault(DOMAIN, {}).setdefault(
        _NODE_ENTITY_REMOVALS, {}
    )
    pending = tuple(
        task
        for entity in batch
        if entity.unique_id is not None
        and (task := removals.get(entity.unique_id)) is not None
    )
    if not pending:
        if current := current_batch():
            async_add_entities(current)
        return

    async def add_after_removals() -> None:
        await asyncio.gather(*pending)
        if current := current_batch():
            async_add_entities(current)

    hass.async_create_task(
        add_after_removals(),
        "Rediscover retired MeshMonitor node entities",
        eager_start=True,
    )


async def async_wait_node_entity_removals(
    hass: HomeAssistant,
    fingerprint: str,
    source_id: str,
    node_id: str,
) -> None:
    """Wait for one node's active platform entities to finish retiring."""
    removals: dict[str, asyncio.Task[None]] = hass.data.setdefault(DOMAIN, {}).setdefault(
        _NODE_ENTITY_REMOVALS, {}
    )
    identities: dict[str, tuple[str, str, str]] = hass.data.setdefault(
        DOMAIN, {}
    ).setdefault(_NODE_ENTITY_REMOVAL_IDENTITIES, {})
    identity = (fingerprint, source_id, node_id)
    pending = tuple(
        task
        for unique_id, task in removals.items()
        if identities.get(unique_id) == identity
    )
    if pending:
        await asyncio.gather(*pending)


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
        self._removal_requested = False
        fingerprint = server_fingerprint(source.data["url"])
        self._removal_identity = (fingerprint, source.source_id, node.id)
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

    @callback
    def _handle_coordinator_update(self) -> None:
        """Retire entities removed by an authoritative successful snapshot."""
        node = self.node
        if (
            self.coordinator.last_update_success
            and (node is None or not node_entities_enabled(self.source, node))
        ):
            if not self._removal_requested:
                self._removal_requested = True
                removals: dict[str, asyncio.Task[None]] = self.hass.data.setdefault(
                    DOMAIN, {}
                ).setdefault(_NODE_ENTITY_REMOVALS, {})
                identities: dict[str, tuple[str, str, str]] = self.hass.data.setdefault(
                    DOMAIN, {}
                ).setdefault(_NODE_ENTITY_REMOVAL_IDENTITIES, {})
                task = self.hass.async_create_task(
                    self.async_remove(force_remove=True),
                    f"Remove retired MeshMonitor node entity {self.unique_id}",
                    eager_start=True,
                )
                if self.unique_id is not None:
                    unique_id = self.unique_id
                    removals[unique_id] = task
                    identities[unique_id] = self._removal_identity

                    def clear_removal(done: asyncio.Task[None]) -> None:
                        if removals.get(unique_id) is done:
                            removals.pop(unique_id, None)
                            identities.pop(unique_id, None)

                    task.add_done_callback(clear_removal)
            return
        super()._handle_coordinator_update()
