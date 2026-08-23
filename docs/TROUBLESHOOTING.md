# Troubleshooting

Use this guide to diagnose MeshMonitor for Home Assistant without broadening
permissions, repeatedly reloading the integration, or exposing private mesh
data. Home Assistant is the daily console; source, radio, channel, credential,
and server administration remain in MeshMonitor.

## Start with the smallest check

1. In **Settings → Devices & services → MeshMonitor**, find the exact-server
   entry and note whether it is loaded or needs attention.
2. Open the MeshMonitor panel's **Overview** tab. Check the affected source
   card's availability, connection state, source ID, last update, node count,
   and optional endpoint names.
3. Confirm the relevant entry option under **Configure**. Panel, tracker,
   message, favorite, and outbound-message features have independent options.
4. Check MeshMonitor's own source health and the dedicated API user's scope.
5. Review **Settings → System → Logs** around one failed refresh. Sanitize a
   small relevant excerpt before sharing it.

Do not repeatedly reload or restart while investigating an outage. Each setup
or reload performs validation and an immediate refresh, so repeated attempts
add traffic without repairing MeshMonitor, routing, TLS, or permissions.

## Installation and setup

### MeshMonitor is not listed

For a manual development installation, verify that the file is exactly
`/config/custom_components/meshmonitor/manifest.json`. Copy the complete
`custom_components/meshmonitor` directory, including `frontend`,
`translations`, and `vendor_meshmonitor_client`, then restart Home Assistant.
Partial copies are unsupported. A manifest, dependency, or import error appears
in **Settings → System → Logs**.

No public HACS repository is authorized yet. Do not infer a repository URL or
install an unrelated integration with a similar name.

### Unable to connect

Enter the MeshMonitor base URL that Home Assistant Core can reach, with no API
path suffix. A URL that works only from a desktop browser may not work from the
Home Assistant host or container. Check the MeshMonitor service, routing, DNS,
port, reverse proxy, and TLS certificate trust on that path. Do not put a user,
password, or token in the URL.

Use the config entry's **Reconfigure** action to correct the URL. Reconfigure
validates every supported visible stored source before saving.

### API token rejected

An invalid or expired token produces an authentication failure. A token
rejected during periodic polling starts Home Assistant's **Reconfigure** or
reauthentication repair flow; enter a replacement token there. Reauthentication
checks every supported visible source's status and node visibility before it
stores the token and reloads the entry.

Do not paste a token into logs, diagnostics, screenshots, issue text, browser
developer tools, or a URL. Rotate a token in MeshMonitor if it may have been
exposed.

### Source missing or unsupported

The setup flow stores only sources visible to the API user whose concrete type
is Meshtastic, MeshCore, or Reticulum. If an intended source is absent, verify its type,
the API user's source scope, and its availability in MeshMonitor, then use the
confirmed **Refresh source inventory** action. Refresh adds newly visible
sources without deleting absent sources or their options.

### Node visibility required

Setup deliberately rejects an empty visible node list because it usually means
the dedicated user can see the source but not its nodes. For Meshtastic, grant
`nodes:read` for the intended source and enable MeshMonitor's **View on map**
setting for at least one channel that user may view. Apply the equivalent
source and node visibility for MeshCore. Do not solve an empty list with broad
administration or radio-action permissions.

## Authentication and permissions

Start with only the permission for the feature being diagnosed. Visibility is
also constrained by the API user's source and channel scope.

| Symptom or feature | Setting to check | Narrow MeshMonitor access |
| --- | --- | --- |
| Required Meshtastic source and nodes | Entry is loaded | `nodes:read` plus allowed source/channel visibility |
| Source status and current telemetry | Entry is loaded | `info:read` |
| Conversations, channels, and received-message events | **Message polling** | `messages:read` |
| A private node's stored position trail | Explicit trail request | `nodes_private:read` in addition to normal node visibility |
| Server-persistent favorite | **Allow server-persistent favorites** | `nodes:write` |
| Outbound message | **Enable outbound messages** | `messages:write`; MeshCore also needs its server-side transmit gate |

