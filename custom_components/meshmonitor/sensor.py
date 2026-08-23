"""Sensor platform for MeshMonitor."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfElectricPotential
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import (
    MeshMonitorConfigEntry,
    MeshMonitorSourceRuntime,
    registry_planning_sources,
    source_runtimes,
)
from .const import SOURCE_TYPE_RETICULUM
from .coordinator import MeshMonitorCoordinator
from .entity import MeshMonitorNodeEntity, source_device_info
from .entity_policy import node_entities_enabled
from .registry import (
    EntityIdSpec,
    entity_id_reservations,
    node_entity_id_spec,
    node_entity_unique_id,
    plan_entity_ids,
    server_fingerprint,
    source_entity_id_spec,
    source_entity_unique_id,
)
from .vendor_meshmonitor_client import Node, ReticulumSnapshot


@dataclass(frozen=True, kw_only=True)
class MeshMonitorSensorDescription(SensorEntityDescription):
    """Describe a MeshMonitor node sensor."""

    value_fn: Callable[[Node], Any]


NODE_SENSORS: tuple[MeshMonitorSensorDescription, ...] = (
    MeshMonitorSensorDescription(
        key="last_heard",
        translation_key="last_heard",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda node: _as_datetime(node.last_heard),
    ),
    MeshMonitorSensorDescription(
        key="battery",
        translation_key="battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda node: node.battery_level,
    ),
    MeshMonitorSensorDescription(
        key="voltage",
        translation_key="voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda node: node.voltage,
    ),
    MeshMonitorSensorDescription(
        key="snr",
        translation_key="snr",
        native_unit_of_measurement="dB",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda node: node.snr,
    ),
    MeshMonitorSensorDescription(
        key="rssi",
        translation_key="rssi",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement="dBm",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda node: node.rssi,
    ),
    MeshMonitorSensorDescription(
        key="channel_utilization",
        translation_key="channel_utilization",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda node: node.channel_utilization,
    ),
    MeshMonitorSensorDescription(
        key="air_util_tx",
        translation_key="air_util_tx",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda node: node.air_util_tx,
    ),
    MeshMonitorSensorDescription(
        key="hops_away",
        translation_key="hops_away",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda node: node.hops_away,
    ),
)

SOURCE_SENSORS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="total_nodes",
        translation_key="total_nodes",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="active_nodes",
        translation_key="active_nodes",
        state_class=SensorStateClass.MEASUREMENT,
    ),
)

RETICULUM_SOURCE_SENSORS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="connection_state",
        translation_key="connection_state",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="interface_count",
        translation_key="interface_count",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="destination_count",
        translation_key="destination_count",
        state_class=SensorStateClass.MEASUREMENT,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MeshMonitorConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up node sensors and discover newly observed nodes."""
    registry = er.async_get(hass)
    reservations = entity_id_reservations(hass)
    sources = source_runtimes(entry)
    planning_sources = registry_planning_sources(hass, entry)
    plans = _sensor_entity_id_plans(registry, planning_sources, reservations)
    for source in sources:
        coordinator = source.coordinator
        fingerprint = server_fingerprint(source.data["url"])
        known: set[tuple[str, str]] = set()

        source_descriptions = (
            RETICULUM_SOURCE_SENSORS
            if source.source_type == SOURCE_TYPE_RETICULUM
            else SOURCE_SENSORS
        )
        async_add_entities(
            MeshMonitorSourceSensor(
                coordinator,
                source,
                description,
                plans[source_entity_unique_id(fingerprint, source.source_id, description.key)],
            )
            for description in source_descriptions
        )

        def _add_new_nodes(
            coordinator: MeshMonitorCoordinator = coordinator,
            source: MeshMonitorSourceRuntime = source,
            known: set[tuple[str, str]] = known,
            fingerprint: str = fingerprint,
            planning_sources: tuple[MeshMonitorSourceRuntime, ...] = planning_sources,
        ) -> None:
            plans = _sensor_entity_id_plans(registry, planning_sources, reservations)
            entities: list[MeshMonitorNodeSensor] = []
            for node in coordinator.nodes.values():
                if not node_entities_enabled(source, node):
                    continue
                for description in NODE_SENSORS:
                    identity = (node.id, description.key)
                    if identity in known or description.value_fn(node) is None:
                        continue
                    known.add(identity)
                    unique_id = node_entity_unique_id(
                        fingerprint, source.source_id, node.id, description.key
                    )
                    entities.append(
                        MeshMonitorNodeSensor(
                            coordinator, source, node, description, plans[unique_id]
                        )
                    )
            if entities:
                async_add_entities(entities)

        _add_new_nodes()
        entry.async_on_unload(coordinator.async_add_listener(_add_new_nodes))


