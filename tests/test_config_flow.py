"""Native Home Assistant tests for exact-server setup and scoped options."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_TOKEN, CONF_URL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.meshmonitor.config_flow import (
    _normalize_url,
    _replace_source_id_segment,
)
from custom_components.meshmonitor.const import (
    CONF_AUTOMATED_TX_UTILIZATION_LIMIT,
    CONF_ENABLE_AUTOMATION_VISIBILITY,
    CONF_ENABLE_DEVICE_TRACKERS,
    CONF_ENABLE_FAVORITES,
    CONF_ENABLE_MESSAGE_POLLING,
    CONF_ENABLE_NODE_MANAGEMENT,
    CONF_ENABLE_NODE_REMOVAL,
    CONF_ENABLE_SIDEBAR_PANEL,
    CONF_ENABLE_TRANSMIT,
    CONF_EXPOSE_MESSAGE_TEXT,
    CONF_MESSAGE_SCAN_INTERVAL,
    CONF_NODE_DEVICE_POLICY,
    CONF_SCAN_INTERVAL,
    CONF_SERVER_OPTIONS,
    CONF_SOURCE_ID,
    CONF_SOURCE_NAME,
    CONF_SOURCE_OPTIONS,
    CONF_SOURCE_TYPE,
    CONF_SOURCES,
    DOMAIN,
    NODE_DEVICE_POLICY_ALL,
    NODE_DEVICE_POLICY_FAVORITES,
)
from custom_components.meshmonitor.entity_policy import RegistryReconciliationPlan
from custom_components.meshmonitor.registry import server_fingerprint
from custom_components.meshmonitor.vendor_meshmonitor_client import Capabilities, Source


def _source(source_id: str, name: str, source_type: str = "meshtastic_tcp") -> Source:
    return Source(
        id=source_id,
        name=name,
        type=source_type,
        enabled=True,
        raw={},
    )


def test_source_id_segment_replacement_is_exact() -> None:
    assert (
        _replace_source_id_segment("node:server:old-id:node:key", "old-id", "new-id")
        == "node:server:new-id:node:key"
    )
    assert (
        _replace_source_id_segment("node:server:not-old-id:node:key", "old-id", "new-id")
        == "node:server:not-old-id:node:key"
    )


def _client_mock(sources: list[Source] | None = None) -> tuple[MagicMock, MagicMock]:
    """Return a reusable async-context-manager client mock."""
    factory = MagicMock()
    client = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=client)
    factory.return_value.__aexit__ = AsyncMock(return_value=None)
    client.get_sources = AsyncMock(
        return_value=sources
        or [
            _source("source-b", "MeshCore room", "meshcore_serial"),
            _source("source-a", "Meshtastic room"),
        ]
    )
    client.probe_capabilities = AsyncMock(
        return_value=Capabilities(sources=True, status=True, nodes=True)
    )
    client.get_meshcore_status = AsyncMock(return_value=MagicMock())
    client.get_meshcore_nodes = AsyncMock(return_value=[MagicMock()])
    client.get_reticulum_status = AsyncMock(return_value=MagicMock())
    return factory, client


async def _create_server_entry(
    hass: HomeAssistant,
    factory: MagicMock,
    *,
    url: str = "HTTP://MESH.TEST:80/Base/",
    token: str = "stored-secret",
):
    with (
        patch("custom_components.meshmonitor.config_flow.MeshMonitorClient", factory),
        patch(
            "custom_components.meshmonitor.config_flow.async_get_clientsession",
            return_value=MagicMock(),
        ),
        patch.object(hass.config_entries, "async_setup", new=AsyncMock(return_value=True)),
    ):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_URL: url, CONF_TOKEN: token}
        )
        await hass.async_block_till_done()
    return result


async def test_user_creates_one_server_with_every_supported_source(
    hass: HomeAssistant,
) -> None:
    """Both protocols are validated serially and stored under one server."""
    factory, client = _client_mock()
    result = await _create_server_entry(hass, factory)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    entry = result["result"]
    assert entry.title == "mesh.test/Base"
    assert entry.unique_id == server_fingerprint("http://mesh.test/Base")
    assert entry.data == {
        CONF_URL: "http://mesh.test/Base",
        CONF_TOKEN: "stored-secret",
        CONF_SOURCES: [
            {
                CONF_SOURCE_ID: "source-a",
                CONF_SOURCE_NAME: "Meshtastic room",
                CONF_SOURCE_TYPE: "meshtastic",
            },
            {
                CONF_SOURCE_ID: "source-b",
                CONF_SOURCE_NAME: "MeshCore room",
                CONF_SOURCE_TYPE: "meshcore",
            },
        ],
    }
    client.probe_capabilities.assert_awaited_once_with("source-a")
    client.get_meshcore_status.assert_awaited_once_with("source-b")
    client.get_meshcore_nodes.assert_awaited_once_with("source-b")


async def test_reticulum_source_requires_only_read_only_status(
    hass: HomeAssistant,
) -> None:
    factory, client = _client_mock([_source("rns-1", "Synthetic RNS", "reticulum_bridge")])

    result = await _create_server_entry(hass, factory)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].data[CONF_SOURCES][0][CONF_SOURCE_TYPE] == "reticulum"
    client.get_reticulum_status.assert_awaited_once_with("rns-1")
    client.probe_capabilities.assert_not_awaited()


async def test_duplicate_normalized_server_rejected_distinct_server_allowed(
    hass: HomeAssistant,
) -> None:
    """Server identity ignores normalization noise but not a distinct host."""
    first_factory, _ = _client_mock([_source("source-a", "First")])
    assert (await _create_server_entry(hass, first_factory))["type"] is FlowResultType.CREATE_ENTRY

    duplicate_factory, _ = _client_mock([_source("source-z", "Duplicate")])
    duplicate = await _create_server_entry(hass, duplicate_factory, url="http://mesh.test/Base")
    assert duplicate["type"] is FlowResultType.ABORT
    assert duplicate["reason"] == "already_configured"

    distinct_factory, _ = _client_mock([_source("source-a", "Other")])
    distinct = await _create_server_entry(hass, distinct_factory, url="http://other.test/Base")
    assert distinct["type"] is FlowResultType.CREATE_ENTRY


@pytest.mark.parametrize(
    "url",
    [
        "ftp://mesh.test",
        "http://user:secret@mesh.test",
        "http://mesh.test?private=yes",
        "http://mesh.test/#private",
        " http://mesh.test",
    ],
)
async def test_user_rejects_unsafe_server_urls(hass: HomeAssistant, url: str) -> None:
    factory, _ = _client_mock([_source("source-a", "Only")])
    result = await _create_server_entry(hass, factory, url=url)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_url"}


async def test_every_source_requires_node_visibility(hass: HomeAssistant) -> None:
    """One unreadable sibling prevents a partially validated server entry."""
    factory, client = _client_mock()
    client.get_meshcore_nodes.return_value = []
    result = await _create_server_entry(hass, factory)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "node_visibility_required"}


async def test_server_and_source_options_remain_isolated(hass: HomeAssistant) -> None:
    factory, _ = _client_mock()
    created = await _create_server_entry(hass, factory)
    entry = created["result"]

    menu = await hass.config_entries.options.async_init(entry.entry_id)
    assert menu["type"] is FlowResultType.MENU
    assert menu["menu_options"] == [
        "server_settings",
        "source_select",
        "refresh_source_inventory",
    ]

    server_form = await hass.config_entries.options.async_configure(
        menu["flow_id"], {"next_step_id": "server_settings"}
    )
    assert {field.schema for field in server_form["data_schema"].schema} == {
        CONF_ENABLE_SIDEBAR_PANEL,
        CONF_ENABLE_AUTOMATION_VISIBILITY,
        CONF_MESSAGE_SCAN_INTERVAL,
        CONF_NODE_DEVICE_POLICY,
    }
    result = await hass.config_entries.options.async_configure(
        server_form["flow_id"],
        {
            CONF_ENABLE_SIDEBAR_PANEL: False,
            CONF_ENABLE_AUTOMATION_VISIBILITY: True,
            CONF_MESSAGE_SCAN_INTERVAL: 45,
            CONF_NODE_DEVICE_POLICY: NODE_DEVICE_POLICY_FAVORITES,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY

    menu = await hass.config_entries.options.async_init(entry.entry_id)
    select = await hass.config_entries.options.async_configure(
        menu["flow_id"], {"next_step_id": "source_select"}
    )
    source_form = await hass.config_entries.options.async_configure(
        select["flow_id"], {CONF_SOURCE_ID: "source-a"}
    )
    assert {field.schema for field in source_form["data_schema"].schema} == {
        CONF_SCAN_INTERVAL,
        CONF_ENABLE_DEVICE_TRACKERS,
        CONF_ENABLE_MESSAGE_POLLING,
        CONF_EXPOSE_MESSAGE_TEXT,
        CONF_ENABLE_FAVORITES,
        CONF_ENABLE_TRANSMIT,
        CONF_ENABLE_NODE_MANAGEMENT,
        CONF_AUTOMATED_TX_UTILIZATION_LIMIT,
        CONF_ENABLE_NODE_REMOVAL,
    }
    result = await hass.config_entries.options.async_configure(
        source_form["flow_id"],
        {
            CONF_SCAN_INTERVAL: 90,
            CONF_ENABLE_DEVICE_TRACKERS: False,
            CONF_ENABLE_MESSAGE_POLLING: True,
            CONF_EXPOSE_MESSAGE_TEXT: False,
            CONF_ENABLE_FAVORITES: False,
            CONF_ENABLE_TRANSMIT: False,
            CONF_ENABLE_NODE_MANAGEMENT: False,
            CONF_AUTOMATED_TX_UTILIZATION_LIMIT: 35,
            CONF_ENABLE_NODE_REMOVAL: False,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_SERVER_OPTIONS][CONF_MESSAGE_SCAN_INTERVAL] == 45
    assert entry.options[CONF_SOURCE_OPTIONS]["source-a"][CONF_SCAN_INTERVAL] == 90
    assert "source-b" not in entry.options[CONF_SOURCE_OPTIONS]


async def test_narrowing_device_policy_requires_exact_cleanup_confirmation(
    hass: HomeAssistant,
) -> None:
    factory, _ = _client_mock()
    entry = (await _create_server_entry(hass, factory))["result"]
    hass.config_entries.async_update_entry(
        entry,
        options={
            CONF_SERVER_OPTIONS: {
                CONF_ENABLE_SIDEBAR_PANEL: True,
                CONF_ENABLE_AUTOMATION_VISIBILITY: False,
                CONF_MESSAGE_SCAN_INTERVAL: 30,
                CONF_NODE_DEVICE_POLICY: NODE_DEVICE_POLICY_ALL,
            }
        },
    )
    with patch(
        "custom_components.meshmonitor.entity_policy.registry_reconciliation_plan",
        return_value=RegistryReconciliationPlan(
            frozenset({"device-a", "device-b"}),
            frozenset({"sensor.a", "sensor.b", "sensor.c"}),
        ),
    ):
        menu = await hass.config_entries.options.async_init(entry.entry_id)
        form = await hass.config_entries.options.async_configure(
            menu["flow_id"], {"next_step_id": "server_settings"}
        )
        preview = await hass.config_entries.options.async_configure(
            form["flow_id"],
            {
                CONF_ENABLE_SIDEBAR_PANEL: True,
                CONF_ENABLE_AUTOMATION_VISIBILITY: False,
                CONF_MESSAGE_SCAN_INTERVAL: 30,
                CONF_NODE_DEVICE_POLICY: NODE_DEVICE_POLICY_FAVORITES,
            },
        )
        assert preview["type"] is FlowResultType.FORM
        assert preview["step_id"] == "confirm_registry_cleanup"
        assert preview["description_placeholders"] == {
            "devices": "2",
            "entities": "3",
        }
        refused = await hass.config_entries.options.async_configure(
            preview["flow_id"], {"confirm_registry_cleanup": False}
        )
        assert refused["errors"] == {"base": "registry_cleanup_confirmation_required"}
        result = await hass.config_entries.options.async_configure(
            refused["flow_id"], {"confirm_registry_cleanup": True}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert (
        entry.options[CONF_SERVER_OPTIONS][CONF_NODE_DEVICE_POLICY] == NODE_DEVICE_POLICY_FAVORITES
    )


async def test_inventory_refresh_is_confirmed_and_retains_absent_sources(
    hass: HomeAssistant,
) -> None:
    initial_factory, _ = _client_mock()
    entry = (await _create_server_entry(hass, initial_factory))["result"]
    hass.config_entries.async_update_entry(
        entry,
        options={
            CONF_SOURCE_OPTIONS: {
                "source-a": {CONF_SCAN_INTERVAL: 75},
                "source-b": {CONF_SCAN_INTERVAL: 120},
            }
        },
    )

    refresh_factory, refresh_client = _client_mock([_source("source-c", "New mesh")])
    with (
        patch("custom_components.meshmonitor.config_flow.MeshMonitorClient", refresh_factory),
        patch(
            "custom_components.meshmonitor.config_flow.async_get_clientsession",
            return_value=MagicMock(),
        ),
    ):
        menu = await hass.config_entries.options.async_init(entry.entry_id)
        preview = await hass.config_entries.options.async_configure(
            menu["flow_id"], {"next_step_id": "refresh_source_inventory"}
        )
        assert preview["type"] is FlowResultType.FORM
        assert preview["description_placeholders"] == {
            "added": "1",
            "replaced": "0",
            "retained": "2",
            "total": "3",
        }
        assert [item[CONF_SOURCE_ID] for item in entry.data[CONF_SOURCES]] == [
            "source-a",
            "source-b",
        ]
        result = await hass.config_entries.options.async_configure(preview["flow_id"], {})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert refresh_client.get_sources.await_count == 1
    assert [item[CONF_SOURCE_ID] for item in entry.data[CONF_SOURCES]] == [
        "source-a",
        "source-b",
        "source-c",
    ]
    assert entry.options[CONF_SOURCE_OPTIONS] == {
        "source-a": {CONF_SCAN_INTERVAL: 75},
        "source-b": {CONF_SCAN_INTERVAL: 120},
    }


async def test_inventory_refresh_replaces_recreated_source_and_migrates_options(
    hass: HomeAssistant,
) -> None:
    """A unique same-name/type source replacement retires its dead ID."""
    initial_factory, _ = _client_mock([_source("source-old", "Synthetic MeshCore", "meshcore")])
    entry = (await _create_server_entry(hass, initial_factory))["result"]
    preserved = {
        CONF_SCAN_INTERVAL: 75,
        CONF_ENABLE_TRANSMIT: False,
    }
    hass.config_entries.async_update_entry(
        entry,
        options={CONF_SOURCE_OPTIONS: {"source-old": preserved}},
    )

    refresh_factory, _ = _client_mock(
        [_source("source-new", "Synthetic MeshCore", "meshcore_serial")]
    )
    with (
        patch("custom_components.meshmonitor.config_flow.MeshMonitorClient", refresh_factory),
        patch(
            "custom_components.meshmonitor.config_flow.async_get_clientsession",
            return_value=MagicMock(),
        ),
    ):
        menu = await hass.config_entries.options.async_init(entry.entry_id)
        preview = await hass.config_entries.options.async_configure(
            menu["flow_id"], {"next_step_id": "refresh_source_inventory"}
        )
        assert preview["description_placeholders"] == {
            "added": "0",
            "replaced": "1",
            "retained": "0",
            "total": "1",
        }
        result = await hass.config_entries.options.async_configure(preview["flow_id"], {})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_SOURCES] == [
        {
            CONF_SOURCE_ID: "source-new",
            CONF_SOURCE_NAME: "Synthetic MeshCore",
            CONF_SOURCE_TYPE: "meshcore",
        }
    ]
    assert entry.options[CONF_SOURCE_OPTIONS] == {"source-new": preserved}


async def test_inventory_refresh_does_not_guess_ambiguous_replacement(
    hass: HomeAssistant,
) -> None:
    """Duplicate human identities remain non-destructive and require review."""
    initial_factory, _ = _client_mock(
        [
            _source("old-a", "Room radio"),
            _source("old-b", "Room radio"),
        ]
    )
    entry = (await _create_server_entry(hass, initial_factory))["result"]
    refresh_factory, _ = _client_mock([_source("new-a", "Room radio")])
    with (
        patch("custom_components.meshmonitor.config_flow.MeshMonitorClient", refresh_factory),
        patch(
            "custom_components.meshmonitor.config_flow.async_get_clientsession",
            return_value=MagicMock(),
        ),
    ):
        menu = await hass.config_entries.options.async_init(entry.entry_id)
        preview = await hass.config_entries.options.async_configure(
            menu["flow_id"], {"next_step_id": "refresh_source_inventory"}
        )

    assert preview["description_placeholders"] == {
        "added": "1",
        "replaced": "0",
        "retained": "2",
        "total": "3",
    }


async def test_blank_token_reconfigure_and_reauth_update_one_server(
    hass: HomeAssistant,
) -> None:
    initial_factory, _ = _client_mock([_source("source-a", "Initial")])
    entry = (await _create_server_entry(hass, initial_factory))["result"]

    reconfigure_factory, _ = _client_mock([_source("source-b", "Moved")])
    with (
        patch(
            "custom_components.meshmonitor.config_flow.MeshMonitorClient",
            reconfigure_factory,
        ),
        patch(
            "custom_components.meshmonitor.config_flow.async_get_clientsession",
            return_value=MagicMock(),
        ),
        patch.object(hass.config_entries, "async_reload", new=AsyncMock(return_value=True)),
    ):
        reconfigure = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "reconfigure", "entry_id": entry.entry_id}
        )
        result = await hass.config_entries.flow.async_configure(
            reconfigure["flow_id"], {CONF_URL: "https://mesh-new.test/", CONF_TOKEN: ""}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_URL] == "https://mesh-new.test"
    assert entry.data[CONF_TOKEN] == "stored-secret"
    assert entry.unique_id == server_fingerprint("https://mesh-new.test")
    assert entry.data[CONF_SOURCES][0][CONF_SOURCE_ID] == "source-b"

    reauth_factory, _ = _client_mock([_source("source-b", "Moved")])
    with (
        patch("custom_components.meshmonitor.config_flow.MeshMonitorClient", reauth_factory),
        patch(
            "custom_components.meshmonitor.config_flow.async_get_clientsession",
            return_value=MagicMock(),
        ),
        patch.object(hass.config_entries, "async_reload", new=AsyncMock(return_value=True)),
    ):
        reauth = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "reauth", "entry_id": entry.entry_id},
            data=dict(entry.data),
        )
        result = await hass.config_entries.flow.async_configure(
            reauth["flow_id"], {CONF_TOKEN: "replacement-secret"}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_TOKEN] == "replacement-secret"


async def test_legacy_source_entry_is_clearly_rejected(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="http://mesh.test::source-a",
        data={
            CONF_URL: "http://mesh.test",
            CONF_TOKEN: "secret",
            CONF_SOURCE_ID: "source-a",
            CONF_SOURCE_NAME: "Old source",
            CONF_SOURCE_TYPE: "meshtastic",
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "reconfigure", "entry_id": entry.entry_id}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "legacy_entry_unsupported"

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "legacy_entry_unsupported"


def test_url_normalization_preserves_case_sensitive_path_and_connection_identity() -> None:
    assert _normalize_url("HTTPS://Example.TEST:443/Api/V1///") == ("https://example.test/Api/V1")
    assert _normalize_url("https://example.test:8443/Api") == ("https://example.test:8443/Api")
    assert _normalize_url("http://[2001:db8::1]:8080/Base/") == ("http://[2001:db8::1]:8080/Base")
