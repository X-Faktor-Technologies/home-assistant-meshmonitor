# MeshMonitor for Home Assistant

Bring Meshtastic, MeshCore, and Reticulum into one Home Assistant workspace for everyday
mesh monitoring, mapping, conversations, and safe operator actions. MeshMonitor
remains the source of truth for radios and technical administration; this
integration presents its API-backed data where dashboards, automations, and
daily routines already live.

> [!IMPORTANT]
> Version 0.16.0 is an unreleased pre-1.0 source candidate. A public source
> repository, tagged release, HACS distribution, and client package are separate
> promotion steps. Do not treat an untagged checkout as a supported release.

## What you get

| Area | Meshtastic | MeshCore | Reticulum | Home Assistant experience |
| --- | --- | --- | --- | --- |
| Source health | Yes | Yes | Yes | Protocol-native source cards and diagnostic entities. |
| Server version | Yes | Yes | Yes | Compact per-server version, health, and automation statistics. |
| Node inventory | Yes | Yes | Destinations | Searchable, sortable inventory without inventing unavailable fields. |
| Positions | Yes | Yes | Not currently | Optional GPS trackers and a unified interactive map. |
| Conversations | Yes | Yes | LXMF | Permission-filtered history with browser-local pin, mute, and unread state. |
| Automations | Yes | Yes | Inbound events | Native HA events, triggers, actions, and importable blueprints. |
| Daily writes | Optional | Optional | No | Explicitly enabled favorites, node requests, and reviewed sends. |
| Administration | Link only | Link only | MeshMonitor-owned | Radio, identity, and server administration stay in MeshMonitor. |

Reticulum 0.16.0 support is intentionally read-only: source connection,
interface/destination counts, and LXMF history/events are included. Home
Assistant does not send LXMF, probe paths, configure RNodes, or manage
Reticulum identities.

The built-in sidebar panel includes Overview, Messages, Nodes, and Map workspaces.
Opening the panel, changing filters, or toggling a
stored-data layer does not add API traffic. Normal updates come from shared,
serialized coordinators rather than one request per entity.

## Screenshots

Every value shown below is synthetic. The images render the real panel code but
contain no live Home Assistant or mesh data; see the
[screenshot provenance notes](docs/images/README.md).

![MeshMonitor Overview with a healthy daily-console headline, four at-a-glance metrics, and protocol-aware synthetic source-health cards](docs/images/panel-overview.png)

![MeshMonitor Messages workspace with a calm dark conversation timeline, selected conversation, source and protocol filters, synthetic senders, compact provenance, and guarded compose controls](docs/images/panel-conversations.png)

![MeshMonitor Nodes workspace with synthetic Meshtastic and MeshCore nodes, protocol colors, sortable health columns, and search controls](docs/images/panel-nodes.png)

![MeshMonitor tile-free Map workspace with the built-in style selector, grouped controls, and four synthetic protocol-colored nodes](docs/images/panel-map.png)

## Product boundary

Home Assistant is the daily mesh console. MeshMonitor owns source creation,
transports, radio and module configuration, channel secrets, credentials,
firmware, remote administration, backups, and database maintenance. The
integration exposes only narrowly scoped API methods; it has no generic API
passthrough. Optional radio writes are explicit, permission-gated, rate-limited,
disabled by default, and never retried after an ambiguous response.

Radio/configuration administration, live telemetry requests, reactions, and
telemetry polls, discovery, reboot, purge, and other administrative operations
are not included. The integration exposes only the features documented in this
README and the user guide; undocumented MeshMonitor API routes are outside its
supported surface.

## Architecture

```text
MeshMonitor API
  └─ one exact-server config entry and API client
       ├─ one serialized coordinator per stored source
       │    ├─ Home Assistant source and node entities
       │    ├─ sanitized in-memory panel snapshots
       │    └─ source connection baselines and events
       ├─ one server-owned message coordinator
       │    ├─ source-scoped reads merged into the Conversations view
       │    └─ privacy-gated Home Assistant events
       └─ one server health coordinator
            ├─ health every five minutes
            └─ cached update status no more than every six hours

Home Assistant administrator
  └─ authenticated panel WebSocket
       └─ explicit bounded favorite, history, or message method
            └─ MeshMonitor API
```

