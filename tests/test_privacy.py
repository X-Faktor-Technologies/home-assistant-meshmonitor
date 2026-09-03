"""Static privacy and safety boundary checks."""

from __future__ import annotations

import json
import struct
from pathlib import Path

ROOT = Path(__file__).parents[1]
COMPONENT = ROOT / "custom_components" / "meshmonitor"


def test_manifest_is_local_polling_and_has_no_discovery() -> None:
    manifest = json.loads((COMPONENT / "manifest.json").read_text())
    assert manifest["iot_class"] == "local_polling"
    assert manifest["config_flow"] is True
    assert not {"dhcp", "zeroconf", "mqtt", "ssdp"}.intersection(manifest)
    assert (COMPONENT / "services.yaml").exists()


def test_only_explicit_bounded_write_routes_exist() -> None:
    source = "\n".join(path.read_text() for path in COMPONENT.rglob("*.py"))
    for method in (".put(", ".patch("):
        assert method not in source
    assert source.count("session.post(") == 1
    assert source.count("session.delete(") == 1
    assert '_source_path(source_id, "messages")' in source
    assert '_meshcore_path(source_id, "messages/send")' in source
    assert 'f"/api/messages/nodes/{node_num}?{urlencode' in source
    assert 'CONF_ENABLE_NODE_REMOVAL' in source
    services = (COMPONENT / "services.yaml").read_text()
    assert services.count("send_direct_message:") == 1
    assert services.count("send_channel_message:") == 1
    assert services.count("send_advert:") == 1
    assert "delete" not in services
    assert "reboot" not in services
    assert "firmware" not in services


def test_diagnostics_explicitly_redact_connection_and_source_identity() -> None:
    source = (COMPONENT / "diagnostics.py").read_text()
    assert "CONF_URL, CONF_TOKEN, CONF_SOURCE_ID, CONF_SOURCE_NAME, CONF_SOURCES" in source
    assert 'redacted_data[key] = "**REDACTED**"' in source
    assert '"source_id": "**REDACTED**"' in source
    assert '"node_count"' in source
    assert '"nodes"' not in source


def test_current_device_tracker_api_and_sparse_sensor_registration() -> None:
    tracker = (COMPONENT / "device_tracker.py").read_text()
    sensor = (COMPONENT / "sensor.py").read_text()
    assert "device_tracker.config_entry" not in tracker
    assert "_state_fingerprint" in tracker
    assert "fingerprint == self._last_written_fingerprint" in tracker
    assert "description.value_fn(node) is None" in sensor


def test_current_home_assistant_device_registry_apis() -> None:
    """Prevent reintroducing APIs deprecated by Home Assistant 2026.9."""
    source = "\n".join(
        path.read_text()
        for path in COMPONENT.rglob("*.py")
        if path.name != "registry.py"
    )
    assert ".async_get_device(" not in source
    assert ".devices.values()" not in source
    assert "via_device=" not in source
    compatibility = (COMPONENT / "registry.py").read_text()
    assert 'getattr(registry, "async_get_device_by_identifier", None)' in compatibility
    assert 'return {"via_device_id": source_device.id}' in compatibility


def test_translations_are_valid_and_reauthentication_is_present() -> None:
    strings = json.loads((COMPONENT / "strings.json").read_text())
    english = json.loads((COMPONENT / "translations" / "en.json").read_text())
    custom_recipient_name = "Send direct message to a custom recipient"
    known_node_name = "Send direct message to a known node"
    assert strings["services"]["send_direct_message"]["name"] == custom_recipient_name
    assert english["services"]["send_direct_message"]["name"] == custom_recipient_name
    assert (
        strings["device_automation"]["action_type"][
            "send_direct_message_to_known_node"
        ]
        == known_node_name
    )
    assert (
        english["device_automation"]["action_type"][
            "send_direct_message_to_known_node"
        ]
        == known_node_name
    )
    expected_extra_fields = {
        "destination_node_id": "Destination node",
        "channel": "Channel",
        "text": "Message",
        "sender": "Sender (optional)",
        "text_required": "Message text is required",
        "for": "For",
        "node": "Node (optional)",
        "metric": "Telemetry metric (optional)",
    }
    assert strings["device_automation"]["extra_fields"] == expected_extra_fields
    assert english["device_automation"]["extra_fields"] == expected_extra_fields
    assert "reauth_confirm" in strings["config"]["step"]
    assert "reauth_confirm" in english["config"]["step"]
    flow = (COMPONENT / "config_flow.py").read_text()
    assert "async_step_reauth_confirm" in flow
    assert "async_update_reload_and_abort" in flow