Stored topology and neighbor data use the already required Meshtastic node
visibility. The current panel has no stored-route browser. Do not add
`packetmonitor:read`, configuration writes, source administration, or radio
action grants while troubleshooting current features.

An optional endpoint failure does not necessarily make the source unavailable.
The required status and node reads determine coordinator availability; each
Overview source card lists optional endpoint names separately.

## Missing or empty data

### Source or entities unavailable

A source becomes unavailable when a required status or node refresh cannot
complete. Check MeshMonitor source health first. Then check the network/TLS path,
authentication repair, and Home Assistant logs. The coordinator retains its
normal interval and retries automatically after a temporary outage.

MeshMonitor entities are intentionally sparse. A node receives only sensors for
values the API actually supplies; a missing battery, voltage, signal, telemetry,
or hop entity is not fabricated as zero. Device trackers require both the
**Home Assistant GPS trackers** option and a valid current position. Stored
position history does not create a current tracker or marker.

### Counts differ from another MeshMonitor user

The integration sees the permission-filtered view of its dedicated API user.
Compare source and allowed-channel scope before assuming data was lost. A node
can also age out of an active count while remaining in the inventory. Report
the two definitions being compared rather than sharing node lists.

### Empty, unavailable, permission denied, and error

These states are not interchangeable:

- **Empty** means MeshMonitor successfully returned no stored records for that
  source, node, or time range.
- **Unavailable** means the running MeshMonitor version or source does not
  provide the optional route.
- **Permission denied** means the dedicated token lacks the narrow grant for
  that request; private position history may need `nodes_private:read`.
- **Error** means a supported optional read failed. Check one later coordinator
  refresh before changing configuration.

Granting more access cannot create records that MeshMonitor has not stored.

## API outages and recovery

Required reads are serialized and time out rather than overlap indefinitely.
During a MeshMonitor or network outage, entities become unavailable and the
panel reports the source state from the coordinator. Home Assistant retries at
the configured 30-to-3,600-second source interval. Message history uses a
separate shared poller at the configured 15-to-900-second interval.

After service returns, wait for one applicable interval and confirm the
Overview source card's update time advances. Use **Reload** once only if the
service is healthy but the entry does not recover after a complete interval. A
URL change belongs in **Reconfigure**; a rejected token belongs in
reauthentication. Restart Home
Assistant only for installation/import changes or when logs identify a process
level problem.

Normal panel refreshes, entity reads, searches, filters, and stored-layer
toggles consume coordinator memory and do not call MeshMonitor. This makes the
source update time—not repeated browser refreshes—the useful recovery signal.

## Panel, map, and history

### Sidebar or panel is missing

At least one loaded entry must have **Sidebar panel** enabled. Option changes
reload that source and reconcile the process-wide panel. If the sidebar item is
present but the panel does not load, check the browser console only for the
specific frontend error; screenshots and exported console logs can contain
source names, node IDs, messages, or coordinates and must be sanitized.

The panel uses authenticated Home Assistant WebSockets. It does not receive the
MeshMonitor token and does not call MeshMonitor directly. A stale browser tab
may need one ordinary page reload after integration files or Home Assistant
Core are upgraded.

### Current node or marker is missing

Clear search, protocol, source, favorite, position, and freshness filters. A
dash or absent sensor means the API supplied no value. A map marker requires a
valid current latitude and longitude; a stored trail alone does not make one.
The marker age style reflects last-heard data and does not prove live radio
reachability.

### Topology or neighbor layer draws no link

Read the layer status before changing permissions. A successful empty response
means no links are stored. A stored link is counted but can be drawn only when
both endpoints resolve to current coordinates. Layer toggles never initiate a
traceroute or neighbor request and create no additional API traffic.

### Position trail does not load

Trails are available only for a visible Meshtastic node and only after an
explicit request for 1, 6, 24, 72, or 168 hours. Each request is capped at
1,000 fixes. An empty range is valid; a private node can require
`nodes_private:read`. Loading another range makes another bounded stored-data
read. Playback, the slider, and **Clear trail** are browser-only operations.

### Map background is blank

