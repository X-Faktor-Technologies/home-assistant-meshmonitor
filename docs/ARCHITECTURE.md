# Architecture and data flow

This document describes the runtime ownership, trust boundaries, and request
paths of MeshMonitor for Home Assistant. The central product boundary is that
Home Assistant is the daily mesh console while MeshMonitor remains the source
of truth for sources, radios, configuration, credentials, and technical
administration.

## Design invariants

- Every MeshMonitor call is made by Home Assistant with a narrowly scoped,
  typed client method. The browser never calls MeshMonitor directly and the
  integration has no generic API passthrough.
- Periodic work belongs to coordinators. Entity updates and normal panel
  refreshes consume coordinator memory instead of creating their own requests.
- Reads that can be expensive or privacy-sensitive are explicit, bounded, and
  limited to data already visible through a loaded config entry.
- Writes require a Home Assistant administrator, an independently enabled
  integration option, and the corresponding least-privilege MeshMonitor grant.
- Radio, configuration, credential, and source administration remain in
  MeshMonitor. Direct links may open those MeshMonitor pages, but they do not
  move an administrative API into Home Assistant.

## Runtime ownership

```text
One Home Assistant config entry (one exact MeshMonitor server)
  -> one API client holding that server entry's token
  -> one parent service device
  -> one serialized coordinator and child device per stored source
       -> node child devices and node-attached entities
       -> sanitized panel source snapshots
       -> exact-server/source connection baselines and events
  -> one server-owned message coordinator
       -> bounded source histories merged into one message snapshot
       -> deduplicated Home Assistant message events

Server entries that explicitly enable automation visibility
  -> one server-owned automation coordinator
       -> bounded definition and recent-run snapshots every five minutes
       -> sanitized Overview projection and restart-safe terminal-run events

Server entries with sources that explicitly enable operations visibility
  -> one server-owned operations coordinator
       -> up to four serialized stored-data reads per source every five minutes
       -> bounded sanitized Operations projection from coordinator memory

Authenticated Home Assistant browser
  -> registered MeshMonitor WebSocket commands
       -> coordinator memory for normal panel refreshes
       -> bounded named API methods for explicit stored-data reads or daily writes
```

Each config entry owns one `MeshMonitorClient`, one stable mapping of stored
source IDs to `MeshMonitorCoordinator` instances, and direct server-owned
message, automation, and operations resources. Server-global options are kept
separate from source polling, entity, privacy, operations, and write options.
Unloading or reloading the server entry removes all of its entity platforms,
listeners, and timers together.

The sidebar panel and WebSocket commands are process-global. The panel is
registered while at least one loaded entry enables it. WebSocket commands are
registered once, and Home Assistant supplies their authenticated connection;
no MeshMonitor credential is shipped with the panel JavaScript.

## Source snapshot flow

Each source coordinator refreshes at its source-specific configured
30-to-3,600-second interval. A Meshtastic refresh performs its reads serially: status and nodes
are mandatory, followed by best-effort network summary, topology, stored
neighbors, telemetry, and channels. MeshCore uses its protocol-specific status
and node routes plus the protocol-neutral channel route when available.
First refreshes and each source's calls are serialized to prevent a server
entry from creating an API burst. One failed source can remain unavailable
beside a ready sibling and recover on a later bounded refresh.

Mandatory status or node failures fail the coordinator update. Optional-route
failures are recorded by endpoint rather than represented as successful empty
collections; presentation code maps unsupported, permission, and temporary
errors separately where the distinction affects the operator. The resulting
typed snapshot is the only periodic source state:

- source and node entities read it through Home Assistant's coordinator entity
  model;
- GPS trackers write only when their position fingerprint changes;
- the panel serializer selects the current fields it needs from the same
  in-memory snapshot; and
- map topology and stored-neighbor toggles operate entirely in the browser.

Opening the panel, changing tabs or filters, opening node details, and toggling
an existing layer do not call MeshMonitor. Only explicit node-history, trail,
and Routes-view load actions make browser-requested stored-data reads.

## Source connection transitions

Each loaded source coordinator contributes its existing successful snapshot to
a registry keyed by the owning server entry and a one-way fingerprint of the
exact stored server URL plus the stable source ID. The first explicit `status.connected`
boolean silently establishes the baseline. A later strict boolean change fires
one `meshmonitor_source_connection_changed` event with only `source_id`,
`protocol`, `previous_connected`, and `connected`.