def test_reconfigure_and_operational_controls_are_present() -> None:
    strings = json.loads((COMPONENT / "strings.json").read_text())
    flow = (COMPONENT / "config_flow.py").read_text()
    init = (COMPONENT / "__init__.py").read_text()
    tracker = (COMPONENT / "device_tracker.py").read_text()
    assert "reconfigure" in strings["config"]["step"]
    assert "async_step_reconfigure" in flow
    server_data = strings["options"]["step"]["server_settings"]["data"]
    source_data = strings["options"]["step"]["source_settings"]["data"]
    assert {"enable_sidebar_panel", "message_scan_interval"} <= server_data.keys()
    assert {
        "scan_interval",
        "enable_device_trackers",
        "enable_message_polling",
    } <= source_data.keys()
    assert "_async_reconcile_shared_runtime" in init
    assert "CONF_ENABLE_DEVICE_TRACKERS" in tracker


def test_inline_brand_icons_match_home_assistant_sizes() -> None:
    brand = COMPONENT / "brand"
    assert _png_size(brand / "icon.png") == (256, 256)
    assert _png_size(brand / "icon@2x.png") == (512, 512)


def test_meshcore_uses_protocol_specific_read_adapter() -> None:
    flow = (COMPONENT / "config_flow.py").read_text()
    coordinator = (COMPONENT / "coordinator.py").read_text()
    client = (COMPONENT / "vendor_meshmonitor_client" / "client.py").read_text()
    assert "get_meshcore_nodes" in flow
    assert "get_meshcore_snapshot" in coordinator
    assert "meshcore/{suffix}" in client


def test_panel_is_authenticated_and_keeps_token_server_side() -> None:
    init = (COMPONENT / "__init__.py").read_text()
    websocket = (COMPONENT / "websocket_api.py").read_text()
    panel = (COMPONENT / "frontend" / "meshmonitor-panel.js").read_text()
    assert "async_register_panel" in init
    assert 'vol.Required("type"): "meshmonitor/panel"' in websocket
    assert "coordinator.data" in websocket
    assert "get_snapshot" not in websocket
    assert "CONF_TOKEN" not in websocket
    assert "token" not in panel.lower()
    assert "fetch(" not in panel
    assert 'callWS({ type: "meshmonitor/panel" })' in panel
    assert "conversation-shell" in panel
    assert "_conversationCatalog" in panel
    assert "meshmonitor.messages.pinned" in panel
    assert "meshmonitor.messages.muted" in panel
    assert 'localStorage.setItem("meshmonitor.messages.body"' not in panel
    assert "neutral-dark-tiles" in panel
    assert "hue-rotate" not in panel
    assert "tile.openstreetmap.org" in panel
    assert "meshmonitor.map.style" in (
        COMPONENT / "frontend" / "map-view.js"
    ).read_text()
    assert (COMPONENT / "frontend" / "vendor" / "leaflet" / "LICENSE").exists()
    assert 'vol.Required("type"): "meshmonitor/send_message"' in websocket
    assert "@require_admin" in websocket
    assert 'vol.Required("confirm"): "SEND"' in websocket
    transmit = (COMPONENT / "transmit.py").read_text()
    assert '"Maximum 3 messages per minute"' in transmit
    assert "reserve_message_send" in websocket


def test_inbound_pipeline_is_get_only_and_cursor_storage_has_no_body() -> None:
    coordinator = (COMPONENT / "message_coordinator.py").read_text()
    runtime = (COMPONENT / "__init__.py").read_text()
    client = (COMPONENT / "vendor_meshmonitor_client" / "client.py").read_text()
    assert "get_meshtastic_messages" in coordinator
    assert "get_meshcore_messages" in coordinator
    assert '"seen_ids"' in coordinator
    assert "message_cursor_v2" in coordinator
    assert 'data["text"] = message.text' in coordinator
    assert "self.hass.is_stopping" in coordinator
    assert "CONF_EXPOSE_MESSAGE_TEXT" in runtime
    assert "source.expose_message_text" in coordinator
    assert "async def get_meshtastic_messages" in client
    assert "async def get_meshcore_messages" in client
    actions = (COMPONENT / "actions.py").read_text()
    assert "get_meshtastic_messages" not in actions
    assert "get_meshcore_messages" not in actions


def _png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()[:24]
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", data[16:24])
