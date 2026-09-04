"""Stable device, entity, and fresh entity-ID planning helpers."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, cast

from homeassistant.const import MAX_LENGTH_STATE_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_registry import EntityRegistry
from homeassistant.util import slugify

from .const import DOMAIN

MEASUREMENT_OBJECT_IDS: dict[str, str] = {
    "active_nodes": "active_nodes",
    "air_util_tx": "air_time_transmit_utilization",
    "battery": "battery_level",
    "channel_utilization": "channel_utilization",
    "connection_state": "connection_state",
    "destination_count": "destination_count",
    "hops_away": "hops_away",
    "interface_count": "interface_count",
    "last_heard": "last_heard",
    "location": "location",
    "rssi": "received_signal_strength",
    "snr": "signal_to_noise_ratio",
    "total_nodes": "total_nodes",
    "voltage": "voltage",
}

_DIGEST_LENGTHS = range(8, 65, 4)

type EntityIdReservations = dict[tuple[str, str], str]


def async_get_device_by_identifier(
    registry: dr.DeviceRegistry,
    identifier: tuple[str, str],
    config_entry_id: str,
) -> dr.DeviceEntry | None:
    """Return one entry-owned device across supported HA registry generations."""
    if lookup := getattr(registry, "async_get_device_by_identifier", None):
        return cast(dr.DeviceEntry | None, lookup(identifier, config_entry_id))
    device = registry.async_get_device(identifiers={identifier})
    if device is None or not device_belongs_to_config_entry(device, config_entry_id):
        return None
    return device


def async_get_devices(
    registry: dr.DeviceRegistry,
    identifiers: set[tuple[str, str]],
    config_entry_id: str,
) -> list[dr.DeviceEntry]:
    """Return matching entry-owned devices across HA registry generations."""
    if lookup := getattr(registry, "async_get_devices", None):
        return cast(
            list[dr.DeviceEntry],
            lookup(identifiers=identifiers, config_entry_id=config_entry_id),
        )
    device = registry.async_get_device(identifiers=identifiers)
    if device is None or not device_belongs_to_config_entry(device, config_entry_id):
        return []
    return [device]


def device_belongs_to_config_entry(device: dr.DeviceEntry, config_entry_id: str) -> bool:
    """Return whether a device has one exact config-entry owner."""
    if (owner := getattr(device, "config_entry_id", None)) is not None:
        return bool(owner == config_entry_id)
    legacy_entries = cast(set[str], getattr(device, "config_entries", set()))
    return legacy_entries == {config_entry_id}


def node_parent_device_info(
    registry: dr.DeviceRegistry,
    identifier: tuple[str, str],
    config_entry_id: str,
) -> dict[str, Any]:
    """Return the supported parent-device field for this HA registry generation."""
    source_device = async_get_device_by_identifier(registry, identifier, config_entry_id)
    if source_device is None:
        return {}
    if hasattr(registry, "async_get_device_by_identifier"):
        return {"via_device_id": source_device.id}
    return {"via_device": identifier}


def server_fingerprint(normalized_url: str) -> str:
    """Return the non-reversible exact-server registry scope."""
    return sha256(normalized_url.encode()).hexdigest()


def server_device_identifier(fingerprint: str) -> tuple[str, str]:
    """Return the server service-device identifier."""
    return (DOMAIN, f"server:{fingerprint}")


def source_device_identifier(fingerprint: str, source_id: str) -> tuple[str, str]:
    """Return a source identifier scoped beneath one exact server."""
    return (DOMAIN, f"source:{fingerprint}:{source_id}")


def node_device_identifier(
    fingerprint: str, source_id: str, node_id: str
) -> tuple[str, str]:
    """Return a node identifier scoped through its exact source and server."""
    return (DOMAIN, f"node:{fingerprint}:{source_id}:{node_id}")


def source_entity_unique_id(fingerprint: str, source_id: str, key: str) -> str:
    """Return an opaque stable source-aggregate entity identity."""
    return f"source:{fingerprint}:{source_id}:{key}"


def node_entity_unique_id(
    fingerprint: str, source_id: str, node_id: str, key: str
) -> str:
    """Return an opaque stable node entity identity."""
    return f"node:{fingerprint}:{source_id}:{node_id}:{key}"


@dataclass(frozen=True, slots=True)
class EntityIdSpec:
    """One entity's stable identity and readable fresh-ID inputs."""

    domain: str
    unique_id: str
    label: str
    measurement_key: str


def node_entity_id_spec(
    *,
    domain: str,
    fingerprint: str,
    source_id: str,
    node_id: str,
    long_name: str | None,
    short_name: str | None,
    measurement_key: str,
) -> EntityIdSpec:
    """Build a node spec using the fixed readable-label fallback order."""
    label = _first_readable_label(long_name, short_name, node_id)
    return EntityIdSpec(
        domain=domain,
        unique_id=node_entity_unique_id(
            fingerprint, source_id, node_id, measurement_key
        ),
        label=label,
        measurement_key=measurement_key,
    )


