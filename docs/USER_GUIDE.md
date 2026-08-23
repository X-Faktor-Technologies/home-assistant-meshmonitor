# User and panel guide

MeshMonitor for Home Assistant brings the current state of every configured
Meshtastic, MeshCore, and Reticulum source into Home Assistant. Use Home Assistant for
everyday monitoring, mapping, conversations, and the two explicitly enabled
daily writes. Continue to use MeshMonitor for source, radio, channel,
credential, and other technical administration.

## Before you start

Configure the integration once for each exact MeshMonitor server. Setup
discovers and validates every supported visible Meshtastic, MeshCore, and Reticulum source,
then stores them beneath that one server entry. The sidebar panel appears when
at least one loaded server entry has **Show the MeshMonitor sidebar panel**
enabled. Message conversations require source-specific message polling and
`messages:read`; position trails and optional daily writes have the additional
requirements described below.

The panel is an authenticated Home Assistant view. It receives selected fields
from Home Assistant's in-memory coordinator snapshots, not the MeshMonitor API
token or raw API responses. The **Refresh** button refreshes the panel from
those snapshots; it does not force a MeshMonitor poll.

## Home Assistant devices and entities

Each configured server creates one MeshMonitor service device. Every stored
source is a child of that server device. Meshtastic and MeshCore expose node
counts when supplied; Reticulum exposes connection, interface, and destination
diagnostics instead of inventing a Meshtastic-style node total.
The devices' configuration links open the configured MeshMonitor address.

Each observed node creates a child device beneath its source. Home Assistant
adds only entities for values MeshMonitor has actually supplied:

- last heard;
- battery percentage or voltage;
- SNR and RSSI;
- channel utilization and transmit airtime;
- hop count; and
- an optional GPS device tracker when the node has a valid position.

Diagnostic radio values appear as diagnostic entities. A value absent from
MeshMonitor is not replaced with a guessed value. If a value or valid position
first appears on a later refresh, its entity can be added then. If a source
refresh fails or a node disappears from the current snapshot, its existing
entities become unavailable instead of retaining a misleading healthy state.

GPS trackers are controlled per source by **Expose positioned nodes to the
Home Assistant map**. They record position changes through normal Home
Assistant state history. Unchanged positions are not rewritten on every poll.
Disabling the option and reloading the entry stops loading trackers for that
source; it does not delete history already retained by Home Assistant.

Integration options are split between one **Server settings** section and a
separate **Source settings** section for each stored source. Refreshing the
source inventory is explicit and confirmed; a temporarily absent source and
its options are retained rather than deleted.

## Panel tour

The sidebar panel combines all loaded sources. Its normal 30-second browser
refresh reads Home Assistant coordinator memory and does not create per-view or
per-entity MeshMonitor traffic.

Four flat top tabs appear in the stable order **Overview**, **Messages**,
**Nodes**, and **Map**. They fit one row at narrow widths without
creating page-level horizontal overflow. The active view is exposed to
assistive technology, Left/Right Arrow plus Home/End move between tabs, and
tabs, links, buttons, fields, and selectors retain a visible keyboard focus
treatment. Initial loading, no loaded sources, and a failed first panel read
remain distinct states in the inventory and conversation views as well as
Overview and Map.

### Overview

The Overview tab is the daily-console landing page. Its headline distinguishes
an all-reporting mesh from one that needs attention because a source is
unavailable, disconnected, or has partial optional data. The summary shows
known nodes, nodes heard in the last hour, positioned-node coverage, and the
represented protocols. Future and unknown last-heard timestamps are not
counted as recent activity.

**Reporting** has one strict meaning everywhere on Overview: the coordinator
is available, the source explicitly reports connected, its latest snapshot is
current, and no optional read is incomplete. Cached node content alone never
makes a source reporting. The badge, headline, explanatory state breakdown,
source-card label, and accessible status text all use this same model.
Unavailable, disconnected, stale, partial, and unknown sources are therefore
outside the reporting count. A snapshot becomes stale after three configured
source polling intervals, with a five-minute minimum grace period. Missing or
future snapshot times and a missing connection answer remain **Health
unknown** instead of being guessed healthy.

