# Automation examples

This guide shows practical ways to turn mesh activity into Home Assistant
automations. You can do all of the common tasks in Home Assistant's visual
automation editor. The YAML examples are here for people who prefer to copy,
paste, and customize them.

You can build automations for things such as:

- a new direct or channel message;
- a source connecting or disconnecting;
- a node appearing or changing;
- new telemetry or a new position;
- a MeshMonitor automation completing or failing; and
- sending a direct message, channel message, or MeshCore advert.

Start with the blueprints below if you want the easiest setup. The exact event
fields and more advanced details are listed later in this guide.

## Easiest option: import a blueprint

The repository includes twelve ready-made automation recipes:

- [Speak a direct message](../blueprints/automation/meshmonitor/direct-message-to-tts.yaml)
- [Send a channel message to a phone](../blueprints/automation/meshmonitor/channel-message-to-mobile-notification.yaml)
- [Send a Home Assistant entity alert over the mesh](../blueprints/automation/meshmonitor/entity-alert-to-mesh.yaml)
- [Warn when a source stays disconnected](../blueprints/automation/meshmonitor/source-outage-to-mobile-notification.yaml)
- [Warn when a MeshMonitor automation fails](../blueprints/automation/meshmonitor/automation-failure-to-mobile-notification.yaml)
- [Forward one mesh channel to another](../blueprints/automation/meshmonitor/channel-bridge.yaml)
- [Reply to an exact direct-message command](../blueprints/automation/meshmonitor/direct-message-responder.yaml)
- [Send a low-battery warning over the mesh](../blueprints/automation/meshmonitor/low-battery-to-mesh.yaml)
- [Welcome a newly discovered node](../blueprints/automation/meshmonitor/new-node-welcome.yaml)
- [Reply to a range-test request](../blueprints/automation/meshmonitor/range-test-responder.yaml)
- [Send a weather alert over the mesh](../blueprints/automation/meshmonitor/weather-alert-to-mesh.yaml)
- [Announce when a tracker leaves a zone](../blueprints/automation/meshmonitor/zone-exit-to-mesh.yaml)

To use one:

1. Open **Settings → Automations & scenes → Blueprints**.
2. Select **Import blueprint**.
3. Open one of the blueprint links above, copy its GitHub page address, and
   paste that address into Home Assistant.
4. Select **Create automation**.
5. Choose the source, notification device, speaker, channel, or other requested
   options.

You do not need to edit YAML.

Blueprints are not installed automatically. This keeps you in control of every
automation that is added to Home Assistant.

The direct-message TTS and channel-notification blueprints need **Expose
message text in events** to be enabled for the selected source. Be aware that
this can copy message text into automation traces, notifications, speech
services, logs, and backups. Leave it off if mesh messages should stay only in
MeshMonitor and its Home Assistant panel.

The entity-alert blueprint sends a mesh message when a Home Assistant entity
needs attention. You can send it to one recipient or one numbered channel.
Outbound messaging must be enabled, and the API token needs permission to send
messages. The integration will not retry a message when the result is unclear.

## Before creating an automation

For message automations, enable **Message polling** for the source you want to
monitor. The MeshMonitor API user also needs `messages:read` access to that
source and channel.

Leave **Expose message text in events** off unless the automation truly needs
the message body. You can still read messages in the MeshMonitor panel while
this option is off.

To react when a MeshMonitor automation completes or fails, enable **Read
configured automations and recent outcomes** and give the API user global
`automations:read` permission. This is read-only: Home Assistant cannot create,
change, test, or run MeshMonitor automations.

For automations that send over the mesh, enable **Outbound messages** for the
source and give the API user `messages:write`. Test with a harmless message and
check the destination before relying on the automation.

## Message event reference

You can skip this section when using a blueprint or the visual editor. It is a
reference for advanced filters and templates.

The event name is `meshmonitor_message_received`. It contains only the useful,
approved fields below; it does not expose MeshMonitor's raw API response.

| Field | Type | Meaning |
| --- | --- | --- |
| `message_id` | string | Stable protocol identity derived from the verified stored-message contract. |
| `protocol` | string | `meshtastic` or `meshcore`, inferred from the receptions. |
| `source_ids` | list of strings | Source IDs on which MeshMonitor received the message. |
| `sender_id` | string or null | Protocol-specific sender node ID or public key. |
| `sender_name` | string or null | Sender name supplied by MeshMonitor. |
| `recipient_id` | string or null | Protocol-specific recipient or broadcast ID. |
| `channel` | integer or null | Channel index; direct messages use null or `-1`. |
| `channel_name` | string or null | Channel label supplied by MeshMonitor. |
| `is_direct` | boolean | True when `channel` is null or `-1`. |
| `timestamp` | number, string, or null | MeshMonitor's source timestamp, passed through without conversion. |
| `direction` | string | `incoming` or `unknown`; outgoing messages are suppressed. |
| `rssi`, `snr` | number, optional | Best available matching reception signal values. |
| `hop_count` | integer, optional | Packet hop count when reported; otherwise the sender node's latest known hop count. |
| `via_mqtt` | boolean, optional | Present only when the message record explicitly classifies MQTT transport. |
| `direct_rf` | boolean, optional | Present only when packet hop data is available; true means zero-hop and not explicitly MQTT. |
| `sender_role`, `sender_hardware_model` | string, optional | Already-loaded sender metadata. |
| `sender_battery_level`, `sender_voltage` | number, optional | Already-loaded sender power data. |
| `sender_latitude`, `sender_longitude`, `sender_altitude` | number, optional | Already-loaded sender position. |
| `text` | string, optional | Present only when a matching source's text-in-events option is enabled. |

