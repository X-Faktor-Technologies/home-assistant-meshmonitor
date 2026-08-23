"""GPS device trackers for MeshMonitor nodes."""

from __future__ import annotations

from homeassistant.components.device_tracker import TrackerEntity  # type: ignore[attr-defined]
from homeassistant.components.device_tracker.const import SourceType
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import (
    MeshMonitorConfigEntry,
    MeshMonitorSourceRuntime,
    registry_planning_sources,
    source_runtimes,
)
from .const import CONF_ENABLE_DEVICE_TRACKERS
from .coordinator import MeshMonitorCoordinator
from .entity import MeshMonitorNodeEntity
from .entity_policy import node_entities_enabled
from .registry import (
    entity_id_reservations,
    node_entity_id_spec,
    node_entity_unique_id,
    plan_entity_ids,
    server_fingerprint,
)
from .vendor_meshmonitor_client import Node


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MeshMonitorConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up trackers for positioned nodes and discover new ones."""
    registry = er.async_get(hass)
    reservations = entity_id_reservations(hass)
    sources = source_runtimes(entry)
    planning_sources = registry_planning_sources(hass, entry)
    for source in sources:
        if not source.options.get(CONF_ENABLE_DEVICE_TRACKERS, True):
            continue
        coordinator = source.coordinator
        known: set[str] = set()

        def _add_new_nodes(
            coordinator: MeshMonitorCoordinator = coordinator,
            source: MeshMonitorSourceRuntime = source,
            known: set[str] = known,
            planning_sources: tuple[MeshMonitorSourceRuntime, ...] = planning_sources,
        ) -> None:
            fingerprint = server_fingerprint(source.data["url"])
            specs = [
                node_entity_id_spec(
                    domain="device_tracker",
                    fingerprint=server_fingerprint(current_source.data["url"]),
                    source_id=current_source.source_id,
                    node_id=node.id,
                    long_name=node.long_name,
                    short_name=node.short_name,
                    measurement_key="location",
                )
                for current_source in planning_sources
                for node in current_source.coordinator.nodes.values()
                if node_entities_enabled(current_source, node)
            ]
            plans = plan_entity_ids(registry, specs, reservations)
            entities: list[MeshMonitorNodeTracker] = []
            for node in coordinator.nodes.values():
                if (
                    node.id in known
                    or not node_entities_enabled(source, node)
                    or node.latitude is None
                    or node.longitude is None
                ):
                    continue
                known.add(node.id)
                unique_id = node_entity_unique_id(
                    fingerprint, source.source_id, node.id, "location"
                )
                entities.append(
                    MeshMonitorNodeTracker(
                        coordinator, source, node, plans[unique_id]
                    )
                )
            if entities:
                async_add_entities(entities)

        _add_new_nodes()
        entry.async_on_unload(coordinator.async_add_listener(_add_new_nodes))


class MeshMonitorNodeTracker(MeshMonitorNodeEntity, TrackerEntity):
    """A MeshMonitor node with a valid reported position."""

    _attr_name = None
    _attr_source_type = SourceType.GPS

    def __init__(
        self,
        coordinator: MeshMonitorCoordinator,
        source: MeshMonitorSourceRuntime,
        node: Node,
        entity_id: str,
    ) -> None:
        super().__init__(coordinator, source, node, "location")
        self.entity_id = entity_id
        self._last_written_fingerprint = self._state_fingerprint()

    @property
    def latitude(self) -> float | None:
        return self.node.latitude if self.node is not None else None

    @property
    def longitude(self) -> float | None:
        return self.node.longitude if self.node is not None else None

    @property
    def location_accuracy(self) -> int:
        """Return GPS accuracy when MeshMonitor exposes it."""
        if self.node is None:
            return 0
        accuracy = self.node.raw.get("positionGpsAccuracy")
        return int(accuracy) if isinstance(accuracy, (int, float)) else 0

    def _state_fingerprint(self) -> tuple[bool, float | None, float | None, int]:
        """Return only fields that affect the tracker's HA state."""
        return (self.available, self.latitude, self.longitude, self.location_accuracy)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Avoid recorder writes when a polled position is unchanged."""
        fingerprint = self._state_fingerprint()
        if fingerprint == self._last_written_fingerprint:
            return
        self._last_written_fingerprint = fingerprint
        self.async_write_ha_state()