def source_entity_id_spec(
    *,
    domain: str,
    fingerprint: str,
    source_id: str,
    source_name: str | None,
    measurement_key: str,
) -> EntityIdSpec:
    """Build a source aggregate spec with a stable missing-name fallback."""
    return EntityIdSpec(
        domain=domain,
        unique_id=source_entity_unique_id(fingerprint, source_id, measurement_key),
        label=_first_readable_label(source_name, source_id),
        measurement_key=measurement_key,
    )


def plan_entity_ids(
    registry: EntityRegistry,
    specs: list[EntityIdSpec] | tuple[EntityIdSpec, ...],
    reservations: EntityIdReservations | None = None,
) -> dict[str, str]:
    """Plan deterministic full entity IDs for one complete discovery batch.

    Existing assignments for MeshMonitor unique IDs always win. Every new
    identity in a colliding readable group is digest-qualified, so discovery
    order never delegates identity to Home Assistant's numeric suffixes.
    """
    ordered = sorted(specs, key=lambda item: (item.domain, item.unique_id))
    unique_keys = {(item.domain, item.unique_id) for item in ordered}
    if len(unique_keys) != len(ordered):
        raise ValueError("duplicate entity identity in planning batch")

    result: dict[str, str] = {}
    pending: list[tuple[EntityIdSpec, str]] = []
    occupied = set(registry.entities)
    for spec in ordered:
        if spec.measurement_key not in MEASUREMENT_OBJECT_IDS:
            raise ValueError(f"unknown measurement key: {spec.measurement_key}")
        if existing := registry.async_get_entity_id(spec.domain, DOMAIN, spec.unique_id):
            result[spec.unique_id] = existing
            occupied.add(existing)
            continue
        candidate = _candidate_entity_id(spec)
        reservation_key = _reservation_unique_key(spec)
        reserved_id = reservations.get(reservation_key) if reservations else None
        if reserved_id is not None and reserved_id not in occupied:
            result[spec.unique_id] = reserved_id
            occupied.add(reserved_id)
            continue
        pending.append((spec, candidate))

    groups: dict[str, list[EntityIdSpec]] = defaultdict(list)
    for spec, candidate in pending:
        groups[candidate].append(spec)

    reserved = {
        candidate
        for candidate, group in groups.items()
        if len(group) == 1 and candidate not in occupied
        and (
            reservations is None
            or reservations.get(("candidate", candidate))
            in (None, _reservation_owner(group[0]))
        )
    }
    for candidate in sorted(reserved):
        spec = groups[candidate][0]
        result[spec.unique_id] = candidate
    occupied.update(reserved)

    for spec, candidate in pending:
        if spec.unique_id in result:
            continue
        object_id = candidate.split(".", 1)[1]
        digest = sha256(f"{spec.domain}\0{spec.unique_id}".encode()).hexdigest()
        for length in _DIGEST_LENGTHS:
            qualified = _qualified_entity_id(spec.domain, object_id, digest[:length])
            if qualified not in occupied:
                result[spec.unique_id] = qualified
                occupied.add(qualified)
                break
        else:
            raise ValueError("could not deterministically disambiguate entity ID")

    if reservations is not None:
        for spec in ordered:
            reservations[_reservation_unique_key(spec)] = result[spec.unique_id]
            reservations.setdefault(
                ("candidate", _candidate_entity_id(spec)), _reservation_owner(spec)
            )

    return result


def entity_id_reservations(hass: HomeAssistant) -> EntityIdReservations:
    """Return process-local reservations covering concurrent platform setup."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    return cast(
        EntityIdReservations,
        domain_data.setdefault("entity_id_reservations", {}),
    )


def _reservation_unique_key(spec: EntityIdSpec) -> tuple[str, str]:
    return ("unique", _reservation_owner(spec))


def _reservation_owner(spec: EntityIdSpec) -> str:
    return f"{spec.domain}\0{spec.unique_id}"


def _candidate_entity_id(spec: EntityIdSpec) -> str:
    label = slugify(spec.label)
    if not label:
        label = f"identity_{sha256(spec.unique_id.encode()).hexdigest()[:8]}"
    measurement = MEASUREMENT_OBJECT_IDS[spec.measurement_key]
    return _bounded_entity_id(spec.domain, f"mm_{label}_{measurement}")


def _qualified_entity_id(domain: str, object_id: str, digest: str) -> str:
    suffix = f"_{digest}"
    max_object_length = MAX_LENGTH_STATE_ENTITY_ID - len(domain) - 1
    return f"{domain}.{object_id[: max_object_length - len(suffix)]}{suffix}"


def _bounded_entity_id(domain: str, object_id: str) -> str:
    max_object_length = MAX_LENGTH_STATE_ENTITY_ID - len(domain) - 1
    return f"{domain}.{object_id[:max_object_length]}"


def _first_readable_label(*values: str | None) -> str:
    for value in values:
        if value and value.strip():
            return value.strip()
    raise ValueError("a stable display fallback is required")
