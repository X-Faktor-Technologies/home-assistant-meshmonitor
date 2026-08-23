# Automation examples

MeshMonitor for Home Assistant emits one event for each newly observed
non-outgoing message and one for each strict API-reported source connection
change. When the separate read-only automation option is enabled, it also emits
one event for each newly observed eligible terminal MeshMonitor automation run.
This guide documents the exact event contracts and safe patterns for turning
them into daily notifications. The integration also registers native
Home Assistant actions for one explicitly targeted radio transmission:
`meshmonitor.send_direct_message`, `meshmonitor.send_channel_message`, and
`meshmonitor.send_advert`. All three are available in the visual Automation and
Script editors; YAML is not required.

The visual editor offers eleven device triggers on each loaded MeshMonitor
source device: any/direct/channel message received, source connected or
disconnected, MeshMonitor automation completed or failed, and node discovered,
node information changed, telemetry received, or position changed. Message
triggers offer optional source-aware sender and channel filters plus a
**Message text is required** switch. Node-derived triggers offer an optional
source-local node filter, and telemetry also offers a metric filter. Each
trigger retains the event object, so action templates can read the allow-listed
values through `trigger.event.data`.

## Importable visual-editor recipes

Five conservative blueprints are included under
`blueprints/automation/meshmonitor/`:

- `direct-message-to-tts.yaml`
- `channel-message-to-mobile-notification.yaml`
- `entity-alert-to-mesh.yaml`
- `source-outage-to-mobile-notification.yaml`
- `automation-failure-to-mobile-notification.yaml`

To install one without editing YAML, open **Settings → Automations & scenes →
Blueprints**, choose **Import blueprint**, and paste the blueprint's
`source_url` from its file. After import, choose **Create automation** and fill
in the normal device, entity, channel, duration, TTS, media-player, recipient,
and notification selectors in the Home Assistant interface.

Home Assistant does not provide a supported way for a custom integration to
silently install user blueprints. Keeping import explicit prevents an
integration update from creating or changing automations behind the owner's
back.

The direct-message TTS and channel-notification recipes require **Expose
message text in events** for the selected source. They copy message bodies into
Home Assistant automation traces and into the selected TTS or mobile
notification system. Those traces, notifications, provider logs, and backups
may retain content after MeshMonitor no longer displays it. Leave text exposure
off if that is not acceptable.

The entity-alert recipe can send to either an exact recipient name/protocol ID
or an explicit numeric channel. It does not retry. Outbound messaging must be
enabled for the source, and the existing token permission, source validation,
shared three-message-per-minute limit, and replay protection all remain in
force.

## Before creating an automation

Enable **Message polling** for at least one stored source. Its exact-server
entry owns one message timer at the server-global configured interval, and
each enabled source makes one bounded stored-history read on that timer.

Leave **Expose message text in events** off unless an automation has a specific
need for message bodies. This setting belongs to one stored source; `text` is
added only when a matching reception came through an enabled source on that
exact server. The authenticated MeshMonitor panel can still display message
text when the option is off.

Terminal-run events are off by default. Enable **Read configured automations
and recent outcomes** only after deliberately granting the dedicated account
global `automations:read`. The exact-server entry owns one five-minute
coordinator and its request budget. This read-only option
cannot create, edit, enable, disable, test, or run a MeshMonitor automation.

## Event contract

The event type is `meshmonitor_message_received`. Its data is a selected,
protocol-neutral projection of locally merged, source-scoped stored history;
it is not a raw API response.

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

## Node-derived event contracts

The source-device node triggers are backed by four sanitized events:
`meshmonitor_node_discovered`, `meshmonitor_node_updated`,
`meshmonitor_telemetry_received`, and `meshmonitor_position_updated`. Every
payload contains `source_id`, `source_name`, `protocol`, and the stable
`node_id` when available. Node payloads add only the currently available
readable node name, role/model/firmware, power, signal, hop, position, and
favorite fields. Node-information changes include `changed_fields`. Telemetry
adds `telemetry_id`, `metric`, `value`, `unit`, and `timestamp` when supplied.