Equal source-health cards keep availability, connection state, node and
position counts, last-reported age, firmware, radio, and practical device
health together. Hover **Last reported** for its exact timestamp. Initial
loading, no-source, and failed-load states are shown
explicitly instead of presenting empty metrics as healthy data. If a refresh
fails after an earlier successful load, the Overview identifies that it is
showing the last successful snapshot.

**Available** means the source coordinator completed its required status and
node reads. Each Overview source card retains the protocol, coordinator state,
connection state when supplied, node and position counts, last-reported age,
and any optional-read failures without falsely marking a
successful empty response as a failure. The dedicated Sources view was retired
because it duplicated this read-only operational detail. Firmware and
connection information occupy one detail column; radio, battery, uptime, and
receiver health occupy the other. At narrow widths, these columns stack
without hiding operational state.

### Nodes

The Nodes tab is a unified inventory across sources. Search covers node names,
IDs, protocols, roles, and hardware models. Filters limit the list by protocol,
favorite status, or whether a position is present. Sort by name, last heard,
battery or voltage, signal, hops, or protocol in either direction.

Favorites always stay above non-favorites. The active sort and direction apply
independently inside both groups, with deterministic ordering for equal values.
A browser with no saved node-sort preference starts with favorites by most
recent **Last heard**, followed by all remaining nodes by most recent **Last
heard**. Changing a favorite repositions that row as soon as MeshMonitor accepts
the change.

The table uses the best value available for each column. For example, signal
shows RSSI when available and otherwise SNR; power shows battery percentage and
otherwise voltage. A dash means MeshMonitor did not provide that value.

**Last heard** uses concise elapsed values such as **2 min**, **3 hours**, and
**4 days**, and refreshes locally between data updates. Hover the value for its
exact ISO timestamp; the same detail is included in its accessible label.
Unknown values are shown explicitly rather than guessed. A timestamp up to one
minute ahead of the browser clock is treated as **Now** to tolerate small clock
skew. Anything further in the future is shown as **Unavailable** and sorts with
missing values instead of appearing to be the newest node. Older values remain
visible and become visually quieter after one day. Select **Details** for a
responsive drawer that keeps current node,
source, radio, hardware, position, and favorite context together. The drawer
does not fetch history when opened. Choose a fixed 1-hour, 6-hour, 24-hour,
3-day, or 7-day range and select **Load history** to make exactly one averaged
telemetry read and one link-quality read for that visible node. Results remain
in page memory, are capped at 1,000 sanitized points per endpoint, and use
small local trend charts without creating Home Assistant entities. Successful
empty data, unavailable routes, missing `info:read`, and failed reads are shown
as different states. **Show position trail** opens the Map for a bounded stored
Meshtastic trail. The star action is disabled until server-persistent favorites
are enabled for that source.

### Map

The Map tab combines current positioned nodes, stored link intelligence, and
one optional position trail. Meshtastic markers are green, MeshCore markers are
purple, and Reticulum markers are blue when positioned data becomes available.
Older markers become less prominent: fresh means heard within one
hour, stale means one to 24 hours, and old means more than 24 hours or an
unknown timestamp. Nearby markers cluster until you zoom in.

The control header keeps node filters, stored-data layers, the current trail,
and view actions in separate groups. It wraps into compact rows at narrow
widths without hiding a control. Use the protocol, source, and freshness
selectors to focus the view. **Locate** fits the map to the currently visible
nodes, links, and trail; the fullscreen button expands the complete map
workspace. A marker popup shows its source, last-heard time, power, signal,
links to its Home Assistant device and MeshMonitor node inventory, and the
Meshtastic trail action when supported.