def _sensor_entity_id_plans(
    registry: er.EntityRegistry,
    sources: tuple[MeshMonitorSourceRuntime, ...],
    reservations: dict[tuple[str, str], str] | None = None,
) -> dict[str, str]:
    """Plan the complete stable sensor batch across every server child source."""
    specs: list[EntityIdSpec] = []
    for source in sources:
        fingerprint = server_fingerprint(source.data["url"])
        source_descriptions = (
            RETICULUM_SOURCE_SENSORS
            if source.source_type == SOURCE_TYPE_RETICULUM
            else SOURCE_SENSORS
        )
        specs.extend(
            source_entity_id_spec(
                domain="sensor",
                fingerprint=fingerprint,
                source_id=source.source_id,
                source_name=source.source_name,
                measurement_key=description.key,
            )
            for description in source_descriptions
        )
        specs.extend(
            node_entity_id_spec(
                domain="sensor",
                fingerprint=fingerprint,
                source_id=source.source_id,
                node_id=node.id,
                long_name=node.long_name,
                short_name=node.short_name,
                measurement_key=description.key,
            )
            for node in source.coordinator.nodes.values()
            if node_entities_enabled(source, node)
            for description in NODE_SENSORS
        )
    return plan_entity_ids(registry, specs, reservations)


class MeshMonitorNodeSensor(MeshMonitorNodeEntity, SensorEntity):
    """A sensor backed only by the coordinator's in-memory snapshot."""

    entity_description: MeshMonitorSensorDescription

    def __init__(
        self,
        coordinator: MeshMonitorCoordinator,
        source: MeshMonitorSourceRuntime,
        node: Node,
        description: MeshMonitorSensorDescription,
        entity_id: str,
    ) -> None:
        super().__init__(coordinator, source, node, description.key)
        self.entity_description = description
        self.source_type = source.source_type
        self.entity_id = entity_id

    @property
    def native_value(self) -> Any:
        """Return the current sensor value."""
        if (node := self.node) is None:
            return None
        return self.entity_description.value_fn(node)


class MeshMonitorSourceSensor(CoordinatorEntity[MeshMonitorCoordinator], SensorEntity):
    """Aggregate sensor attached to the MeshMonitor source device."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: MeshMonitorCoordinator,
        source: MeshMonitorSourceRuntime,
        description: SensorEntityDescription,
        entity_id: str,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self.source_type = source.source_type
        fingerprint = server_fingerprint(source.data["url"])
        self._attr_unique_id = source_entity_unique_id(
            fingerprint, source.source_id, description.key
        )
        self._attr_device_info = source_device_info(source)
        self.entity_id = entity_id

    @property
    def native_value(self) -> Any:
        """Return the current aggregate count."""
        if self.coordinator.data is None:
            return None
        if self.source_type == SOURCE_TYPE_RETICULUM:
            if not isinstance(self.coordinator.data, ReticulumSnapshot):
                return None
            status = self.coordinator.data.status
            if self.entity_description.key == "connection_state":
                return "connected" if status.connected else "disconnected"
            if self.entity_description.key == "interface_count":
                return status.interface_count
            if self.entity_description.key == "destination_count":
                return status.destination_count
            return None
        if isinstance(self.coordinator.data, ReticulumSnapshot):
            return None
        network = self.coordinator.data.network
        if network is None:
            if self.entity_description.key == "total_nodes":
                return len(self.coordinator.data.nodes)
            return None
        if self.entity_description.key == "total_nodes":
            return network.total_nodes
        return network.active_nodes


def _as_datetime(value: int | float | str | None) -> datetime | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(value, UTC)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    return None