Repeated, missing, or null values and failed coordinator refreshes are silent
and preserve the previous explicit boolean. Reload preserves the exact
server/source identity while unloading the server discards its baseline. The registry has no
persistent cursor and observes coordinator listeners only, so it adds no API
read or timer.

## Shared message polling and events

One server entry owns its `MeshMonitorMessageCoordinator` and shared message
interval. Only stored sources with message polling enabled contribute reads.
MeshMonitor 4.14.1's optional-auth
`/api/unified/messages` route does not bind Bearer API tokens and therefore
silently answers as the anonymous user. The coordinator instead makes one
bounded, read-only history request for each configured source on the shared
timer: the canonical v1 source message route for Meshtastic and the verified
source-scoped MeshCore message route for MeshCore. Reconciliation replaces the
timer and source set when ownership or options change.

Each source read asks for at most 200 stored messages. Existing source snapshots
provide channel names and known sender labels without another request. The
coordinator derives stable Meshtastic packet identities from the verified row-ID
contract, keeps MeshCore identity source-scoped, merges duplicate Meshtastic
receptions, and orders the combined result deterministically by server arrival
time. A failed first read, partial source result, stale retained result, and
successful empty result remain distinct in the authenticated panel payload.
The coordinator keeps
at most 500 seen message IDs in Home Assistant storage; it does not persist
message bodies. On first setup it baselines the returned history, and after a
restart it restores the ID cursor, so old messages are not replayed as new
events. Outgoing messages are excluded from received-message events.

`meshmonitor_message_received` contains routing and identity metadata. Message
text is added only when a matching reception's exact source enables the
text-in-events privacy option. The panel's authenticated conversation view can
show message text independently of that event option. Pins, mutes, filters,
map preferences, and read markers are browser-local; message bodies are not
stored in browser preferences.

## Shared automation polling and terminal events

Automation visibility polling is off by default and requires a deliberate
global `automations:read` grant. When a server entry enables it, one coordinator
owns that exact stored server URL. Every five minutes it performs
one global definition read, retains at most 25 definitions in stable ID order,
and visits at most ten 20-row histories in stable round-robin order. A full
retained set is therefore visited in three successful cycles. Duplicate source
entries do not multiply this budget.

Supported-empty, permission-denied, unsupported, authentication, and transient
failure states remain distinct for the list and each history. One failed
history does not stop the remaining bounded reads, while a failed list read
skips all histories. The coordinator drops client `raw` mappings before data
enters Home Assistant memory, excluding serialized automation configuration,
trigger, state, and log content.

The same coordinator silently baselines the first complete bounded sweep and
persists at most 500 hashed `(automation_id, run_id)` terminal identities per
full server-address fingerprint. Newly observed `completed` and `failed` rows
then schedule `meshmonitor_automation_executed` oldest-first with an exact
six-field allow list. Restart catch-up requires a valid update time within 24
hours; a full page with no known terminal identity, an old row, or invalid
cursor fails toward a silent rebaseline. The event path adds no request beyond
the existing coordinator budget and has no write or radio operation.

The normal `meshmonitor/panel` response projects the same in-memory data into
Overview without making another MeshMonitor request. It allow-lists definition
ID, name, description, enabled state, and created/updated time plus run ID,
source ID, status, and started/updated time. It also preserves list/history
state, definition and history truncation, retained rows, and history-gap flags.
Serialized configuration, trigger, state, logs, creator identity, server URL,
client raw mappings, and event-cursor hashes never cross to the browser. A
server-global group is labeled only with source identities already visible in
the panel, and the UI provides no create, edit, enable, test, or run control.

## Authenticated panel transport

The panel is a static JavaScript module served by Home Assistant. It uses Home
Assistant's authenticated WebSocket connection for narrowly scoped commands,
including:

| Command | Data path | Additional boundary |
| --- | --- | --- |
| `meshmonitor/panel` | Coordinator memory to an allow-listed response | Makes no MeshMonitor request. |
| `meshmonitor/node_history` | One typed averaged-telemetry GET plus one typed link-quality GET | Only a node visible in the selected coordinator; explicit action; fixed 1, 6, 24, 72, or 168-hour window; at most 1,000 sanitized points per endpoint. |
| `meshmonitor/position_history` | One typed stored-history GET | Only a node visible in the selected coordinator; fixed 1, 6, 24, 72, or 168-hour window; at most 1,000 fixes. |
| `meshmonitor/set_favorite` | One protocol-specific favorite POST | Administrator only; exact source option and `nodes:write` required. |
| `meshmonitor/send_message` | One protocol-specific message POST | Administrator only; exact source option and `messages:write` required. |