Each config entry represents one exact MeshMonitor server and retains its
bounded supported-source inventory. Each stored source owns an independent
coordinator and child device; enabled sources contribute one bounded
stored-history read to the server's message timer. The browser talks only to
authenticated Home Assistant WebSocket commands. Periodic reads are owned by
coordinators.
Browser-requested reads are limited to bounded node telemetry/link-quality,
position-trail, or stored traceroute/history results. Daily writes are named
operations with their own option, permission check, and safety limits.

See [architecture and data flow](docs/ARCHITECTURE.md) for coordinator
ownership, shared polling, panel transport, privacy boundaries, lifecycle
behavior, and the complete bounded-write path.

## Requirements

- Home Assistant 2026.8.0 or newer.
- A network-reachable MeshMonitor 4.14.x or 4.15.x server. Reticulum support is
  verified against 4.15.1.
- At least one visible Meshtastic, MeshCore, or Reticulum source.
- A dedicated MeshMonitor API user and token. Start read-only and add an
  optional write grant only for the corresponding explicitly enabled feature.
- Browser access from Home Assistant to the configured MeshMonitor address if
  you want direct administration links to work.

The integration currently carries a reviewed vendored copy of the typed
`meshmonitor-api-client`, so it does not depend on manually populating HAOS
`/config/deps`. The vendored copy will be replaced only after the standalone
client has an approved, installable package release.

## Least-privilege permissions

Permission names below are MeshMonitor permissions. Grants remain subject to
the relevant source and channel visibility rules.

Start with a dedicated read-only API account. For the smallest useful
monitoring profile, grant source visibility plus `nodes:read` and `info:read`.
Add `messages:read` only when the Messages view and received-message events are
needed. Every write below is optional, independently disabled in the
integration, and should be added only for the feature the user intends to use.

| Capability | Permission | Needed when |
| --- | --- | --- |
| Discover visible sources | A source-scoped read grant | Always; the setup flow must see the selected source. |
| Nodes, current positions, topology, and stored neighbors | `nodes:read` | Always for Meshtastic monitoring; grant equivalent node visibility for MeshCore. |
| Source status and telemetry | `info:read` | Source status and current telemetry; also required by the on-demand node telemetry and link-quality drawer. |
| Channels and stored message history | `messages:read` | Bounded source-scoped message polling, Conversations, Channels, and received-message events. |
| Private-position history | `nodes_private:read` | Only when private-position nodes should appear in on-demand trails. |
| Server-persistent favorites | `nodes:write` | Only with **Allow server-persistent favorites** enabled. Meshtastic changes always use `syncToDevice: false`. |
| Outbound messages | `messages:write` | Only with **Enable outbound messages** enabled. MeshCore also requires its server-side transmit gate. |
| Remove a remote Meshtastic node from MeshMonitor | `messages:write` | Only with **Allow removing remote Meshtastic nodes and stored history** enabled. MeshMonitor 4.14.1 uses this permission for its local node-delete route. The action deletes the local node record plus stored messages, traceroutes, and telemetry; it never purges the node from the radio. |
| Request traceroute or neighbor information | `traceroute:write` | Used only by explicit visual-editor actions, with both HA and MeshMonitor transmit gates enforced. |
| Request position or node information; linked direct reply | `messages:write` | Used only by explicit visual-editor actions. No automatic retry or fan-out. |
| Configured automations and recent runs | Global `automations:read` | Only with **Read configured automations and recent outcomes** enabled. Overview shows bounded sanitized definitions and outcomes; eligible terminal outcomes emit a restart-safe event. |

MeshCore contact removal is not exposed because MeshMonitor 4.14.1 may delete
the contact from the connected radio before forgetting it locally; that is not
the same safety contract as **Remove from MeshMonitor**.

Do not grant `packetmonitor:read`, configuration writes, source administration,
or radio-action permissions for the current integration. A supported optional
endpoint can be unavailable without taking the source offline; the panel keeps
unsupported, permission-denied, supported-empty, and transient-error states
distinct where that difference affects the operator.

## Installation

### HACS after a tagged release

After a tagged release has been published and its HACS checks pass:

1. In HACS, add the published repository as a custom **Integration** repository.
2. Find **MeshMonitor**, choose **Download**, and restart Home Assistant.
3. Continue with [configuration](#configuration).

Until then, use only a reviewed source checkout. Do not install an unrelated
project with a similar name.

### Manual source checkout

For an authorized development checkout:

1. Copy the complete `custom_components/meshmonitor` directory into
   `/config/custom_components/meshmonitor`.
2. Restart Home Assistant.
3. Confirm **MeshMonitor** appears under **Settings → Devices & services → Add
   integration**.

Keep the directory intact, including `frontend`, `translations`, and
`vendor_meshmonitor_client`. Back up Home Assistant before replacing an
existing development build.

## Configuration

1. In MeshMonitor, create a dedicated API user, scope it to the required
   source/channel data, and issue a token with the permissions above.
2. In Home Assistant, open **Settings → Devices & services → Add integration →
   MeshMonitor**.
3. Enter the MeshMonitor base URL as Home Assistant can reach it, plus the API
   token.
4. Confirm the bounded inventory of every supported visible Meshtastic,
   MeshCore, and Reticulum source. Setup creates one exact-server entry.
5. Open the entry's **Configure** action to review server settings and each
   source's polling, entity, privacy, and write options.

Use the entry's **Reconfigure** action to replace the server URL or token after
all supported visible sources validate. Use **Refresh source inventory** for a
confirmed non-destructive merge; absent-source options and identity are
retained. Authentication failures start Home Assistant's reauthentication flow.

If setup can see a source but reports no nodes, enable **View on map** for at
least one allowed channel in MeshMonitor and verify the token's node visibility.

### Options

| Option | Default | Range or effect |
| --- | --- | --- |
| Node and telemetry polling | 60 seconds | 30–3,600 seconds. One serialized source snapshot feeds all entities and most panel data. |
| Home Assistant GPS trackers | On | Creates trackers only for nodes with a valid reported position. |
| Sidebar panel | On | Registers or removes the unified MeshMonitor panel. |
| Home Assistant node devices | Source nodes + favorites | Server-global. Choose source nodes only, source nodes plus favorites, or every discovered node. All nodes remain visible and live in the MeshMonitor panel. Narrowing previews and confirms the HA-only registry cleanup; unfavoriting performs the same cleanup automatically. MeshMonitor data and recorder history are never deleted. |
| Automation visibility polling | Off | Creates one read-only owner per exact server URL. Reads at most 25 definitions and ten 20-row histories every five minutes for compact server-card statistics and restart-safe terminal events. |
| Message polling | On | Source-specific. Enables that source in Conversations and received-message events. |
| Message polling interval | 30 seconds | Server-global, 15–900 seconds. One timer covers enabled stored sources. |
| Expose message text in events | Off | Adds `text` to the event payload; panel message text is unaffected. |
| Server-persistent favorites | Off | Allows explicit favorite changes and requires `nodes:write`. |
| Outbound messages | Off | Allows administrator-only composition and requires `messages:write`. |

Option changes reload the server entry cleanly. Request volume scales with the
enabled source inventory and optional coordinators. Source reads are serialized,
and shared message and automation coordinators prevent duplicate polling for
entries that use the same MeshMonitor server.

## Using the integration

For a task-oriented walkthrough of every device, entity, panel view, map
layer, conversation feature, daily write, and browser-local preference, see
the [user and panel guide](docs/USER_GUIDE.md).

### Entities and devices

Each source always becomes a Home Assistant device with total-node and, when
available, active-node sensors. By default, only each monitored source node
and remote nodes explicitly favorited in MeshMonitor become additional Home
Assistant devices. Server options can narrow that to source nodes only or
expand it to every discovered node. This registry policy never hides or deletes
nodes in MeshMonitor or the integration panel. Qualifying nodes expose only the
values MeshMonitor supplies: last seen, battery or voltage, SNR, RSSI, channel
utilization, transmit airtime, hop count, and an optional GPS tracker. Unchanged
tracker positions are not rewritten to the recorder.

### Panel and map

The panel reads bounded, sanitized coordinator snapshots over authenticated
Home Assistant WebSockets. It never receives the MeshMonitor token or raw API
responses. Stored topology and neighbor/SNR layers refresh with the source
coordinator. Position trails are explicit on-demand reads for one visible
Meshtastic node, one fixed range from 1 hour to 7 days, and at most 1,000 fixes.
The Nodes detail drawer can make exactly two additional on-demand reads for one
visible node and the same fixed ranges: averaged telemetry and link quality,
each capped at 1,000 sanitized points in the panel response.
Overview presents compact counts from the off-by-default automation coordinator
inside the matching server card. Unsupported, denied, empty, failed, truncated,
pending, retained, and history-gap states remain distinct in coordinator data.
The panel response adds no request, exposes no server URL or raw automation
configuration/log content, and provides no create, edit, enable, run, or test
control.

The default Neutral dark map uses a near-black charcoal treatment while
keeping semantic markers and stored-link overlays legible; the unmodified
Standard style shows the same OpenStreetMap tiles without that treatment.
Select **Tiles off / privacy** to prevent
external tile requests while retaining nodes and overlays. Direct MeshMonitor
links are derived from the configured address, strip URL user information,
query data, and fragments, and never include the API token. Because MeshMonitor
4.14.1 has no stable node permalink, node links open the source's node inventory.

### Message event

With message polling enabled, a newly observed non-outgoing message fires
`meshmonitor_message_received` once. Existing history is baselined so startup
does not replay old messages.

The event contains `message_id`, `protocol`, `source_ids`, sender ID/name,
recipient ID, channel ID/name, `is_direct`, `timestamp`, and `direction`. It
contains `text` only when **Expose message text in events** is enabled. Treat
IDs, names, channel metadata, timestamps, and text as potentially sensitive
when writing automations, logs, and notifications.

Example trigger:

```yaml
automation:
  - alias: "Mesh direct message received"
    triggers:
      - trigger: event
        event_type: meshmonitor_message_received
        event_data:
          is_direct: true
    actions:
      - action: persistent_notification.create
        data:
          title: "Mesh message received"
          message: "A direct mesh message arrived. Open the MeshMonitor panel."
```

This example deliberately avoids copying message or identity data into the
notification. See the [automation examples guide](docs/AUTOMATION_EXAMPLES.md)
for the exact event schema, restart behavior, direct and channel triggers, and
privacy-preserving notification patterns.

The repository also ships five importable, visual-editor-configurable
blueprints for direct-message TTS, channel-message mobile notifications, HA
entity alerts sent to mesh, sustained source outages, and MeshMonitor
automation failures. Import remains an explicit user action; the integration
does not silently create or modify automations. Message-based recipes clearly
identify when content may be retained in Home Assistant traces and downstream
TTS or notification systems.

### Source connection event

After the first successful explicit connection value establishes a silent
baseline, a strict API-reported change fires
`meshmonitor_source_connection_changed`. Its exact four fields are
`source_id`, `protocol`, `previous_connected`, and `connected`. Each exact
server/source identity owns one in-memory baseline, so reload cannot multiply
the event.

Missing connection data and failed refreshes are silent and preserve the last
explicit boolean. Setup, restart, and the owning server entry's unload discard
the in-memory baseline; no cursor is persisted. This event consumes the
existing source snapshot and adds no MeshMonitor request. See the
[automation examples guide](docs/AUTOMATION_EXAMPLES.md) for a bounded trigger
example and lifecycle details.

### Favorites and outbound messages

Both write features require two independent gates: the Home Assistant option
and the narrow MeshMonitor permission. Favorites are explicit per-node changes;
Meshtastic favorites are stored server-side without radio synchronization.
Outbound composition is visible only to Home Assistant administrators, is
limited to three submissions per minute, and rejects duplicate submissions.
There is no service that an automation can call to transmit.

## Privacy and security

- Tokens stay in Home Assistant config-entry storage and authenticated server
  calls; diagnostics redact the server address and token.
- The panel receives selected fields rather than raw MeshMonitor payloads.
- Message text in Home Assistant events is disabled by default.
- Browser preferences such as pins, mutes, filters, map state, and read markers
  stay in that browser; they do not change MeshMonitor.
- Enabling GPS trackers records positions through normal Home Assistant state
  history. Keep them off if that retention is not appropriate.
- Standard and Neutral dark map styles disclose tile requests and approximate
  viewed map areas to the tile provider. Tiles off / privacy prevents those
  requests.
- Direct links open MeshMonitor in a new tab and still rely on the browser's
  MeshMonitor authentication/session policy.

Never post tokens, raw API responses, message bodies, node identities, or
coordinates in public issues. Read the dedicated [privacy and threat
model](docs/PRIVACY_THREAT_MODEL.md) for data classification, trust boundaries,
retention, external disclosures, write safety, abuse cases, and mitigations.
Follow [SECURITY.md](SECURITY.md) for sensitive reports and review the
capability boundary before granting new permissions.

## Project policies

Read [SUPPORT.md](SUPPORT.md) before requesting help or filing a bug. Proposed
changes must follow [CONTRIBUTING.md](CONTRIBUTING.md), including the verified
API and synthetic-data rules, and all project participation is governed by the
[code of conduct](CODE_OF_CONDUCT.md). Security reports must use the private
route described in [SECURITY.md](SECURITY.md), never a public issue.

## Troubleshooting

For a complete symptom-based workflow covering installation, setup,
authentication, least-privilege access, empty visibility, outage recovery,
panel/map/history behavior, message events, and privacy-safe diagnostic
collection, see the [troubleshooting guide](docs/TROUBLESHOOTING.md).

### Integration is not listed

Verify the directory is exactly
`/config/custom_components/meshmonitor/manifest.json`, restart Home Assistant,
and check **Settings → System → Logs** for manifest or import errors. A partial
copy that omits the vendored client or frontend is not supported.

### Cannot connect or authentication failed

Use the base URL Home Assistant Core can reach, without an API path suffix.
Check TLS trust, DNS/routing, and the dedicated token in MeshMonitor. Use
**Reconfigure** for URL changes or Home Assistant's reauthentication prompt for
a rotated token. Do not place credentials in the URL.

### Source is missing or setup says node visibility is required

Confirm that the API user is scoped to the intended source, has `nodes:read`,
and can view at least one allowed channel. For Meshtastic, enable MeshMonitor's
**View on map** setting for an allowed channel. The setup flow intentionally
rejects an empty visible node list because it usually indicates a visibility
configuration problem.

### Panel, messages, or trackers are missing

Open the config entry's **Configure** action and verify the corresponding
option. The sidebar is registered when at least one loaded entry enables it.
Message history requires `messages:read`; trackers appear only for nodes with
valid coordinates and do not backfill old position history.

### A layer is empty, unavailable, or permission denied

These are different conditions. Empty means MeshMonitor successfully returned
no stored records for the selected source/range. Unavailable means the running
server does not expose the optional route. Permission denied means the token
lacks the route or private-position grant. Adjust permissions only for the
feature you intend to use; do not add broad administration or radio grants.

### Favorites or sending fails

Confirm both the per-source Home Assistant option and the matching MeshMonitor
permission. Outbound MeshCore messages also require MeshMonitor's server-side
transmit gate. A `429`/rate-limit response is intentional protection; wait and
retry manually rather than automating retries.

### Data is stale or the source is unavailable

Check MeshMonitor source health first, then the config entry and Home Assistant
logs. Requests are serialized and time out rather than overlap indefinitely.
After a temporary outage, the coordinator retries on its configured interval;
avoid repeatedly reloading the integration because doing so adds setup traffic.

When reporting a reproducible problem, include the integration version, Home
Assistant version, MeshMonitor version, source protocol, sanitized log lines,
and exact steps—never the token, private content, identities, or coordinates.
See the [development and testing guide](docs/DEVELOPMENT.md) for reproducible
local setup and validation commands.

## Development and release status

This is pre-release software. The source-publication, HACS, client-package,
clean-install, soak, privacy, and promotion gates are tracked separately in
[RELEASE.md](RELEASE.md). A public source repository does not by itself mean a
PyPI package, HACS release, or production promotion has been approved.

Useful project documents:

- [Development and testing](docs/DEVELOPMENT.md)
- [Release process](docs/RELEASE_PROCESS.md)
- [User and panel guide](docs/USER_GUIDE.md)
- [Automation examples](docs/AUTOMATION_EXAMPLES.md)
- [Troubleshooting guide](docs/TROUBLESHOOTING.md)
- [Privacy and threat model](docs/PRIVACY_THREAT_MODEL.md)
- [Architecture and data flow](docs/ARCHITECTURE.md)
- [Changelog](CHANGELOG.md)
- [Contributing guide](CONTRIBUTING.md)
- [Security policy](SECURITY.md)
- [Release checklist](RELEASE.md)

The integration is not affiliated with or endorsed by the MeshMonitor,
Meshtastic, MeshCore, or Home Assistant projects.
