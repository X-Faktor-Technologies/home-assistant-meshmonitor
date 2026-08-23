"""Native action contract tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_TOKEN, CONF_URL
from homeassistant.core import Context, HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import service as service_helper
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.meshmonitor import MeshMonitorRuntimeData, MeshMonitorSourceRuntime
from custom_components.meshmonitor.actions import (
    ATTR_CHANNEL,
    ATTR_DESTINATION_DEVICE_ID,
    ATTR_RECIPIENT,
    ATTR_REPLY_ID,
    ATTR_SOURCE_DEVICE_ID,
    ATTR_TEXT,
    SEND_DIRECT_SCHEMA,
    SERVICE_SEND_CHANNEL_MESSAGE,
    SERVICE_SEND_DIRECT_MESSAGE,
    _async_send_advert,
    _async_send_channel_message,
    _async_send_direct_message,
    async_register_actions,
)
from custom_components.meshmonitor.const import (
    CONF_AUTOMATED_TX_UTILIZATION_LIMIT,
    CONF_ENABLE_TRANSMIT,
    CONF_SOURCE_OPTIONS,
    DOMAIN,
)
from custom_components.meshmonitor.registry import (
    node_device_identifier,
    server_fingerprint,
    source_device_identifier,
)
from custom_components.meshmonitor.vendor_meshmonitor_client import (
    MeshMonitorPermissionError,
    Node,
)


def _runtime(
    hass: HomeAssistant, *, protocol: str = "meshtastic", transmit: bool = True
) -> tuple[MeshMonitorSourceRuntime, str, str]:
    source_id = "source-a"
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_URL: "http://mesh.invalid", CONF_TOKEN: "token", "sources": []},
        options={CONF_SOURCE_OPTIONS: {source_id: {CONF_ENABLE_TRANSMIT: transmit}}},
    )
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    node_id = "a" * 64 if protocol == "meshcore" else "!1234abcd"
    node = Node.from_dict({"id": node_id, "longName": "Remote"})
    client = Mock()
    source = MeshMonitorSourceRuntime(
        entry,
        client,
        Mock(nodes={node_id: node}),
        source_id,
        "Source A",
        protocol,
    )
    fingerprint = server_fingerprint(entry.data[CONF_URL])
    entry.runtime_data = MeshMonitorRuntimeData(client, fingerprint, {source_id: source})
    devices = dr.async_get(hass)
    source_device = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={source_device_identifier(fingerprint, source_id)},
    )
    node_device = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={node_device_identifier(fingerprint, source_id, node_id)},
    )
    return source, source_device.id, node_device.id


def _call(
    hass: HomeAssistant,
    service: str,
    data: dict[str, object],
    *,
    response: bool = True,
    context_id: str = "01JTESTACTIONCONTEXT00000000",
) -> ServiceCall:
    return ServiceCall(
        hass,
        DOMAIN,
        service,
        data,
        Context(id=context_id),
        return_response=response,
    )


@pytest.mark.asyncio
async def test_reticulum_source_sends_one_supported_lxmf_direct_message(
    hass: HomeAssistant,
) -> None:
    source, source_device_id, _node_device_id = _runtime(
        hass, protocol="reticulum", transmit=True
    )
    source.client.send_reticulum_message = AsyncMock(
        return_value=SimpleNamespace(id="lxmf-message", state="sending")
    )
    source.coordinator.data = SimpleNamespace(
        destinations=(
            SimpleNamespace(
                destination_hash="a" * 32,
                display_name="Friendly LXMF peer",
            ),
        )
    )
    call = _call(
        hass,
        SERVICE_SEND_DIRECT_MESSAGE,
        {
            ATTR_SOURCE_DEVICE_ID: source_device_id,
            ATTR_RECIPIENT: "Friendly LXMF peer",
            ATTR_TEXT: "Hello over LXMF",
        },
    )

    result = await _async_send_direct_message(call)

    source.client.send_reticulum_message.assert_awaited_once_with(
        source.source_id,
        "Hello over LXMF",
        to_destination_hash="a" * 32,
    )
    assert result == {
        "accepted": True,
        "source_id": source.source_id,
        "protocol": "reticulum",
        "message_id": "lxmf-message",
        "delivery_state": "sending",
    }


@pytest.mark.asyncio
async def test_registers_all_ui_actions_with_visual_editor_descriptions(
    hass: HomeAssistant,
) -> None:
    async_register_actions(hass)
    assert hass.services.has_service(DOMAIN, SERVICE_SEND_DIRECT_MESSAGE)
    assert hass.services.has_service(DOMAIN, SERVICE_SEND_CHANNEL_MESSAGE)
    assert hass.services.has_service(DOMAIN, "send_advert")
    descriptions = (await service_helper.async_get_all_descriptions(hass))[DOMAIN]
    assert set(descriptions) == {
        SERVICE_SEND_DIRECT_MESSAGE,
        SERVICE_SEND_CHANNEL_MESSAGE,
        "send_advert",
    }
    assert descriptions[SERVICE_SEND_DIRECT_MESSAGE]["fields"][ATTR_SOURCE_DEVICE_ID]["selector"][
        "device"
    ]["filter"] == [
        {"integration": DOMAIN, "model": "Meshtastic source"},
        {"integration": DOMAIN, "model": "MeshCore source"},
        {"integration": DOMAIN, "model": "Reticulum source"},
    ]
    assert descriptions[SERVICE_SEND_DIRECT_MESSAGE]["fields"][ATTR_DESTINATION_DEVICE_ID][
        "selector"
    ]["device"]["filter"] == [
        {"integration": DOMAIN, "manufacturer": "Meshtastic"},
        {"integration": DOMAIN, "manufacturer": "MeshCore"},
    ]
    assert descriptions["send_advert"]["fields"][ATTR_SOURCE_DEVICE_ID]["selector"]["device"][
        "filter"
    ] == [{"integration": DOMAIN, "model": "MeshCore source"}]
    assert (
        descriptions[SERVICE_SEND_DIRECT_MESSAGE]["fields"][ATTR_TEXT]["selector"]["text"][
            "multiline"
        ]
        is True
    )


@pytest.mark.asyncio
async def test_direct_action_resolves_devices_and_returns_response(
    hass: HomeAssistant,
) -> None:
    source, source_device_id, node_device_id = _runtime(hass)
    source.client.send_meshtastic_message = AsyncMock(
        return_value=SimpleNamespace(message_id="message-1", delivery_state="accepted")
    )

    result = await _async_send_direct_message(
        _call(
            hass,
            SERVICE_SEND_DIRECT_MESSAGE,
            {
                ATTR_SOURCE_DEVICE_ID: source_device_id,
                ATTR_DESTINATION_DEVICE_ID: node_device_id,
                ATTR_TEXT: "automation test",
            },
        )
    )

    source.client.send_meshtastic_message.assert_awaited_once_with(
        "source-a", "automation test", to_node_id="!1234abcd"
    )
    assert result == {
        "accepted": True,
        "source_id": "source-a",
        "protocol": "meshtastic",
        "message_id": "message-1",
        "delivery_state": "accepted",
    }


@pytest.mark.asyncio
async def test_automation_transmit_pauses_above_source_airtime_ceiling(
    hass: HomeAssistant,
) -> None:
    source, source_device_id, node_device_id = _runtime(hass)
    source.entry.options[CONF_SOURCE_OPTIONS][source.source_id][
        CONF_AUTOMATED_TX_UTILIZATION_LIMIT
    ] = 30
    source.coordinator.data.status.channel_utilization = 30.5
    source.client.send_meshtastic_message = AsyncMock()

    with pytest.raises(ServiceValidationError, match="paused at 30.5%"):
        await _async_send_direct_message(
            _call(
                hass,
                SERVICE_SEND_DIRECT_MESSAGE,
                {
                    ATTR_SOURCE_DEVICE_ID: source_device_id,
                    ATTR_DESTINATION_DEVICE_ID: node_device_id,
                    ATTR_TEXT: "blocked automation",
                },
            )
        )

    source.client.send_meshtastic_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_direct_action_resolves_exact_source_local_name(
    hass: HomeAssistant,
) -> None:
    source, source_device_id, _ = _runtime(hass)
    source.client.send_meshtastic_message = AsyncMock(
        return_value=SimpleNamespace(message_id="message-2", delivery_state="accepted")
    )

    await _async_send_direct_message(
        _call(
            hass,
            SERVICE_SEND_DIRECT_MESSAGE,
            {
                ATTR_SOURCE_DEVICE_ID: source_device_id,
                ATTR_RECIPIENT: "remote",
                ATTR_TEXT: "name lookup",
            },
        )
    )

    source.client.send_meshtastic_message.assert_awaited_once_with(
        "source-a", "name lookup", to_node_id="!1234abcd"
    )


@pytest.mark.asyncio
async def test_direct_action_preserves_meshtastic_reply_linkage(
    hass: HomeAssistant,
) -> None:
    source, source_device_id, _ = _runtime(hass)
    source.client.send_meshtastic_message = AsyncMock(
        return_value=SimpleNamespace(message_id="message-2", delivery_state="accepted")
    )

    await _async_send_direct_message(
        _call(
            hass,
            SERVICE_SEND_DIRECT_MESSAGE,
            {
                ATTR_SOURCE_DEVICE_ID: source_device_id,
                ATTR_RECIPIENT: "!1234abcd",
                ATTR_TEXT: "linked reply",
                ATTR_REPLY_ID: 3726281140,
            },
        )
    )

    source.client.send_meshtastic_message.assert_awaited_once_with(
        "source-a",
        "linked reply",
        to_node_id="!1234abcd",
        reply_id=3726281140,
    )


@pytest.mark.asyncio
async def test_direct_action_rejects_ambiguous_source_local_name(
    hass: HomeAssistant,
) -> None:
    source, source_device_id, _ = _runtime(hass)
    second = Node.from_dict({"id": "!abcdef12", "shortName": "Remote"})
    source.coordinator.nodes[second.id] = second

    with pytest.raises(ServiceValidationError, match="ambiguous"):
        await _async_send_direct_message(
            _call(
                hass,
                SERVICE_SEND_DIRECT_MESSAGE,
                {
                    ATTR_SOURCE_DEVICE_ID: source_device_id,
                    ATTR_RECIPIENT: "REMOTE",
                    ATTR_TEXT: "do not guess",
                },
            )
        )


def test_direct_schema_requires_exactly_one_destination_method() -> None:
    common = {ATTR_SOURCE_DEVICE_ID: "source", ATTR_TEXT: "test"}
    with pytest.raises(vol.Invalid, match="exactly one"):
        SEND_DIRECT_SCHEMA(common)
    with pytest.raises(vol.Invalid, match="exactly one"):
        SEND_DIRECT_SCHEMA(
            {
                **common,
                ATTR_DESTINATION_DEVICE_ID: "device",
                ATTR_RECIPIENT: "!1234abcd",
            }
        )
    assert (
        SEND_DIRECT_SCHEMA({**common, ATTR_RECIPIENT: " !1234abcd "})[ATTR_RECIPIENT] == "!1234abcd"
    )


@pytest.mark.asyncio
async def test_channel_action_validates_protocol_range(hass: HomeAssistant) -> None:
    source, source_device_id, _ = _runtime(hass)
    source.client.send_meshtastic_message = AsyncMock(side_effect=ValueError("channel invalid"))

    with pytest.raises(ServiceValidationError, match="channel invalid"):
        await _async_send_channel_message(
            _call(
                hass,
                SERVICE_SEND_CHANNEL_MESSAGE,
                {
                    ATTR_SOURCE_DEVICE_ID: source_device_id,
                    ATTR_CHANNEL: 8,
                    ATTR_TEXT: "automation test",
                },
            )
        )


@pytest.mark.asyncio
async def test_action_requires_per_source_transmit_gate(hass: HomeAssistant) -> None:
    _, source_device_id, node_device_id = _runtime(hass, transmit=False)
    with pytest.raises(ServiceValidationError, match="disabled"):
        await _async_send_direct_message(
            _call(
                hass,
                SERVICE_SEND_DIRECT_MESSAGE,
                {
                    ATTR_SOURCE_DEVICE_ID: source_device_id,
                    ATTR_DESTINATION_DEVICE_ID: node_device_id,
                    ATTR_TEXT: "blocked",
                },
            )
        )


@pytest.mark.asyncio
async def test_advert_requires_meshcore_source(hass: HomeAssistant) -> None:
    _, source_device_id, _ = _runtime(hass)
    with pytest.raises(ServiceValidationError, match="MeshCore"):
        await _async_send_advert(
            _call(hass, "send_advert", {ATTR_SOURCE_DEVICE_ID: source_device_id})
        )


@pytest.mark.asyncio
async def test_interactive_radio_action_requires_administrator(
    hass: HomeAssistant,
) -> None:
    _, source_device_id, node_device_id = _runtime(hass)
    hass.auth.async_get_user = AsyncMock(return_value=SimpleNamespace(is_admin=False))
    call = ServiceCall(
        hass,
        DOMAIN,
        SERVICE_SEND_DIRECT_MESSAGE,
        {
            ATTR_SOURCE_DEVICE_ID: source_device_id,
            ATTR_DESTINATION_DEVICE_ID: node_device_id,
            ATTR_TEXT: "blocked",
        },
        Context(user_id="not-admin"),
    )
    with pytest.raises(ServiceValidationError, match="administrator"):
        await _async_send_direct_message(call)


@pytest.mark.asyncio
async def test_action_maps_upstream_permission_loss_without_retry(
    hass: HomeAssistant,
) -> None:
    """A revoked MeshMonitor write grant fails once and is never retried."""
    source, source_device_id, node_device_id = _runtime(hass)
    source.client.send_meshtastic_message = AsyncMock(side_effect=MeshMonitorPermissionError())

    with pytest.raises(ServiceValidationError, match="lacks the required write"):
        await _async_send_direct_message(
            _call(
                hass,
                SERVICE_SEND_DIRECT_MESSAGE,
                {
                    ATTR_SOURCE_DEVICE_ID: source_device_id,
                    ATTR_DESTINATION_DEVICE_ID: node_device_id,
                    ATTR_TEXT: "blocked upstream",
                },
            )
        )

    assert source.client.send_meshtastic_message.await_count == 1


@pytest.mark.asyncio
async def test_actions_share_replay_and_three_message_rate_guard(
    hass: HomeAssistant,
) -> None:
    """Automation actions use the same bounded transmit state as the panel."""
    source, source_device_id, node_device_id = _runtime(hass)
    source.client.send_meshtastic_message = AsyncMock(
        return_value=SimpleNamespace(message_id="accepted", delivery_state="accepted")
    )
    data = {
        ATTR_SOURCE_DEVICE_ID: source_device_id,
        ATTR_DESTINATION_DEVICE_ID: node_device_id,
        ATTR_TEXT: "bounded",
    }

    await _async_send_direct_message(
        _call(hass, SERVICE_SEND_DIRECT_MESSAGE, data, context_id="context-1")
    )
    with pytest.raises(ServiceValidationError, match="Duplicate"):
        await _async_send_direct_message(
            _call(hass, SERVICE_SEND_DIRECT_MESSAGE, data, context_id="context-1")
        )

    for index in (2, 3):
        await _async_send_direct_message(
            _call(
                hass,
                SERVICE_SEND_DIRECT_MESSAGE,
                data,
                context_id=f"context-{index}",
            )
        )
    with pytest.raises(ServiceValidationError, match="Maximum 3 messages"):
        await _async_send_direct_message(
            _call(hass, SERVICE_SEND_DIRECT_MESSAGE, data, context_id="context-4")
        )

    assert source.client.send_meshtastic_message.await_count == 3