The normal panel response contains selected source, node, channel, topology,
neighbor, message, automation, and operations fields rather than raw API objects. It
excludes the API token, channel key material, server identity, raw automation
configuration, and execution logs. Node, position, and route history similarly
return only the fields needed for their views. Node trend responses omit
packet IDs, receive metadata, and raw mappings; position records without
coordinates are filtered out; route database IDs, packet IDs, and raw mappings
are excluded. Charts, playback, scrubbing, path labels, and route-card
rendering then stay in the browser.

The panel itself is available to authenticated Home Assistant users because it
is a daily monitoring surface. Both write commands separately require Home
Assistant administrator authorization in the backend; hiding a control in the
browser is never treated as an authorization boundary.

## Bounded write paths

Favorite updates and outbound messages are the only current writes. Neither is
registered as a Home Assistant service, so an automation cannot use this
integration as a generic transmitter.

For a favorite change, the backend resolves a loaded source, checks its
favorite option, validates the protocol-specific node ID, and calls only the
matching favorite method. Meshtastic always sends `syncToDevice: false`, which
keeps the change as MeshMonitor server metadata; MeshCore uses its server-side
favorite route. A successful update explicitly refreshes that source snapshot.

For an outbound message, the backend resolves a loaded source, checks its
transmit option, requires the literal confirmation value `SEND`, and accepts
exactly one channel or direct recipient. Protocol-specific client methods
enforce destination and message-length rules. Home Assistant also enforces a
process-wide limit of three submissions per minute and rejects a repeated
nonce for five minutes. MeshMonitor still enforces `messages:write`, its own
rate limits, and the MeshCore server-side transmit gate. A successful send asks
the relevant shared message coordinator to refresh.

There is no retry loop for either write. A timeout or rejection is returned to
the operator rather than replayed automatically.

## Privacy and trust boundaries

| Boundary | Data that crosses | Data deliberately retained or excluded |
| --- | --- | --- |
| MeshMonitor to Home Assistant | Typed API responses over the configured server connection | Raw objects are retained only inside typed client models as needed for compatibility and are not passed to the panel. |
| Home Assistant config entry | Exact server address and token, bounded source inventory, separated server/source options | The token and inventory stay server-side. Diagnostics redact both and report aggregate counts instead of nodes, messages, or coordinates. |
| Home Assistant to panel | Allow-listed current state and explicit history/write results | No token, channel key, generic endpoint, or raw API response. |
| Home Assistant event bus | Message metadata with optional text; source ID, protocol, and connection booleans on strict changes | Message text is off by default. Entity and event data may still enter Home Assistant logs, recorder, or downstream automations. |
| Browser local storage | View preferences, pins, mutes, read marker, and map state | No message-body cache. Browser profiles and shared devices remain part of the user's trust boundary. |
| Browser to external services | Map tile requests when tiles are enabled; direct navigation to MeshMonitor when a link is chosen | Tile-free mode avoids map-provider requests. Direct links strip URL user information, query, and fragment data and contain no API token. |

Node names, IDs, channel metadata, signal data, messages, and coordinates can
all be sensitive even when they are not credentials. Home Assistant recorder
retention applies to enabled entities, especially GPS trackers. Operators
should enable only the entities, event text, map tiles, and write permissions
appropriate for their environment.

## Failure and lifecycle behavior

- Token rejection during source polling starts Home Assistant's
  reauthentication path; connection and server failures mark the coordinator
  update unsuccessful and retry on its normal schedule.
- Optional source data never silently becomes a successful empty result when
  the API returned a denial, missing route, or transient failure.
- Message polling failure does not fan out into per-source retry loops. The one
  server-owned coordinator retries on its configured timer.
- Option changes reload the affected server entry, then reconcile the global
  panel and direct server-owned shared coordinators.
- Direct MeshMonitor links are navigation only. The destination applies its own
  browser session and authorization policy.

The public README and user guide define the supported route and permission
boundary. New API families require a typed client method, explicit resource
bounds, privacy review, tests, and documentation before entering that boundary.