The count badge reports only content drawable under the current filters. The
footer keeps marker and line meanings beside three compact status blocks for
topology, neighbor/SNR, and the selected position trail. Loading the first
snapshot, having no configured source data or positioned content, matching no
filters, and failing the initial panel read each have different map-state copy;
a refresh failure with retained content continues to show that last successful
snapshot under the panel error banner.

The map's stored-data controls are independent:

- **Topology** draws blue stored topology routes when both endpoints can be
  positioned.
- **Neighbor SNR** draws purple stored neighbor links and shows SNR in the
  tooltip when supplied.
- The layer status below the map distinguishes no stored records, an
  unavailable capability, and a failed optional read. A stored record whose
  endpoints lack coordinates is counted but cannot be drawn.

The normal coordinator refresh supplies topology and neighbor data. Toggling a
layer does not call MeshMonitor and never triggers an active traceroute or
neighbor request.

#### Position trails and playback

Choose **Trail** in the Nodes table or load a trail from a Meshtastic marker.
Select a fixed range of 1, 6, 24, 72, or 168 hours. This explicit action makes
one of the panel's bounded on-demand reads: stored position history for that
already visible node, capped at 1,000 fixes. It does not ask the radio for a
position.

The trail loads at its latest fix. With two or more fixes, use the slider or
**Play** to move through the history in timestamp order; playback is entirely
in the browser. **Clear trail** removes it from the current panel session.
Loading a different range repeats the bounded history read.

Map controls, marker popups, and links retain visible keyboard focus. Leaflet
pan/zoom transitions are disabled when the browser requests reduced motion;
trail playback still starts only after the operator chooses **Play**.

No stored fixes is a successful empty result. **Not available** means that
source or server does not provide the route. **Permission denied** can mean a
private-position node also needs `nodes_private:read`. Add that grant only when
showing those private positions is intended.

#### Map tiles and privacy

The Map style selector has three built-in choices. **Standard** shows the
current OpenStreetMap tiles without a visual filter. The default **Neutral
dark** applies a near-black charcoal grayscale treatment in the browser so the
base map recedes behind markers, trails, labels, and stored-link overlays;
semantic overlay colors are not filtered. **Tiles off / privacy** uses the
local tile-free background; nodes, links, trails, popups, and fit controls
remain usable.

Standard and Neutral dark both load the same OpenStreetMap tiles in the
browser. This discloses tile requests and the approximate viewed area to the
tile provider. Tiles off makes no external tile request. The selection is
stored only in the current browser profile.

### Conversations and channels

The Messages tab is a unified conversation workspace. The left rail contains
**All messages**, visible channel conversations, and direct-message
conversations across Meshtastic, MeshCore, and Reticulum. Read-only channel metadata seeds
the rail, so a visible channel can appear before its first recent message.
Channel secrets and raw channel payloads never reach the browser.

Search narrows the visible messages by sender, sender ID, channel name, or
text. Protocol and, when applicable, source selectors limit the timeline.
Messages are grouped by day, incoming and outgoing messages have different
alignment, and a message heard by multiple configured sources is shown once
with compact protocol and source provenance.

The timeline is a bounded region with its own visible desktop scrollbar. It can
be focused and scrolled with the keyboard or wheel, supports touch scrolling,
and preserves its position across normal snapshot refreshes when practical. A
newly opened conversation starts at its most recent messages. Scroll the page
outside the workspace; there is no second vertical scroller nested inside the
timeline.

On narrow screens the conversation list becomes a contained horizontal rail
above the timeline. Scroll that rail to reach later channels or direct
messages; the page itself does not scroll sideways. The selected conversation,
protocol filter, pin and mute state, and Mark read action remain keyboard
reachable, and the timeline uses the full available width without clipping
message text.

