# Privacy and threat model

This page explains what sensitive information the integration can handle, what
it deliberately leaves out, and the safeguards contributors must preserve. It
is written for reviewers and advanced users; everyday privacy choices are
summarized in the [user guide](USER_GUIDE.md).

It covers the integration's 0.16.0 API-backed entities, panel,
messages, map, position history, favorites, and outbound-message surface. It
does not make claims about MeshMonitor, Meshtastic, MeshCore, Home Assistant,
radio firmware, or notification providers beyond how this integration uses
them.

The governing product boundary is unchanged: Home Assistant is the daily mesh
console, while MeshMonitor owns source, radio, channel, credential, and
technical administration.

## Security goals

- Keep the MeshMonitor API token and channel key material out of the browser,
  entity state, events, diagnostics, and direct links.
- Expose only API-backed fields needed for daily monitoring and explicit
  operator actions; never expose a generic API request path.
- Make sensitive retention and external disclosure opt-in or visible wherever
  the integration controls it.
- Keep monitoring read-only by default and require independent authorization
  gates for each supported write.
- Prevent startup, reconnect, retry, browser replay, or automation replay from transmitting a
  message automatically.
- Preserve the difference between unsupported, denied, empty, and failed reads
  so an operator is not encouraged to grant unnecessary access.

The integration cannot protect data after an authorized Home Assistant user,
administrator, automation, browser extension, backup process, or host-level
operator copies it elsewhere. It also does not replace the authentication,
retention, transport security, or radio-security policies of the surrounding
systems.

## Data classification

| Class | Examples in the current surface | Required handling |
| --- | --- | --- |
| Credentials and key material | MeshMonitor API token; any credential embedded in a URL; channel keys in upstream responses | Secret. Store only server-side, never serialize to the panel or diagnostics, and never put credentials in a URL. The panel exposes only whether a channel has a key. |
| Message content | Direct and channel message text, reactions, reply IDs, sender and recipient context | Sensitive content. Visible in the authenticated panel; excluded from events by default and never written to browser preferences or the integration's restart cursor. |
| Identity and routing data | Source, node, sender, recipient, and channel IDs/names; protocol; local-node identity; routes and receptions | Sensitive metadata. It can identify people, equipment, groups, and communication patterns even without message text. |
| Location and movement | Current coordinates, altitude, bounded position trails, timestamps, speed, track, topology endpoints | Highly sensitive operational data. Current trackers can enter Home Assistant history; on-demand trails remain in page memory unless another component or user copies them. |
| Radio and operational telemetry | Last-heard time, battery, voltage, RSSI, SNR, hop count, topology, neighbor links, source health, counts, error endpoint names | Sensitive operational data. It may reveal presence, activity, coverage, equipment condition, or network structure. |
| Automation metadata | Definition IDs, names, descriptions, enabled state, run IDs, source IDs, statuses, and timestamps | Sensitive operational metadata. Visible only through the authenticated panel when the off-by-default read option is enabled; raw configuration, triggers, state, logs, creator identity, server identity, and cursor hashes stay server-side. |
| Stored security findings | Source ID, node identity/name, key-quality flags, packet-rate/time-offset findings, scanner state, and dead-node history | Highly sensitive operational/security metadata. The off-by-default coordinator keeps a bounded sanitized copy in Home Assistant process memory. A second allow-list projects it only to authenticated panel users, without old/new key fragments, free-form key-detail text, mismatch IDs, dead-node internal IDs, server identity, or raw fields. It never enters entities, events, diagnostics, recorder, or persistent storage. |
| Preferences and cursors | Pinned/muted conversation identifiers, read timestamp, filters, sort and map settings; up to 500 seen message IDs | Lower sensitivity but still linkable metadata. Browser preferences stay in that browser profile; the restart cursor contains IDs only in Home Assistant storage. |
| Write content | Favorite changes, outbound destination/channel, and outbound message body | Integrity- and safety-sensitive. Accept only through the two named, bounded backend commands after all applicable gates pass. |

Treat sanitized diagnostics as confidential operational material. Redaction
removes the connection and source identity, but options, counts, booleans, and
endpoint names can still reveal how the installation is used.

## Trust boundaries and access

