# Troubleshooting MeshMonitor

Start with the source card on the MeshMonitor **Overview** page. Note whether
the source is connected, when it last updated, and whether the card names a
permission or optional-data problem.

Then check the same source in MeshMonitor itself. Home Assistant cannot repair
a stopped radio, disconnected source, expired token, or unreachable server.

## MeshMonitor is not listed in Home Assistant

For a manual installation, confirm this file exists:

`/config/custom_components/meshmonitor/manifest.json`

The complete `meshmonitor` folder must include `frontend`, `translations`, and
`vendor_meshmonitor_client`. Restart Home Assistant after copying the folder,
then check **Settings → System → Logs** for an import or manifest error.

## Home Assistant cannot connect

Use the MeshMonitor address that the Home Assistant host or container can
reach. An address that works on your laptop may not work from Home Assistant.

Check:

- MeshMonitor is running;
- the hostname, port, and HTTPS certificate are correct;
- DNS and routing work from the Home Assistant host; and
- the URL does not contain an API path, username, password, or token.

Use **Reconfigure** on the integration entry to change the address.

## The API token is rejected

Create or rotate the token in MeshMonitor, then use Home Assistant's
reauthentication prompt or the integration's **Reconfigure** action.

Never paste a token into a URL, screenshot, issue, log, or browser developer
tool. Rotate it immediately if it may have been exposed.

## A source is missing during setup

The API user must be able to see the source, and the source must be Meshtastic,
MeshCore, or Reticulum.

1. Check the source type and status in MeshMonitor.
2. Check the API user's source and channel access.
3. Use **Refresh source inventory** from the integration menu.

Refreshing adds newly visible sources. It does not automatically delete a
source that is temporarily offline or hidden.

## Setup says node visibility is required

This usually means the API user can see the source but not its nodes.

For Meshtastic:

1. Grant `nodes:read` for the intended source.
2. Allow the API user to see at least one channel.
3. Enable **View on map** for that channel in MeshMonitor.

Use equivalent source and node access for MeshCore. Do not solve this by
granting administrator or radio-control permissions.

## The sidebar panel is missing

Open **Settings → Devices & services → MeshMonitor → Configure** and enable
**Sidebar panel**. At least one working MeshMonitor entry must have the option
enabled.

After upgrading integration files, reload the browser page once. If the panel
still fails, check the browser console for the specific error.

## A source or its entities are unavailable

Check the source in this order:

1. MeshMonitor source status.
2. Network and HTTPS access from Home Assistant to MeshMonitor.
3. Token validity and source permissions.
4. The MeshMonitor source card and Home Assistant logs.

After a temporary outage, wait for one configured polling interval. Reload the
integration once only if MeshMonitor is healthy and the source still does not
recover.

Missing entities are not always an error. MeshMonitor creates only the sensors
for values the radio actually reports.

## Counts differ from MeshMonitor

The integration sees only what its API user is allowed to see. Compare the
user's source and channel access first.

“Known,” “active,” and “heard recently” can also use different time windows.
Compare the labels and definitions before assuming nodes were lost.

## A node or map marker is missing

1. Clear the search and protocol, source, favorite, position, and freshness
   filters.
2. Confirm the node has a valid current latitude and longitude.
3. Confirm the source is updating.
4. If you expect a Home Assistant tracker, make sure **GPS trackers** is
   enabled for that source.

Stored position history by itself does not create a current map marker or GPS
tracker.

## The map background is blank

Check the map style:

- **Tiles off / privacy** intentionally shows no background tiles.
- **Standard** and **Neutral Dark** require your browser to reach the
  OpenStreetMap tile service.

Browser privacy settings, DNS filters, and content blockers can stop tile
requests. Nodes and saved links can still work in tile-free mode.

## A topology or neighbor layer has no links

A saved link can be drawn only when MeshMonitor has the relationship and both
nodes have current positions. A successful empty result simply means there are
no saved links to show.

Turning these layers on reads saved information. It does not send a traceroute
or another radio request.

## A position trail is empty

Position trails are loaded only when you select a visible Meshtastic node and a
time range. An empty result means MeshMonitor has no saved positions for that
node and period. Private positions may require `nodes_private:read`.

## Conversations or channels are missing

Check both:

- **Message polling** is enabled for the source; and
- the API user has `messages:read` for the source and channel.

A channel may appear before its first recent message. A muted conversation is
still collected; muting changes only the current browser view.

## No message event is fired

The first successful message update records existing history without firing
events. Test with a new incoming message after that first update.

Outgoing messages do not fire `meshmonitor_message_received`. Direct-message
direction is known only when the recipient matches a local node from a loaded
source.

## Message text is missing from an event

This is the default privacy setting. Enable **Expose message text in events**
only if the automation really needs it.

Remember that Home Assistant automation traces, logs, notifications, and TTS
services may retain the message after it leaves MeshMonitor.

## Favorite changes fail

Favorite changes need both:

- **Server-persistent favorites** enabled in Home Assistant; and
- `nodes:write` on the MeshMonitor API user.

The node must still be visible to that user. Meshtastic favorite changes are
saved in MeshMonitor without syncing them to the radio.

## Sending a message fails

Sending needs:

- a Home Assistant administrator;
- **Outbound messages** enabled for the source;
- `messages:write`; and
- for MeshCore, its transmit setting enabled in MeshMonitor.

A rate-limit response is intentional. Wait and try again manually. If a
timeout makes the result uncertain, check the conversation before resending.

## Understanding status words

- **Empty** means the request worked but MeshMonitor had no saved records.
- **Unavailable** means this server or source does not provide that feature.
- **Permission denied** means the API user lacks the required access.
- **Error** means the request should be supported but failed.
- **Out of date** means the last successful information is older than expected.

Granting more permissions will not create records that MeshMonitor has never
stored.

## Collect information safely

When filing an issue, include:

- integration version;
- Home Assistant version;
- MeshMonitor version;
- protocol;
- what you expected and what happened;
- the smallest set of steps that reproduces it; and
- a short, reviewed log excerpt if relevant.

Do not include tokens, cookies, authorization headers, message bodies, channel
secrets, node or source names and IDs, coordinates, private addresses, raw API
responses, databases, or unreviewed diagnostics. Replace identities with
fictional labels before sharing screenshots or logs.

Read [SUPPORT.md](../SUPPORT.md) before opening an issue. Report security
problems privately as described in [SECURITY.md](../SECURITY.md).