The first successfully loaded snapshot is a silent baseline. Later coordinator
refreshes emit only new nodes, changed allow-listed node-information fields,
changed valid positions, and telemetry records not already observed in the
bounded in-memory cursor. Setup/restart never replays the loaded inventory.
These events add no polling and never contain raw API mappings.

## Source connection event contract

The event type is `meshmonitor_source_connection_changed`. It has exactly four
fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `source_id` | string | Stable MeshMonitor source ID. |
| `protocol` | string | `meshtastic` or `meshcore`. |
| `previous_connected` | boolean | Last successfully observed explicit value. |
| `connected` | boolean | Newly observed explicit value. |

The first successful explicit boolean after setup or restart is a silent
baseline. Repeated values, null or missing values, and source refresh failures
do not fire an event or erase that baseline. The exact server/source runtime
owns its in-memory baseline. Reload reestablishes it silently; unloading the
server discards it. This tracking uses the existing source refresh and adds no
request.

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

Filter on an approved `source_id` when different sources need different
actions. Keep notification wording static when copying the source identity to
another system is unnecessary.

## Terminal automation-run event contract

The event type is `meshmonitor_automation_executed`. It has exactly six fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `run_id` | string | Stable MeshMonitor automation-run ID. |
| `automation_id` | string | Stable MeshMonitor automation-definition ID. |
| `source_id` | string or null | Source ID when MeshMonitor associates one. |
| `status` | string | `completed` or `failed`. |
| `started_at` | string or null | Valid run start time normalized to ISO 8601 UTC. |
| `updated_at` | string or null | Valid run update time normalized to ISO 8601 UTC. |

The payload excludes names, description, configuration, trigger, state, logs,
error text, creator, server, and config-entry identity. The first complete
bounded sweep is silent. A valid restart cursor may catch up a run only when
its update time is valid, no more than 24 hours old, and the bounded page proves
there is no unknown prefix. Invalid or missing cursor data and history gaps
silently rebaseline instead of replaying a backlog.

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

Use an approved `automation_id` filter when only one definition should match.
Keep notification text static unless copying operational identity and timing
metadata into Home Assistant traces and notification storage is intentional.

## Visual editor actions and triggers

In **Settings → Automations & scenes**, choose a MeshMonitor source device as
the trigger device, then select a message, connection, or automation-outcome
trigger. These device triggers are available only on source devices, not remote
node devices. Optional message filters are evaluated locally and add no API
requests. **Message text is required** matches only when the selected source
has **Expose message text in events** enabled and the event contains nonblank
text.

The action picker exposes **Send direct message to a custom recipient**, **Send
channel message**, and **Send MeshCore advert** under MeshMonitor. Each action
requires a source device. The custom-recipient action accepts either one
existing Home Assistant node device or an exact name/protocol ID. The source
picker is filtered to the Meshtastic source and MeshCore source models, and
backend validation rejects a source, a node from another source, or a stale
device selection.

For a live source-specific node inventory, choose **By type → Device → Device —
Does something on a device**, select the source device, and use **Send direct
message to a known node**. Home Assistant places native device automations
under the generic Device action type; selecting or changing the source causes
the destination dropdown to be generated from that source's current node
inventory, including nodes without Home Assistant devices.

The same Device path offers **Send channel message to a known channel** when
the source currently reports a channel inventory. Its dropdown is regenerated
from that exact source, and execution rejects a channel that disappeared after
the automation was edited. The integration-grouped **Send channel message**
action remains available for an explicit numeric channel index.

Outbound actions remain unavailable until **Enable outbound messages for this
source** is enabled in the integration options and the dedicated MeshMonitor
token has the required write permission. The panel and HA actions share a
maximum of three messages per minute and one advert per five minutes. A timeout
or ambiguous failure is never retried automatically.

Scripts can optionally capture the action response using Home Assistant's
response-variable control. A successful response includes `accepted`,
`source_id`, `protocol`, `delivery_state`, and, for messages, `message_id` when
MeshMonitor supplies one. API acceptance is not RF delivery confirmation.