Treat all fields as potentially sensitive. Node IDs and names, source IDs,
channel metadata, routing, and timestamps can disclose activity even without
message text. Do not assume that a timestamp is always an ISO string or always
an epoch number.

For a direct message, `direction: incoming` means the recipient matched a
local node ID from a loaded entry. A direct message that cannot be classified
that way has `direction: unknown`. Channel messages are classified as incoming.
The coordinator never emits this received-message event for a message it can
identify as outgoing.

## Node event reference

Node triggers use four privacy-filtered events:
`meshmonitor_node_discovered`, `meshmonitor_node_updated`,
`meshmonitor_telemetry_received`, and `meshmonitor_position_updated`. Every
payload contains `source_id`, `source_name`, `protocol`, and the stable
`node_id` when available. Node payloads add only the currently available
readable node name, role/model/firmware, power, signal, hop, position, and
favorite fields. Node-information changes include `changed_fields`. Telemetry
adds `telemetry_id`, `metric`, `value`, `unit`, and `timestamp` when supplied.

When Home Assistant starts, it quietly records the current state instead of
treating every existing node as new. After that, events fire only for new or
changed information. Restarting Home Assistant does not replay the whole node
list. These events use the normal refresh cycle and never include raw API data.

## Source connection example

The event type is `meshmonitor_source_connection_changed`. It has exactly four
fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `source_id` | string | Stable MeshMonitor source ID. |
| `protocol` | string | `meshtastic` or `meshcore`. |
| `previous_connected` | boolean | Last successfully observed explicit value. |
| `connected` | boolean | Newly observed explicit value. |

After setup or restart, Home Assistant quietly records the source's current
connection state. The event fires only when MeshMonitor later reports a real
change between connected and disconnected. A temporary refresh error does not
pretend that the source disconnected.

The payload deliberately omits source name, server and config-entry identity,
coordinator errors, node data, and an integration timestamp. Home Assistant's
event time records when the already API-reported transition was observed.

```yaml
automation:
  - alias: "Mesh source disconnected"
    mode: single
    triggers:
      - trigger: event
        event_type: meshmonitor_source_connection_changed
        event_data:
          connected: false
    actions:
      - action: persistent_notification.create
        data:
          notification_id: meshmonitor_source_connection
          title: "Mesh source unavailable"
          message: "A configured mesh source reported that it disconnected."
```

Add a `source_id` filter if different sources should run different actions.
Use a generic notification message unless the source name or ID is genuinely
useful outside Home Assistant.

## MeshMonitor automation result example

The event type is `meshmonitor_automation_executed`. It has exactly six fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `run_id` | string | Stable MeshMonitor automation-run ID. |
| `automation_id` | string | Stable MeshMonitor automation-definition ID. |
| `source_id` | string or null | Source ID when MeshMonitor associates one. |
| `status` | string | `completed` or `failed`. |
| `started_at` | string or null | Valid run start time normalized to ISO 8601 UTC. |
| `updated_at` | string or null | Valid run update time normalized to ISO 8601 UTC. |

The event leaves out automation names, configuration, logs, errors, creator
details, and server information. Home Assistant quietly records existing runs
when the feature is first enabled so it does not flood you with old alerts.

```yaml
automation:
  - alias: "MeshMonitor automation failed"
    mode: queued
    max: 3
    triggers:
      - trigger: event
        event_type: meshmonitor_automation_executed
        event_data:
          status: failed
    actions:
      - action: persistent_notification.create
        data:
          notification_id: meshmonitor_automation_failure
          title: "MeshMonitor automation failed"
          message: "A configured MeshMonitor automation reported a failure."
```

Add an `automation_id` filter if you care about only one MeshMonitor
automation. Keep the notification generic unless you intentionally want IDs or
times copied into Home Assistant's stored traces and notifications.

## Build one in the visual editor

In **Settings → Automations & scenes**, create an automation and choose
**Device** as the trigger. Select a MeshMonitor source device, then choose the
message, connection, node, telemetry, position, or automation-result trigger
you want. These triggers appear on source devices, not on remote node devices.

Message triggers can be narrowed to a sender or channel. **Message text is
required** works only when **Expose message text in events** is enabled and the
message actually contains text.

