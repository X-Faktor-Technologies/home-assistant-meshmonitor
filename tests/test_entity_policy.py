"""Tests for bounded Home Assistant device creation policy."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.meshmonitor.const import (
    CONF_NODE_DEVICE_POLICY,
    CONF_SERVER_OPTIONS,
    NODE_DEVICE_POLICY_ALL,
    NODE_DEVICE_POLICY_FAVORITES,
    NODE_DEVICE_POLICY_SOURCES,
)
from custom_components.meshmonitor.entity_policy import (
    async_reconcile_node_registries,
    is_source_node,
    node_entities_enabled,
    registry_reconciliation_plan,
)
from custom_components.meshmonitor.registry import (
    node_device_identifier,
    source_device_identifier,
)
from custom_components.meshmonitor.vendor_meshmonitor_client import Node


def _source(policy: str | None, local_node_id: str = "!000004d2") -> SimpleNamespace:
    server = {} if policy is None else {CONF_NODE_DEVICE_POLICY: policy}
    return SimpleNamespace(
        entry=SimpleNamespace(options={CONF_SERVER_OPTIONS: server}),
        coordinator=SimpleNamespace(
            data=SimpleNamespace(status=SimpleNamespace(local_node_id=local_node_id)),
            last_update_success=True,
        ),
    )


def _node(node_id: str, *, favorite: bool = False) -> Node:
    return Node.from_dict({"id": node_id, "isFavorite": favorite})


def test_source_identity_matches_decimal_and_meshtastic_hex_forms() -> None:
    source = _source(NODE_DEVICE_POLICY_SOURCES, local_node_id="1234")
    assert is_source_node(source, _node("!000004d2"))
    assert not is_source_node(source, _node("!000004d3"))


@pytest.mark.parametrize(
    ("policy", "favorite", "expected"),
    [
        (NODE_DEVICE_POLICY_SOURCES, False, False),
        (NODE_DEVICE_POLICY_SOURCES, True, False),
        (NODE_DEVICE_POLICY_FAVORITES, False, False),
        (NODE_DEVICE_POLICY_FAVORITES, True, True),
        (NODE_DEVICE_POLICY_ALL, False, True),
        (NODE_DEVICE_POLICY_ALL, True, True),
        (None, False, False),
        (None, True, True),
    ],
)
def test_remote_node_policy(policy: str | None, favorite: bool, expected: bool) -> None:
    assert (
        node_entities_enabled(_source(policy), _node("remote", favorite=favorite))
        is expected
    )


@pytest.mark.parametrize(
    "policy",
    [NODE_DEVICE_POLICY_SOURCES, NODE_DEVICE_POLICY_FAVORITES, NODE_DEVICE_POLICY_ALL],
)
def test_source_node_always_qualifies(policy: str) -> None:
    assert node_entities_enabled(_source(policy), _node("!000004d2"))


async def test_reconciliation_removes_only_ineligible_node_registry_objects(
    hass,
) -> None:
    """Cleanup is entry-scoped and protects source and favorite nodes."""
    entry_id = "entry"
    fingerprint = "fingerprint"
    source = _source(NODE_DEVICE_POLICY_FAVORITES, local_node_id="local")
    source.source_id = "source-a"
    source.coordinator.nodes = {
        "local": _node("local"),
        "favorite": _node("favorite", favorite=True),
        "ordinary": _node("ordinary"),
    }
    other_source = _source(NODE_DEVICE_POLICY_FAVORITES)
    other_source.source_id = "source-a:child"
    other_source.coordinator.nodes = {
        "new-identity": _node("new-identity", favorite=True)
    }
    entry = MockConfigEntry(
        domain="meshmonitor",
        entry_id=entry_id,
        data={},
        options=source.entry.options,
    )
    entry.add_to_hass(hass)
    entry.runtime_data = SimpleNamespace(
        fingerprint=fingerprint,
        sources={source.source_id: source, other_source.source_id: other_source},
    )
    source.entry = entry
    other_source.entry = entry
    devices = dr.async_get(hass)
    entities = er.async_get(hass)
    devices.async_get_or_create(
        config_entry_id=entry_id,
        identifiers={source_device_identifier(fingerprint, source.source_id)},
    )
    devices.async_get_or_create(
        config_entry_id=entry_id,
        identifiers={source_device_identifier(fingerprint, other_source.source_id)},
    )
    created = {}
    for node_id in (*source.coordinator.nodes, "deleted"):
        device = devices.async_get_or_create(
            config_entry_id=entry_id,
            identifiers={node_device_identifier(fingerprint, source.source_id, node_id)},
            via_device=source_device_identifier(fingerprint, source.source_id),
        )
        created[node_id] = device.id
        entities.async_get_or_create(
            "sensor",
            "meshmonitor",
            f"node:{fingerprint}:{source.source_id}:{node_id}:last_heard",
            config_entry=entry,
            device_id=device.id,
            suggested_object_id=f"{node_id}_last_heard",
        )
    foreign_entry = MockConfigEntry(domain="other", entry_id="other-entry", data={})
    foreign_entry.add_to_hass(hass)
    foreign = devices.async_get_or_create(
        config_entry_id="other-entry", identifiers={("other", "device")}
    )
    other_source_device = devices.async_get_or_create(
        config_entry_id=entry_id,
        identifiers={
            node_device_identifier(fingerprint, other_source.source_id, "new-identity")
        },
        via_device=source_device_identifier(fingerprint, other_source.source_id),
        name="xMesh-01",
    )

    plan = registry_reconciliation_plan(hass, entry)
    assert plan.device_ids == {created["ordinary"], created["deleted"]}
    assert len(plan.entity_ids) == 2

    result = async_reconcile_node_registries(hass, entry)
    assert result == plan
    assert devices.async_get(created["ordinary"]) is None
    assert devices.async_get(created["deleted"]) is None
    assert devices.async_get(created["local"]) is not None
    assert devices.async_get(created["favorite"]) is not None
    assert devices.async_get(other_source_device.id) is not None
    assert devices.async_get(foreign.id) is not None


async def test_reconciliation_preserves_orphans_after_failed_snapshot(hass) -> None:
    """A failed refresh cannot be interpreted as authoritative deletion."""
    entry_id = "entry"
    fingerprint = "fingerprint"
    source = _source(NODE_DEVICE_POLICY_FAVORITES)
    source.source_id = "source-a"
    source.coordinator.last_update_success = False
    source.coordinator.nodes = {}
    entry = MockConfigEntry(domain="meshmonitor", entry_id=entry_id, data={})
    entry.add_to_hass(hass)
    entry.runtime_data = SimpleNamespace(
        fingerprint=fingerprint, sources={source.source_id: source}
    )
    source.entry = entry
    devices = dr.async_get(hass)
    device = devices.async_get_or_create(
        config_entry_id=entry_id,
        identifiers={node_device_identifier(fingerprint, source.source_id, "missing")},
    )

    plan = registry_reconciliation_plan(hass, entry)

    assert plan.device_ids == frozenset()
    assert devices.async_get(device.id) is not None