Trigger action templates can read message variables such as
`trigger.event.data.text`, `sender_name`, `sender_id`, `channel`,
`channel_name`, and `is_direct`. `text` is absent unless the matching source's
text-in-events option is enabled.

## Startup and restart behavior

On first setup, the first successful poll establishes a baseline and fires no
events for existing history. The coordinator then stores only a bounded cursor
of up to 500 message IDs; it does not persist message bodies.

After a restart, Home Assistant restores that ID cursor before polling. Messages
already in the cursor are not replayed. A message that arrived while Home
Assistant was stopped can fire once after restart if it is still present in the
bounded 200-message feed and was not already stored. If the cursor storage is
missing or reset, the next successful poll is treated as a new baseline.

This behavior prevents old history from becoming a notification burst while
still allowing a genuinely new, recently received message to be noticed after
downtime. Use `message_id` only if an additional downstream system requires its
own idempotency; ordinary Home Assistant automations do not need to deduplicate
the event again.

The automation-run cursor follows the same replay-safe principle but completes
its silent baseline across the coordinator's round-robin sweep. It stores at
most 500 hashes of terminal `(automation_id, run_id)` pairs, not the raw IDs or
run content. After restart, only a valid, recent, gap-free terminal row can
emit. `pending`, `waiting`, `cancelled`, missing, and unknown statuses remain
unrecorded so a later verified `completed` or `failed` row can still emit once.

## Direct-message notification

This automation accepts only direct messages confidently classified as
incoming. Its notification is deliberately static: it does not copy message,
identity, channel, or routing fields into another store.

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

The fixed `notification_id` updates one notification instead of accumulating a
new persistent notification for every message.

## Channel notification with a cooldown

Match channels by the numeric `channel` index and, when useful, by `protocol`.
Channel names are operator-editable labels and make a less stable automation
key. Replace `0` with the visible channel index you intend to monitor.

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

The five-minute delay and `mode: single` intentionally coalesce later matching
events while the automation is running. Remove the delay if every message must
produce an action, or adjust it to the channel's expected volume.

## Privacy-preserving patterns

- Keep the text-in-events option off on every loaded MeshMonitor entry. Event
  filters cannot remove `text` from the trigger object or from automation
  traces after the event has already fired.
- Use fixed notification wording. Avoid templates that copy
  `trigger.event.data.text`, names, node IDs, source IDs, channel names, or the
  complete event object into notifications, logs, webhooks, calendars, or
  third-party services.
- Prefer `is_direct`, `direction`, `protocol`, and an approved numeric channel
  index for routing. These fields still reveal metadata in the automation
  definition or trace, but they avoid duplicating message content.
- Use a fixed persistent-notification ID, a cooldown, or a destination-side
  grouping key to bound notification volume. Do not update `input_text`,
  counters, or other recorded entity state for every message unless that
  history is an explicit requirement.
- Limit access to Home Assistant automation traces and backups. Traces can
  retain trigger data even when an action emits only a generic notification.
- Test with a synthetic or non-sensitive message, then inspect the automation
  trace and notification destination before relying on the rule. Do not paste
  raw event data into issues or public logs.

Browser-local mute controls in the MeshMonitor panel do not disable message
polling, Home Assistant events, or notifications created by these automations.
Disable the automation or change its trigger when notifications should stop.

## Troubleshooting an event automation

If no event arrives, confirm that message polling is enabled, the token has
`messages:read`, and MeshMonitor exposes at least one allowed channel. Remember
that the first successful poll is a baseline, so an existing message is not a
valid first-event test. Send or otherwise arrange a new authorized test message
only under the project's normal radio-operation approval process.

If a direct trigger does not match, inspect whether the event was classified as
`unknown` because its recipient did not match a loaded local node ID. Do not
broaden a security-sensitive automation to all unknown messages without first
understanding that routing boundary.

For coordinator ownership, polling bounds, and storage behavior, see
[Architecture and data flow](ARCHITECTURE.md). For panel behavior and local
preferences, see the [User and panel guide](USER_GUIDE.md).