The unread count is local to this browser. **Mark read** records the current
time as its read boundary; it does not modify MeshMonitor message state. Pinning
moves a conversation to the top of its section. Muting is also a browser-local
conversation preference: it labels the conversation as muted, but it does not
disable polling, Home Assistant events, or external notifications created by
your automations.

Message history is permission-filtered by MeshMonitor and bounded to 200 stored
records per configured source on one shared server timer. Home Assistant joins
the source-scoped history to the existing sanitized channel inventory, so
Primary channel metadata and Primary history remain one conversation. A failed
initial read, partial result, stale retained history, successful empty history,
and loading state are presented distinctly. Setup and restart baseline existing
message IDs, so old history does not fire received-message events as if it were
new. The panel may display message text regardless of the separate **Include
message text in Home Assistant events** privacy option.

## Read-only automation polling and terminal events

**Read configured automations and recent outcomes** is off by default and
requires the global MeshMonitor `automations:read` permission. Enabling it now
starts one bounded five-minute coordinator per exact server address, shared by
all matching source entries. It retains at most 25 definitions and checks at
most ten 20-row histories per cycle.

Overview adds compact configured, enabled, and recent-run statistics to the
matching server card. Detailed definition and run browsing remains in
MeshMonitor. Successful empty, pending, permission-denied, unsupported,
authentication, transient failure, retained-data, truncation, and cursor-gap
states remain distinct in coordinator data. A history gap means unknown rows
were safely absorbed without replaying unprovable events; it is not proof that
no run occurred.

The same coordinator emits `meshmonitor_automation_executed` only for newly
observed `completed` and `failed` rows after a silent full-sweep baseline, with
bounded restart catch-up and gap safeguards. Opening or refreshing Overview
adds no MeshMonitor request. The panel never receives serialized automation
configuration, triggers, state, logs, creator identity, the server URL, or
cursor hashes. Enabling the option does not authorize creating, editing,
testing, enabling, disabling, or running a MeshMonitor automation, and it
performs no radio operation. Leave it disabled unless the dedicated account
has deliberately received the documented read-only permission.

## Common daily writes

The panel's most common writes are favorites and reviewed messages. Both are
off by default and require the narrow MeshMonitor permission as a second
independent gate. Additional bounded Meshtastic requests and server-only node
organization actions are available through Home Assistant's visual action
editor and are documented in the automation examples guide.

### Favorite a node

Enable **Allow server-persistent favorites** for the relevant source and grant
its dedicated MeshMonitor account `nodes:write`. In the Nodes tab, select the
star beside a node. The resulting favorite is stored by MeshMonitor and becomes
visible to other clients using the same server state.

For Meshtastic, the integration always uses `syncToDevice: false`; changing a
favorite does not transmit it to the radio. Removing the Home Assistant option
or permission disables future changes but does not undo an already stored
favorite.

### Send a message

Enable **Enable outbound messages** for the source and grant `messages:write`.
MeshCore also needs its server-side transmit gate. The composer appears only to
Home Assistant administrators and only for one selected conversation with an
exact, fresh, compatible source whose option is enabled. **All messages**,
unknown direct peers, missing channel indexes, unavailable/disconnected/stale
sources, and unsupported protocol destinations remain locked.

Select the channel or direct-message conversation first. Routing uses its
protocol plus the selected source's exact server-entry/source identity and the
channel index or recipient node ID; displayed names never determine the route.
When several eligible sources can reach the destination, the composer always
shows the exact source selector. It never substitutes another source, fans out,
or automatically retries.

The inline composer shows the protocol-specific UTF-8 byte count. Enter inserts
a newline and never sends. **Review message** opens an explicit review dialog
with the source, protocol, exact destination, byte count, and complete body.
Only **Confirm and send** from that dialog activates the existing backend
confirmation. Cancel returns focus to the unchanged in-memory draft.

Each stored message has a **Reply** action. It selects that message's stable
channel or direct peer, shows a visual quote, and focuses the composer without
sending. The quote is presentation context only; it is never sent as a reply
identifier.