```text
Mesh and radios
  -> MeshMonitor storage and API
       -> Home Assistant Core and persistent storage
            -> entities, recorder, event bus, and automations
            -> authenticated Home Assistant WebSocket
                 -> browser memory and local preferences
                 -> optional map-tile provider
                 -> explicit navigation to MeshMonitor
```

### MeshMonitor to Home Assistant Core

Home Assistant connects to the configured MeshMonitor base URL with the token
stored in the config entry. Typed, narrowly scoped client methods validate and
bound the supported calls. The client can retain unknown response fields in a
model's in-memory `raw` mapping for compatibility, but the panel serializer
allow-lists fields and never passes those raw mappings onward.

The operator controls the network path and TLS policy. Use a trusted HTTPS
endpoint when traffic can cross an untrusted network. A compromised or
impersonated MeshMonitor server can return misleading data and receives every
API request and its token.

### Home Assistant Core and storage

The config entry persistently contains the exact server address and token, a
bounded source inventory, and separated server/source options. Home Assistant administrators,
host-level operators, storage files, and backups are therefore inside the
credential trust boundary. Removing a config entry does not retroactively
remove it from existing backups.

Coordinator snapshots and the latest locally merged stored messages live in
Home Assistant process memory. Entities copy selected values into Home Assistant state. Normal
recorder policy then governs retained entity history, including GPS tracker
positions when trackers are enabled. The integration does not create entities
for message bodies or stored position trails.

The received-message event always contains identity and routing metadata.
Message text is added only when a matching reception's stored source enables
**Expose message text in events** on that exact server. The source
connection event contains only source ID, protocol, and the previous and new
explicit booleans. Its one-way server fingerprint and config-entry identity
stay inside process memory. Event consumers, automation traces, logs,
notifications, and other integrations may make independent retained copies.

The reviewed source-connection and automation-run event contracts
omit source and automation names, server and config-entry identity, serialized
automation configuration, trigger, state, and log data, and execution text.
The shared automation coordinator is off by default, requires an
explicit global `automations:read` grant, and drops client raw mappings before
retaining its bounded in-memory projections. The event bus receives only the
six reviewed terminal-run fields; storage retains at most 500 one-way terminal
identity hashes, never raw IDs, names, configuration, triggers, state, or logs.
The authenticated panel receives only the reviewed automation definition/run
allow list and explicit lifecycle, truncation, retained-data, and history-gap
flags from coordinator memory; it receives no server URL or cursor hashes and
causes no additional MeshMonitor request. Event payloads are explicit
allow-listed projections, and cursor, catch-up, and request bounds are enforced
by the shared automation coordinator.

### Authenticated Home Assistant users

The panel and its read commands are an authenticated Home Assistant surface,
not an administrator-only surface. Any authenticated Home Assistant user who
can call the registered WebSocket commands can receive the allow-listed node,
message, channel, topology, neighbor, source, current-position, and enabled
automation-visibility data for all
loaded MeshMonitor entries, and can request a bounded stored trail for a
visible Meshtastic node. The sidebar toggle controls presentation, not
per-user authorization.

Deploy this integration only where every authenticated Home Assistant user is
trusted with that mesh data. Home Assistant administrator status is separately
required in the backend for favorite changes and outbound messages; hiding or
disabling a browser control is never used as an authorization check.

### Browser and external services

Message bodies, node telemetry/link-quality trends, and position trails are
present in page memory while displayed. Local storage contains view settings
and identifiers used for pins, mutes, conversation selection, and read state,
but not message bodies or history points. Other users of
the same browser profile, browser extensions, screenshots, developer tools,
and a compromised browser are inside this boundary. Clear Home Assistant site
data when a shared browser profile changes hands.

With the Standard or Neutral dark Map style, the browser sends tile coordinates
and ordinary request metadata to the configured OpenStreetMap tile service.
Those requests can reveal the client's network address, timing, and approximate
viewed area. **Tiles off / privacy** prevents the panel from making external
tile requests; the visual filter choice does not change the tile provider or
send data anywhere else.

Direct links disclose a deliberate navigation to the configured MeshMonitor
origin. The generated links strip URL user information, query data, and
fragments and contain no API token, but the destination still applies its own
browser session, logging, and authorization policy.

## Retention inventory