Under MeshMonitor actions, you can choose **Send direct message to a custom
recipient**, **Send channel message**, or **Send MeshCore advert**. Select the
source device first. For a direct message, choose an existing node device or
enter the exact recipient name or protocol ID.

To pick from the source's current nodes, choose **By type → Device → Device —
Does something on a device**, select the source, and then choose **Send direct
message to a known node**. The recipient list updates from that source's
current node list, including nodes that do not have their own Home Assistant
device.

The same Device menu offers **Send channel message to a known channel** when
the source reports its channels. You can also use the regular **Send channel
message** action and enter a channel number yourself.

Sending stays unavailable until **Enable outbound messages for this source** is
turned on and the API token has the required write permission. The panel and
automations share a limit of three messages per minute and one advert every
five minutes. A timeout or unclear failure is never retried automatically;
check the conversation before sending again.

Advanced scripts can save the action response with Home Assistant's response
variable feature. An accepted API request does not prove that the radio message
reached its destination.

Trigger action templates can read message variables such as
`trigger.event.data.text`, `sender_name`, `sender_id`, `channel`,
`channel_name`, and `is_direct`. `text` is absent unless the matching source's
text-in-events option is enabled.

## What happens after a restart

On first setup, Home Assistant quietly records the messages that already exist.
It does not send a notification for each old message. It remembers up to 500
message IDs for duplicate protection, but it does not store message bodies in
that restart record.

After a restart, known messages are not replayed. A genuinely new message that
arrived while Home Assistant was off may still trigger once after startup. If
the saved duplicate-protection data is missing, Home Assistant safely treats
the next update as a fresh starting point instead of replaying old history.

Ordinary Home Assistant automations do not need to remove duplicates again.
Use `message_id` only when another system needs its own duplicate protection.

MeshMonitor automation results follow the same rule: existing results are
quietly recorded, and only a newly confirmed `completed` or `failed` result
fires an event.

## Example: notify me about a direct message

This automation creates one Home Assistant notification when a new incoming
direct message arrives. It does not copy the message text or sender details.

```yaml
automation:
  - alias: "Mesh direct message received"
    mode: single
    triggers:
      - trigger: event
        event_type: meshmonitor_message_received
        event_data:
          is_direct: true
          direction: incoming
    actions:
      - action: persistent_notification.create
        data:
          notification_id: meshmonitor_direct_message
          title: "Mesh message received"
          message: "A direct mesh message arrived. Open the MeshMonitor panel."
```

Because the notification uses one fixed ID, new messages update the same alert
instead of filling Home Assistant with separate notifications.

## Example: channel alert with a cooldown

Replace `0` with the channel number you want to monitor. Channel numbers are
safer automation filters than channel names because names can be changed.

```yaml
automation:
  - alias: "Mesh channel activity"
    mode: single
    max_exceeded: silent
    triggers:
      - trigger: event
        event_type: meshmonitor_message_received
        event_data:
          protocol: meshtastic
          is_direct: false
          channel: 0
          direction: incoming
    actions:
      - action: persistent_notification.create
        data:
          notification_id: meshmonitor_channel_activity
          title: "Mesh channel activity"
          message: "New activity arrived on the monitored mesh channel."
      - delay: "00:05:00"
```

The five-minute delay prevents a busy channel from creating an alert for every
message. Remove it if you want every message to trigger, or change the delay to
fit your channel.

## Keep notifications private

- Keep **Expose message text in events** off unless an automation needs the
  message body. Automation traces may keep the text after the event fires.
- Use fixed notification wording. Avoid templates that copy
  `trigger.event.data.text`, names, node IDs, source IDs, channel names, or the
  complete event object into notifications, logs, webhooks, calendars, or
  third-party services.
- Prefer simple filters such as direct versus channel, protocol, direction, and
  channel number. They avoid copying message content.
- Use one fixed notification ID or a cooldown to control alert volume. Avoid
  saving every message into another recorded Home Assistant entity unless you
  truly need that history.
- Limit access to Home Assistant automation traces and backups. Traces can
  retain trigger data even when an action emits only a generic notification.
- Test with a synthetic or non-sensitive message, then inspect the automation
  trace and notification destination before relying on the rule. Do not paste
  raw event data into issues or public logs.

Browser-local mute controls in the MeshMonitor panel do not disable message
polling, Home Assistant events, or notifications created by these automations.
Disable the automation or change its trigger when notifications should stop.

## If an automation does not run

Check that message polling is enabled, the token has `messages:read`, and the
API user can see the source and channel. Old messages do not trigger after
setup, so test with a new, non-sensitive message that you are authorized to
send.

If a direct-message trigger still does not match, the recipient may not match a
local node loaded in Home Assistant. Check the event in Home Assistant's
developer tools before making the trigger broader.

For coordinator ownership, polling bounds, and storage behavior, see
[Architecture and data flow](ARCHITECTURE.md). For panel behavior and local
preferences, see the [User and panel guide](USER_GUIDE.md).
