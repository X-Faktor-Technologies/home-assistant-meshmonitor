"""Home Assistant registry exposure policy for MeshMonitor nodes."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from . import MeshMonitorSourceRuntime, server_options
from .const import (
    CONF_NODE_DEVICE_POLICY,
    DEFAULT_NODE_DEVICE_POLICY,
    NODE_DEVICE_POLICY_ALL,
    NODE_DEVICE_POLICY_FAVORITES,
)
from .registry import (
    async_get_device_by_identifier,
    device_belongs_to_config_entry,
    node_device_identifier,
    source_device_identifier,
)
from .vendor_meshmonitor_client import Node

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from . import MeshMonitorConfigEntry


@dataclass(frozen=True, slots=True)
class RegistryReconciliationPlan:
    """Exact HA registry objects made ineligible by one node policy."""

    device_ids: frozenset[str]
    entity_ids: frozenset[str]


def _identifier_variants(value: object) -> set[str]:
    """Return comparable decimal/hex variants without guessing source scope."""
    text = str(value or "").strip().casefold().removeprefix("!")
    if not text:
        return set()
    variants = {text, text.lstrip("0") or "0"}
    try:
        number = int(text, 10 if text.isdecimal() else 16)
    except ValueError:
        return variants
    variants.update({str(number), f"{number:x}", f"{number:08x}"})
    return variants


def is_source_node(source: MeshMonitorSourceRuntime, node: Node) -> bool:
    """Return whether a node is the exact locally monitored source identity."""
    snapshot = source.coordinator.data
    local_node_id = getattr(getattr(snapshot, "status", None), "local_node_id", None)
    return bool(
        local_node_id
        and _identifier_variants(node.id) & _identifier_variants(local_node_id)
    )


def node_entities_enabled(
    source: MeshMonitorSourceRuntime, node: Node, policy: str | None = None
) -> bool:
    """Return whether this node should create HA entities and a device."""
    if is_source_node(source, node):
        return True
    if policy is None:
        policy = server_options(source.entry).get(
            CONF_NODE_DEVICE_POLICY, DEFAULT_NODE_DEVICE_POLICY
        )
    if policy == NODE_DEVICE_POLICY_ALL:
        return True
    return policy == NODE_DEVICE_POLICY_FAVORITES and bool(node.is_favorite)


def registry_reconciliation_plan(
    hass: HomeAssistant,
    entry: MeshMonitorConfigEntry,
    policy: str | None = None,
    source_ids: Collection[str] | None = None,
) -> RegistryReconciliationPlan:
    """Plan exact ineligible or deleted node objects from complete snapshots."""
    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)
    fingerprint = entry.runtime_data.fingerprint
    device_ids: set[str] = set()
    for source in entry.runtime_data.sources.values():
        if source_ids is not None and source.source_id not in source_ids:
            continue
        if (
            getattr(source.coordinator, "last_update_success", False) is not True
            or source.coordinator.data is None
        ):
            continue
        nodes = source.coordinator.nodes
        if not isinstance(nodes, Mapping):
            continue
        active_identifiers = {
            node_device_identifier(fingerprint, source.source_id, node.id)
            for node in nodes.values()
        }
        for node in nodes.values():
            if node_entities_enabled(source, node, policy):
                continue
            identifier = node_device_identifier(fingerprint, source.source_id, node.id)
            device = async_get_device_by_identifier(
                device_registry,
                identifier, entry.entry_id
            )
            if device is not None:
                device_ids.add(device.id)

        source_device = async_get_device_by_identifier(
            device_registry,
            source_device_identifier(fingerprint, source.source_id),
            entry.entry_id,
        )
        if source_device is None:
            continue
        for device in dr.async_entries_for_config_entry(device_registry, entry.entry_id):
            if device.via_device_id != source_device.id:
                continue
            scoped_identifiers = {
                (domain, identifier)
                for domain, identifier in device.identifiers
                if domain == "meshmonitor"
                and identifier.startswith(f"node:{fingerprint}:")
            }
            if scoped_identifiers and scoped_identifiers.isdisjoint(active_identifiers):
                device_ids.add(device.id)

    entity_ids = {
        item.entity_id
        for item in entity_registry.entities.values()
        if item.config_entry_id == entry.entry_id and item.device_id in device_ids
    }
    return RegistryReconciliationPlan(frozenset(device_ids), frozenset(entity_ids))


def async_reconcile_node_registries(
    hass: HomeAssistant,
    entry: MeshMonitorConfigEntry,
    source_ids: Collection[str] | None = None,
) -> RegistryReconciliationPlan:
    """Remove only node objects retired by an authoritative source snapshot."""
    plan = registry_reconciliation_plan(hass, entry, source_ids=source_ids)
    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)
    for entity_id in sorted(plan.entity_ids):
        entity_registry.async_remove(entity_id)
    for device_id in sorted(plan.device_ids):
        device = device_registry.async_get(device_id)
        if device is not None and device_belongs_to_config_entry(
            device, entry.entry_id
        ):
            device_registry.async_remove_device(device_id)
    return plan