| Location | Current data | Lifetime or limit | Operator control |
| --- | --- | --- | --- |
| MeshMonitor | Nodes, messages, telemetry, topology, positions, and write results | MeshMonitor policy; not controlled here | Configure and purge in MeshMonitor. |
| Home Assistant config-entry storage and backups | Exact server URL and token, bounded source identity/type/name inventory, and separated server/source options | Until entry removal; backups can outlive the entry | Protect Home Assistant storage and backups; rotate the token after suspected exposure. |
| Source coordinator memory | Latest typed source snapshot, including model `raw` fields | Replaced on refresh; discarded on unload/restart | Polling and feature options; upstream source scope. |
| Shared message coordinator memory | At most 200 messages returned by each poll | Replaced on poll; discarded when unused or on restart | Disable message polling or narrow `messages:read` visibility. |
| Home Assistant integration storage | Up to 500 seen message IDs per server fingerprint | Bounded rolling cursor; persists across restart | Removed with the relevant Home Assistant storage data; contains no bodies. |
| Home Assistant state and recorder | Source/node entity states and optional current GPS trackers | Home Assistant recorder policy | Disable trackers where location history is inappropriate; configure recorder inclusion, retention, and purge separately. |
| Home Assistant events and downstream systems | Message metadata and optional text; source ID, protocol, and connection booleans on strict changes | Consumer-specific | Keep text disabled, minimize event data copied onward, and use privacy-preserving notification templates. |
| Browser page memory | Panel snapshot, including messages and any loaded node trends or position trail | Until replaced, cleared, or the page closes | Close the drawer or page, log out, and protect the browser profile. |
| Browser local storage | Sort/filter/map settings, conversation identifiers, pins/mutes, and last-read timestamp | Until site data is cleared | Clear site data; no message-body cache is written. |
| Downloaded diagnostics | Redacted config data and aggregate operational state | Until the downloaded file is deleted | Review locally, share minimally, and delete according to support policy. |

## Credential handling

1. Create a dedicated MeshMonitor API user and scope it to only the intended
   sources, channels, and methods. Do not reuse an administrator credential.
2. Enter the token only in the Home Assistant setup, reconfigure, or
   reauthentication flow. Do not embed a user, password, or token in the URL.
3. Grant read permissions only for enabled features. Add `nodes:write` or
   `messages:write` only when the matching write option is deliberately
   enabled. Do not grant configuration, source administration, radio-action,
   or packet-monitor permissions for the current surface.
4. Protect Home Assistant `.storage`, backups, host access, and administrator
   sessions as secrets because they can expose or use the token.
5. Rotate the token in MeshMonitor after suspected disclosure, then replace it
   through Home Assistant reauthentication or reconfigure. Rotation does not
   erase data already copied to logs, backups, browsers, or downstream tools.

Config-entry diagnostics redact the URL, token, server fingerprint, complete
source inventory, and source-option map keys.
They omit nodes, messages, coordinates, and raw optional-error text. Direct
links and panel responses never contain the token. These controls reduce
accidental disclosure; they do not make complete Home Assistant logs, storage
files, backups, raw API responses, screenshots, network captures, or browser
developer-tool exports safe to publish.

## Write and radio safety

Monitoring, topology, stored neighbors, node-history, and position-history
features perform stored-data reads only. Active traceroute, neighbor refresh, telemetry poll,
discovery, configuration, reboot, firmware, and remote-administration routes
are excluded because they can transmit, mutate technical state, or exceed the
daily-console boundary.

Favorite updates require a Home Assistant administrator, the exact source's
favorite option, and `nodes:write`. Meshtastic favorite changes always set
`syncToDevice: false`, so the supported operation changes MeshMonitor server
metadata rather than synchronizing over radio. MeshCore uses its specific
server-side favorite method.

Outbound messages are real transmit operations. Panel composition requires a
Home Assistant administrator plus explicit review and literal confirmation.
Native HA actions accept only an HA-owned automation context or an authenticated
administrator and require one source device plus exactly one validated channel
or remote node device. Both paths require the exact source's outbound option,
`messages:write`, and any MeshCore server-side transmit gate. They share a
maximum of three message submissions per minute and five-minute replay keys;
adverts share a separate once-per-five-minute guard. Only protocol-specific
client methods are used and no failed or ambiguous call is retried. API
acceptance does not prove over-the-air delivery.

