"""Constants for the MeshMonitor integration."""

from datetime import timedelta

DOMAIN = "meshmonitor"
PANEL_URL_PATH = "meshmonitor"

CONF_SOURCE_ID = "source_id"
CONF_SOURCE_NAME = "source_name"
CONF_SOURCE_TYPE = "source_type"
CONF_SOURCES = "sources"
CONF_SERVER_OPTIONS = "server"
CONF_SOURCE_OPTIONS = "sources"

SOURCE_TYPE_MESHCORE = "meshcore"
SOURCE_TYPE_MESHTASTIC = "meshtastic"
SOURCE_TYPE_RETICULUM = "reticulum"

DEFAULT_SCAN_INTERVAL = timedelta(seconds=60)
MESSAGE_SCAN_INTERVAL = timedelta(seconds=30)
AUTOMATION_SCAN_INTERVAL = timedelta(minutes=5)
SERVER_HEALTH_SCAN_INTERVAL = timedelta(minutes=5)

CONF_ENABLE_DEVICE_TRACKERS = "enable_device_trackers"
CONF_ENABLE_MESSAGE_POLLING = "enable_message_polling"
CONF_ENABLE_AUTOMATION_VISIBILITY = "enable_automation_visibility"
CONF_ENABLE_SIDEBAR_PANEL = "enable_sidebar_panel"
CONF_EXPOSE_MESSAGE_TEXT = "expose_message_text"
CONF_ENABLE_TRANSMIT = "enable_transmit"
CONF_ENABLE_FAVORITES = "enable_favorites"
CONF_ENABLE_NODE_MANAGEMENT = "enable_node_management"
CONF_AUTOMATED_TX_UTILIZATION_LIMIT = "automated_tx_utilization_limit"
CONF_ENABLE_NODE_REMOVAL = "enable_node_removal"
CONF_NODE_DEVICE_POLICY = "node_device_policy"
CONF_MESSAGE_SCAN_INTERVAL = "message_scan_interval"
CONF_SCAN_INTERVAL = "scan_interval"
EVENT_MESSAGE_RECEIVED = "meshmonitor_message_received"
EVENT_SOURCE_CONNECTION_CHANGED = "meshmonitor_source_connection_changed"
EVENT_AUTOMATION_EXECUTED = "meshmonitor_automation_executed"
EVENT_NODE_DISCOVERED = "meshmonitor_node_discovered"
EVENT_NODE_UPDATED = "meshmonitor_node_updated"
EVENT_TELEMETRY_RECEIVED = "meshmonitor_telemetry_received"
EVENT_POSITION_UPDATED = "meshmonitor_position_updated"

NOTIFICATION_SCOPE_ALL = "all"
NOTIFICATION_SCOPE_CHANNEL = "channel"
NOTIFICATION_SCOPE_DIRECT = "direct"

NODE_DEVICE_POLICY_SOURCES = "sources"
NODE_DEVICE_POLICY_FAVORITES = "favorites"
NODE_DEVICE_POLICY_ALL = "all"
DEFAULT_NODE_DEVICE_POLICY = NODE_DEVICE_POLICY_FAVORITES

PLATFORMS = ["sensor", "device_tracker"]