Check the Map style selector. **Tiles off / privacy** deliberately makes no
external tile request while keeping markers and overlays usable. **Standard**
and **Neutral dark** both require the browser—not Home Assistant Core—to reach
the OpenStreetMap tile service. Browser privacy controls, content blockers,
DNS, or network policy can block it. Do not weaken those controls if tile-free
operation is preferred. If Neutral dark is too subdued for the current Home
Assistant theme, choose Standard; it uses the same provider without filtering
the tile imagery.

### MeshMonitor links do not open the expected item

Links open a new tab and depend on that browser's MeshMonitor login and network
path. They contain no API token and strip URL user information, query, and
fragment data. MeshMonitor 4.14.1 has no stable node permalink, so a node link
correctly opens the source's node inventory rather than a selected node.

## Messages and Home Assistant events

### Conversations or channels are missing

Enable **Message polling** for the intended stored source and grant
`messages:read` with its source/channel scope. The server entry owns one unified
poller at its server-global interval. A visible channel may appear before its first recent
message; a channel outside the API user's view must remain absent.

Browser-local conversation mute does not stop polling, received-message events,
or Home Assistant automations. Disable or edit the automation when a downstream
notification should stop.

### No `meshmonitor_message_received` event fires

The first successful message poll establishes a baseline and intentionally
fires no events for existing history. Test only with a newly received,
non-outgoing message under the project's normal radio-operation authorization.
After restart, a bounded ID-only cursor prevents replay of already seen
messages. A recent message received while Home Assistant was offline can fire
once if it remains in the feed and was not in that cursor.

Direct messages are `incoming` only when their recipient matches a local node
ID from a loaded entry; otherwise their direction can be `unknown`. Outgoing
messages never fire the received-message event. See [Automation
examples](AUTOMATION_EXAMPLES.md) for the exact schema and safe test patterns.

### Event text is absent or unexpectedly present

**Expose message text in events** is off by default and belongs to one stored
source. A received-message event can contain `text` only when its matching
reception came through a source with that option enabled on the exact server.
Check that source's settings. The authenticated panel can show message bodies
independently of this option.

Turning the option off prevents text in future events; it does not erase
existing automation traces, logs, notifications, or downstream copies.

### Favorite or outbound message is rejected

Both operations require the source's Home Assistant option and the matching
narrow MeshMonitor permission. The composer is administrator-only, requires an
explicit review/confirmation, rejects duplicate submissions, and allows at
most three submissions per minute. Wait and retry manually after a rate-limit
response. Do not automate retries. API acceptance does not prove over-the-air
delivery.

## Privacy-safe diagnostic collection

Prefer the config entry's **Download diagnostics** action over raw API output or
a complete Home Assistant log. Diagnostics contain operational settings and
aggregate state only. The integration redacts the configured URL, token, server
fingerprint, complete source inventory, and source-option map keys; omits node
records, identities, coordinates, messages, and raw endpoint errors; and
reports only safe option values, source type, coordinator success, aggregate
counts/booleans, and optional endpoint names.

Before sharing even sanitized diagnostics:

1. Open the file locally and verify that values sensitive in your environment
   are absent. Options and counts can still reveal operational patterns.
2. Include only the affected entry's diagnostics, the integration, Home
   Assistant, and MeshMonitor versions, source protocol, approximate failure
   time, expected behavior, and minimal reproduction steps.
3. Add only the few relevant sanitized Home Assistant log lines. Remove URLs,
   hostnames, addresses, source/channel/node identifiers and names, tokens,
   message text, routing metadata, coordinates, and precise timestamps when
   they are not essential.
4. Use [SECURITY.md](../SECURITY.md) for a suspected credential leak or
   vulnerability instead of a public issue.

Do not share `.storage` files, config-entry exports, backups, raw API responses,
browser network captures, complete logs, screenshots with map or conversation
content, or automation traces containing the full event. Never enable a broad
permission merely to collect diagnostics.

For architectural request ownership and failure behavior, see [Architecture
and data flow](ARCHITECTURE.md). For expected UI semantics, see the [User and
panel guide](USER_GUIDE.md).