## Threats, mitigations, and residual risk

| Threat or abuse case | Current mitigation | Residual risk and operator action |
| --- | --- | --- |
| A stolen MeshMonitor token reads more data or performs writes | Dedicated user, source/channel scope, narrow typed methods, independent write options | An overprivileged token defeats least privilege. Keep grants minimal, protect backups, and rotate after exposure. |
| An authenticated Home Assistant user reads sensitive mesh data | Authentication and allow-listed WebSocket responses; no token or channel keys sent | Read access is not per-user or admin-only. Trust every HA user with loaded mesh data. |
| A malicious browser request invokes a write | Backend administrator check, option gate, API permission, strict schema, named client method | A compromised administrator session can still act. Use strong HA authentication and revoke suspicious sessions. |
| A refresh, reconnect, retry, or duplicate panel/automation action sends twice | No send retry; panel confirmation; one shared process rate limit; five-minute panel nonce or HA-context/payload replay rejection | An authorized automation can deliberately send, and a result lost after API acceptance is ambiguous. Check MeshMonitor rather than blindly resending. |
| Private messages leak through events or notifications | Event text off by default; privacy-preserving examples; no bodies in cursor or local storage | Metadata is always present in the event and consumers can retain copies. Audit automations and traces before enabling text. |
| Coordinates accumulate in Home Assistant | Trackers are optional; trails are on-demand, capped at 1,000 fixes, and returned only for a currently visible node | Current tracker history follows recorder policy. Disable trackers or exclude them from recorder when retention is unacceptable. |
| Map viewing discloses location interest to a third party | Tile-free mode | With tiles enabled, the provider sees tile requests and metadata. Use **Tiles off** for sensitive operations. |
| Browser-local metadata leaks on a shared device | No message bodies in local storage; output is HTML-escaped | Conversation identifiers and read/view state remain until site data is cleared; page memory and screenshots can contain full content. |
| Support material leaks secrets or identities | Diagnostics redact connection/source identity and omit detailed records; troubleshooting requires local review | Counts/options can still be sensitive, and raw logs or captures are not sanitized. Share the minimum through the security-reporting path. |
| A compromised or spoofed MeshMonitor endpoint steals the token or returns hostile data | Operator-chosen endpoint, transport validation, typed parsing, allow-listed serialization, escaped rendering | The integration does not establish endpoint trust. Use trusted TLS and secure DNS/network routing. |
| Direct navigation carries credentials or opens untrusted content | Link construction strips credentials, query, and fragment; new tabs use `noopener noreferrer` | The configured origin controls the destination page and its logs. Verify the base URL and rely on MeshMonitor authentication. |
| Broad new API functionality bypasses the product boundary | No generic request primitive; capability matrix and verified-route review | Every new endpoint changes this model. Re-review permissions, retention, user access, and radio effects before implementation. |

Home Assistant administrators and host operators remain fully trusted: they can
read config-entry storage, alter integration files or options, inspect memory,
configure recorder and automations, and authorize writes. This model does not
claim end-to-end encryption for mesh messages or defend against a compromised
Home Assistant host, MeshMonitor server, radio, protocol, or browser.

## Privacy-first operating checklist

- Use a dedicated, least-privileged MeshMonitor user over a trusted network
  path; protect and test token rotation.
- Give Home Assistant accounts only to people trusted with all loaded panel
  data, and protect administrator sessions with strong authentication.
- Leave event text, server-persistent favorites, and outbound messages off
  unless their specific benefit and retention or transmit impact are accepted.
- Disable GPS trackers or exclude them from recorder when current-location
  history is not appropriate.
- Use **Tiles off** when external map requests are not acceptable.
- Review automations, traces, notification targets, browser profiles, backups,
  logs, and downloaded diagnostics as separate disclosure paths.
- Report suspected vulnerabilities or credential exposure through
  [SECURITY.md](../SECURITY.md), never with live secrets or private mesh data in
  a public issue.

Revisit this model whenever a new API method, entity, event, external service,
persistent store, browser cache, permission, or write path is proposed. The
[architecture guide](ARCHITECTURE.md) defines runtime ownership and the
supported endpoint and permission boundary.