Home Assistant requires a fresh submission nonce and explicit confirmation,
rejects duplicates, and limits the user to three submissions per minute.
**Accepted/pending by MeshMonitor** confirms API acceptance, not over-the-air
delivery. Permission, validation, source-transmit, rate-limit, authentication,
and server failures are distinct. Connection/time-out results are explicitly
ambiguous and instruct the operator to check stored history before a deliberate
retry. There is no optimistic conversation bubble, automatic retry, or Home
Assistant service that an automation can call to transmit.

## Browser-local preferences

The following preferences use the current browser profile's local storage:

- node sort field and direction (the unsaved default is Last heard descending);
- selected conversation, pinned and muted conversation keys, and the last-read
  timestamp; and
- map style plus topology and neighbor-layer visibility.

Conversation keys contain routing metadata such as protocol, channel index, or
node ID, but message bodies are never written to local storage. Searches,
temporary filters, map pan/zoom, loaded position trails, playback position, and
draft messages live only in the current panel instance and are lost when it is
reloaded or closed.

These preferences are not Home Assistant entities, do not synchronize between
browsers, and do not alter MeshMonitor. Clearing site data resets them. A
shared browser profile therefore also shares these local view preferences with
other people using that profile.

## Common workflows

### Check the mesh at a glance

1. Open Overview and compare the **reporting** count with the expected source
   count.
2. Review the attention headline, recent-node and position coverage metrics,
   then inspect any source card marked unavailable, disconnected, or partial.
3. If one source is unavailable or its counts look wrong, inspect its Overview
   card for the source ID, connection state, snapshot age, and partial errors.
4. Follow **Open details** only when MeshMonitor-level investigation is needed.

### Find a stale or weak node

1. Open Nodes, search for the node, and sort by **Last heard** or **Signal**.
2. Check its Home Assistant device for the available radio and power entities.
3. On Map, filter to its source and freshness class.
4. Inspect stored topology or neighbor links; absence of a drawable link is not
   proof that the radio is unreachable.

### Review mesh traffic without copying private text

1. Open Messages and choose a channel or direct conversation.
2. Pin frequently used conversations and mark the current history read.
3. Keep message text out of Home Assistant events unless an automation truly
   needs it.
4. Prefer automations that notify that a message arrived and direct the user to
   the panel rather than copying identity or body data into another system.

### Review where a node has been

1. Choose a suitable fixed range before loading the trail.
2. Load the Meshtastic node's trail from Nodes or its map popup.
3. Read the status carefully if the result is empty or permission denied.
4. Use the slider for individual timestamps or Play for browser-only playback,
   then clear the trail when finished on a shared screen.

### Perform an administrative task

1. Use Home Assistant only to identify the source or node involved.
2. Follow the bounded MeshMonitor detail or administration link.
3. Authenticate to MeshMonitor in the new browser tab.
4. Make source, radio, channel, credential, or configuration changes there;
   those operations intentionally do not exist in this integration.

## When data does not look right

- **Unavailable source:** verify MeshMonitor source health, then the Home
  Assistant config entry and logs. The coordinator retries at its configured
  interval.
- **Missing node entities:** confirm the token can see the node and remember
  that entities exist only for fields MeshMonitor supplies.
- **Missing conversations:** enable message polling and check `messages:read`
  plus source/channel visibility.
- **No map marker:** confirm the node has a valid current position. Stored
  history does not create a current tracker or marker.
- **Empty map layer:** check its status text and whether both link endpoints
  have coordinates before changing permissions.
- **Favorite or send blocked:** check both the per-source Home Assistant option
  and the matching narrow MeshMonitor permission.

For setup and connection failures, see the [README troubleshooting
section](../README.md#troubleshooting). For request ownership and privacy
boundaries, see [architecture and data flow](ARCHITECTURE.md). Never include
tokens, message bodies, identities, or coordinates in public issue reports.
