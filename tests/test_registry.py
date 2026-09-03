"""Deterministic tests for MeshMonitor registry identity planning."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

from homeassistant.components.device_tracker import DOMAIN as TRACKER_DOMAIN
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.meshmonitor.const import DOMAIN
from custom_components.meshmonitor.registry import (
    MEASUREMENT_OBJECT_IDS,
    async_get_device_by_identifier,
    async_get_devices,
    device_belongs_to_config_entry,
    node_device_identifier,
    node_entity_id_spec,
    node_entity_unique_id,
    node_parent_device_info,
    plan_entity_ids,
    server_device_identifier,
    server_fingerprint,
    source_device_identifier,
    source_entity_id_spec,
    source_entity_unique_id,
)

SERVER_A = server_fingerprint("https://mesh-a.test/base")
SERVER_B = server_fingerprint("https://mesh-b.test/base")


def test_modern_device_registry_helpers_are_config_entry_scoped() -> None:
    """Supported HA registries use owned lookups and concrete parent IDs."""
    identifier = (DOMAIN, "source:server:source-a")
    device = SimpleNamespace(id="source-device", config_entry_id="entry")
    registry = Mock()
    registry.async_get_device_by_identifier.return_value = device
    registry.async_get_devices.return_value = [device]

    assert async_get_device_by_identifier(registry, identifier, "entry") is device
    assert async_get_devices(registry, {identifier}, "entry") == [device]
    assert device_belongs_to_config_entry(device, "entry") is True
    assert node_parent_device_info(registry, identifier, "entry") == {
        "via_device_id": "source-device"
    }
    registry.async_get_device_by_identifier.assert_called_with(identifier, "entry")
    registry.async_get_devices.assert_called_once_with(
        identifiers={identifier}, config_entry_id="entry"
    )


def _node_spec(
    *,
    server: str = SERVER_A,
    source: str = "source-a",
    node: str = "!01020304",
    long_name: str | None = "1st Watchung Mtn. Solar",
    short_name: str | None = "SOLAR",
    key: str = "snr",
    domain: str = SENSOR_DOMAIN,
):
    return node_entity_id_spec(
        domain=domain,
        fingerprint=server,
        source_id=source,
        node_id=node,
        long_name=long_name,
        short_name=short_name,
        measurement_key=key,
    )


def test_server_scoped_registry_identities() -> None:
    """Equal source and node IDs cannot merge across exact servers."""
    assert len(SERVER_A) == 64
    assert SERVER_A == server_fingerprint("https://mesh-a.test/base")
    assert SERVER_A != SERVER_B
    assert server_device_identifier(SERVER_A) == (DOMAIN, f"server:{SERVER_A}")
    assert source_device_identifier(SERVER_A, "shared") != source_device_identifier(
        SERVER_B, "shared"
    )
    assert node_device_identifier(SERVER_A, "shared", "node") != node_device_identifier(
        SERVER_A, "other", "node"
    )
    assert node_entity_unique_id(SERVER_A, "shared", "node", "battery") != (
        node_entity_unique_id(SERVER_B, "shared", "node", "battery")
    )
    assert source_entity_unique_id(SERVER_A, "shared", "total_nodes") != (
        source_entity_unique_id(SERVER_B, "shared", "total_nodes")
    )


def test_readable_measurements_missing_names_and_length_bound(hass: HomeAssistant) -> None:
    """The vocabulary is expanded, fallback is stable, and IDs fit HA limits."""
    registry = er.async_get(hass)
    specs = [
        _node_spec(key=key, domain=TRACKER_DOMAIN if key == "location" else SENSOR_DOMAIN)
        for key in MEASUREMENT_OBJECT_IDS
        if key not in {"active_nodes", "total_nodes"}
    ]
    specs.extend(
        source_entity_id_spec(
            domain=SENSOR_DOMAIN,
            fingerprint=SERVER_A,
            source_id="source-a",
            source_name="Lab source",
            measurement_key=key,
        )
        for key in (
            "active_nodes",
            "connection_state",
            "destination_count",
            "interface_count",
            "total_nodes",
        )
    )
    specs.append(
        _node_spec(node="!abcdef01", long_name=None, short_name=None, key="battery")
    )
    specs.append(_node_spec(node="node-z", long_name="Z" * 400, key="voltage"))

    planned = plan_entity_ids(registry, specs)

    snr = next(spec for spec in specs if spec.measurement_key == "snr")
    assert planned[snr.unique_id] == (
        "sensor.mm_1st_watchung_mtn_solar_signal_to_noise_ratio"
    )
    missing = specs[-2]
    assert planned[missing.unique_id] == "sensor.mm_abcdef01_battery_level"
    assert all(entity_id.split(".", 1)[1].startswith("mm_") for entity_id in planned.values())
    assert all(len(entity_id) <= 255 for entity_id in planned.values())


def test_all_readable_collisions_get_stable_qualifiers(hass: HomeAssistant) -> None:
    """Names, punctuation, sources, and servers are batch-order independent."""
    registry = er.async_get(hass)
    specs = [
        _node_spec(node="node-1", long_name="Same Name", source="source-a"),
        _node_spec(node="node-2", long_name="Same--Name", source="source-a"),
        _node_spec(node="node-1", long_name="Same Name", source="source-b"),
        _node_spec(node="node-1", long_name="Same Name", source="source-a", server=SERVER_B),
    ]

    forward = plan_entity_ids(registry, specs)
    reverse = plan_entity_ids(registry, list(reversed(specs)))

    assert forward == reverse
    assert len(set(forward.values())) == 4
    assert all(
        value.startswith("sensor.mm_same_name_signal_to_noise_ratio_")
        for value in forward.values()
    )
    assert all(len(value.rsplit("_", 1)[1]) == 8 for value in forward.values())
    assert all(not value.endswith(("_2", "_3", "_4")) for value in forward.values())


def test_foreign_collision_and_existing_assignment_win(hass: HomeAssistant) -> None:
    """Registry collisions qualify fresh IDs while reloads reuse assignments."""
    registry = er.async_get(hass)
    spec = _node_spec(key="rssi")
    readable_id = "sensor.mm_1st_watchung_mtn_solar_received_signal_strength"
    registry.async_get_or_create(
        SENSOR_DOMAIN,
        "foreign_integration",
        "foreign-unique-id",
        suggested_object_id=readable_id.split(".", 1)[1],
    )

    planned = plan_entity_ids(registry, [spec])
    assert planned[spec.unique_id].startswith(f"{readable_id}_")
    assert not planned[spec.unique_id].endswith("_2")

    assigned = registry.async_get_or_create(
        SENSOR_DOMAIN,
        DOMAIN,
        spec.unique_id,
        suggested_object_id=planned[spec.unique_id].split(".", 1)[1],
    )
    renamed = _node_spec(key="rssi", long_name="A completely changed name")
    assert plan_entity_ids(registry, [renamed])[spec.unique_id] == assigned.entity_id


def test_process_reservations_prevent_concurrent_platform_suffixes(
    hass: HomeAssistant,
) -> None:
    """Separate server batches reserve readable bases before HA registration."""
    registry = er.async_get(hass)
    reservations: dict[tuple[str, str], str] = {}
    first = _node_spec(server=SERVER_A, node="node-1", long_name="Shared label")
    second = _node_spec(server=SERVER_B, node="node-1", long_name="Shared label")

    first_id = plan_entity_ids(registry, [first], reservations)[first.unique_id]
    second_id = plan_entity_ids(registry, [second], reservations)[second.unique_id]

    assert first_id == "sensor.mm_shared_label_signal_to_noise_ratio"
    assert second_id.startswith(f"{first_id}_")
    assert not second_id.endswith("_2")
    assert plan_entity_ids(registry, [first], reservations)[first.unique_id] == first_id


def test_duplicate_batch_identity_and_unknown_measurement_fail(hass: HomeAssistant) -> None:
    """Incomplete planner inputs fail before Home Assistant can suffix them."""
    registry = er.async_get(hass)
    spec = _node_spec()
    try:
        plan_entity_ids(registry, [spec, spec])
    except ValueError as err:
        assert str(err) == "duplicate entity identity in planning batch"
    else:
        raise AssertionError("duplicate identity was accepted")

    unknown = _node_spec(key="not_a_measurement")
    try:
        plan_entity_ids(registry, [unknown])
    except ValueError as err:
        assert str(err) == "unknown measurement key: not_a_measurement"
    else:
        raise AssertionError("unknown measurement was accepted")
