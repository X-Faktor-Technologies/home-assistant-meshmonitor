# Changelog

## Unreleased

- Keep the Messages composer stable during background refreshes, open selected
  and sent conversations at the latest message, provide an accessible jump to
  the latest message, use a compact mobile layout, size message bubbles to their
  content, and report MeshMonitor send acceptance or rejection honestly.
- Prevent duplicate Home Assistant device-tracker discovery when a node's
  coordinates temporarily disappear and later return.
- Keep received and sent MeshCore direct messages in one conversation when
  MeshMonitor stores the received sender as an unambiguous public-key prefix.
- Reconcile Home Assistant node devices against successful MeshMonitor source
  snapshots so explicitly deleted nodes disappear in place, and update favorite
  membership without reloading the full integration or panel.
- Honor MeshMonitor's persisted Hide from Map preference in map markers,
  topology and neighbor overlays, fit bounds, and positioned-node counts while
  keeping the node available in Nodes and Home Assistant entities.

## 0.16.0

- Promote the clean-install-tested public beta to the first stable release so
  HACS installs it without enabling prerelease tracking.
- Clarify the verified HACS custom-repository flow and provide the exact
  copyable repository URL.

- Temporarily hide stored-node removal because MeshMonitor 4.15.1 cannot
  authenticate API tokens on that route; keep the guarded backend support for
  a future verified server fix.
- Keep every supported Node Details action visible, add clear action icons,
  and reserve the warning color for ignore controls.
- Polish the map controls, empty-filter recovery, markers, legend, and mobile
  layout, and include positioned Reticulum destinations without turning them
  into Home Assistant node devices.
- Add off-by-default administrator-only LXMF direct messaging through
  MeshMonitor 4.15.1's source-scoped Reticulum endpoint, retaining the shared
  transmit gate, replay guard, rate limit, stored-history reconciliation, and
  no-retry behavior.
- Rewrite the public setup and everyday-use documentation in plain language,
  and add privacy-reviewed Home Assistant setup images plus denser synthetic
  panel screenshots.
- Add read-only Reticulum source discovery, connection and inventory diagnostics,
  and LXMF conversations to the shared Home Assistant daily console.
- Preserve Reticulum delivery, method, signature-validation, ratchet, and
  available RF metadata in sanitized message events without inventing values.
- Keep Reticulum identity management, path probing, radio configuration,
  propagation changes, and automatic announces out of scope.
- Add a protocol-native Reticulum Overview card and centralized accessible
  Meshtastic-green, MeshCore-purple, and Reticulum-blue identity palette.
- Simplify the daily panel to Overview, Messages, Nodes, and Map; remove the
  unused standalone stored-route view.
- Move compact automation counts into the matching server card and add
  accessible clear controls to Nodes and Messages search.
- Synchronize publication metadata and current user documentation for the
  initial public source candidate.
- Make shared polling timers explicitly cancel on Home Assistant shutdown and
  keep test runs free of external firmware-release traffic.
- Remove private development reports, speculative design notes, and the unused
  stored-route frontend/backend surface from the public source candidate.
- Bring all integration modules under the committed strict-mypy check and run
  that check in continuous integration.

## 0.15.2

- Add capability-driven manual traceroute and position requests to Node Details.
- Group node-information, neighbor-information, and confirmed server-only ignore actions under a compact More actions control.
- Prevent duplicate in-flight node requests and distinguish API acceptance from a remote-node reply.

## 0.15.1

- Add off-by-default visual automation actions for server-only favorite,
  unfavorite, ignore, and unignore changes; Meshtastic writes explicitly keep
  device synchronization disabled and MeshCore exposes favorites only.
- Add a per-source automated-transmit channel-utilization ceiling. A value of
  zero disables it; interactive panel/manual actions remain exempt.
- Add UI-configurable blueprints for new-node welcomes, command responders,
  range tests, low-battery warnings, zone exits, weather alerts, and a marked,
  rate-bounded channel bridge.

## 0.15.0

- Add source-aware visual device actions for Meshtastic traceroute, position,
  NodeInfo, and NeighborInfo requests through MeshMonitor's authenticated v1
  action routes.
- Add optional Meshtastic reply linkage to the direct-message integration
  action so automations can reply to the triggering sender and message ID.
- Reuse the existing administrator/automation authorization, per-source
  transmit gate, source-local node inventory, replay protection, and shared
  radio rate limit for every new request.
- Keep remote telemetry requests and reactions excluded because MeshMonitor
  4.14.1 does not expose equivalent authenticated v1 contracts for them.

## 0.14.0

- Enrich received-message events with available sanitized reception signal,
  packet hop/MQTT classification, and already-loaded sender hardware, power,
  role, and position facts while preserving the explicit text privacy gate.
- Add visual source-device triggers for node discovery, node-information
  changes, telemetry, and position changes, with source-aware node and
  telemetry-metric filters.
- Derive the new events from existing coordinated snapshots after a silent
  setup/restart baseline, without extra API requests, recorder entities, or
  radio traffic.

## 0.13.0

- Add five importable, visual-editor-configurable automation blueprints for
  direct-message TTS, channel-message mobile notifications, HA entity alerts
  sent to mesh, sustained source outages, and MeshMonitor automation failures.
- Make message-retention and text-exposure consequences explicit in the two
  recipes that copy message bodies into traces and downstream systems.
- Validate every shipped recipe with Home Assistant's blueprint and automation
  schemas, and extend deterministic hardening coverage for upstream permission
  loss plus the shared action/panel replay and rate guard.

## 0.12.3

- Correct the connection-trigger duration capability translation so Home
  Assistant renders a human-readable **For** label in the visual editor.

## 0.12.2

- Add cancellable **For** durations to source connected/disconnected device
  triggers.
- Restore the Home Assistant sidebar control in the mobile panel header.
- Re-apply message notification deep links when an already-open MeshMonitor
  panel receives an in-place Home Assistant route change.

## 0.12.1

- Add human-readable labels for every native device-automation capability
  field used by MeshMonitor actions and triggers, including optional message
  filters and source-aware destination/channel selectors.

## 0.12.0

- Add visual source connected/disconnected and MeshMonitor automation
  completed/failed triggers backed by the existing privacy-reviewed events.
- Add optional source-aware sender, channel, and message-text filters to the
  three received-message device triggers.
- Add a source-device channel-message action whose channel dropdown is
  regenerated from that source's current channel inventory.

## 0.11.4

- Rename the integration-grouped direct-message action to **Send direct
  message to a custom recipient** and document its distinction from the native
  **Send direct message to a known node** device action with the live
  source-specific node inventory.

## 0.11.3

- Make the source-aware direct-message device action independently loadable by
  Home Assistant's device-automation discovery path, and cover the exact editor
  action-list request with a regression test.

## 0.11.2

- Add a source-device direct-message action whose destination dropdown is
  generated from every current remote node on that exact MeshMonitor source.
  Changing the source device causes Home Assistant to request a fresh,
  protocol-scoped node list without requiring node devices in the HA registry.

## 0.11.1

- Restrict the MeshCore advert action to MeshCore source devices and correct
  the direct-message destination picker to offer protocol node devices rather
  than source devices.
- Allow direct-message automations to use either a known Home Assistant node
  device or a source-local exact node name/protocol-native recipient ID, with
  explicit ambiguity and exactly-one-destination validation.

## 0.11.0

- Add visual-editor-native actions for one direct message, one channel message,
  and one MeshCore advert, with explicit source/destination device selectors,
  optional response data, protocol validation, and shared panel/automation
  transmit and replay limits.
- Add source-device triggers for any, direct, and channel messages while
  retaining the existing restart-safe unified event payload for automation
  templates and TTS actions.

## 0.10.12

- Refine Node Details with readable Meshtastic hardware names, Last seen
  terminology, altitude when reported, separate RSSI and SNR values, and a
  clearer Send Message action.

## 0.10.11

- Simplify Overview source-health cards with a concise reporting timestamp,
  divided firmware and radio-health columns, and no redundant source links or ID.

## 0.10.10

- Merge each monitored local node into its source device while preserving
  existing entity IDs and history, and remove the entity-less server device.

## 0.10.9

- Reconcile the Home Assistant registry when the node-device policy narrows or
  a node is unfavorited, with an exact cleanup preview and no MeshMonitor data
  deletion.

## 0.10.8

- Add a server-level Home Assistant node-device policy with source-only,
  source-plus-favorites (default), and all-discovered modes. The policy limits
  registry entities only; every MeshMonitor node remains visible in the panel.

## 0.10.7

- Condense the Overview header and replace aggregate review wording with exact,
  navigable source warnings.
- Cap source-card width for balanced multi-source layouts while preserving
  responsive single-column behavior.

## 0.10.6

- Add one compact Overview card per exact MeshMonitor server with installed and
  latest available version numbers, honest health/update lifecycle states, an
  allow-listed upstream release link, source count, and check freshness. Server
  health is read every five minutes and MeshMonitor's cached update status no
  more than every six hours; panel opens add no requests and expose no server
  URL, token, or raw response.
- Recover the previously deployed radio-firmware release helper into canonical
  Git so a clean checkout reproduces the confirmed HA Lab baseline.

## 0.9.1

- Replace the disabled Messages reply footer with an administrator-only,
  conversation-bound inline composer when an exact fresh source is eligible.
  Channel and direct routes retain stable protocol/source/destination identity,
  multi-source choice stays explicit, UTF-8 byte limits are destination-aware,
  Enter never sends, and a full-body review dialog precedes the backend
  confirmation. Message Reply selects and focuses the correct conversation with
  display-only quote context. Locked, pending, ambiguous, and all backend error
  states remain honest, with no optimistic bubble, fallback source, fan-out, or
  automatic retry.

- Route WebSocket panel source discovery through the typed exact-server runtime
  helper, preserving focused legacy-shaped test compatibility without an
  untyped server-entry fallback.

- Exercise real Home Assistant platform registration across unavailable and
  reappearing sources, reload, restart-shaped unload/setup, two exact servers,
  duplicate and punctuated labels, missing names, renamed nodes, and foreign
  entity-ID collisions. Process-local readable-base reservations now cover
  concurrent platform forwarding so fresh `mm_` IDs never fall through to
  Home Assistant's order-dependent numeric suffixes.

- Refactor runtime ownership to one client and one exact-server entry with
  serialized per-source first refreshes, independent source coordinators, and
  direct per-server message, automation, and operations timers. Create the
  server service device and source children before platform forwarding, attach
  node entities through exact source-scoped devices, apply isolated source
  options and message-text privacy, and suggest deterministic compact `mm_`
  entity IDs from the complete source batch. A failed or absent source can now
  remain unavailable beside a ready sibling without losing its stored identity
  or options. Panel actions carry the owning server-entry ID, so equal source
  IDs on two configured servers cannot cross history, favorite, route, or
  outbound-message boundaries; message deduplication is server-scoped too.

- Replace source selection with one normalized exact-server config entry that
  validates and stores every supported visible Meshtastic and MeshCore source.
  Add separate server and per-source options sections, a confirmed bounded
  inventory refresh that retains absent sources and their options, atomic
  reconfigure/reauth flows, unsafe-URL rejection, and explicit rejection of
  the unsupported pre-v1 source-entry shape.

- Add exact-server-scoped server, source, node, and entity identity helpers
  plus a deterministic fresh-registration entity-ID planner. New planned IDs
  begin with `mm_`, expand measurement names, remain within Home Assistant's
  limit, reuse existing registry assignments, and use stable short digests for
  duplicate labels, punctuation collapse, cross-source/server identity, and
  pre-existing registry collisions without numeric discovery-order suffixes.

- Define the separately gated read-only server-managed map-style contract,
  including the current public GETs, missing-file manifest mutation, unbounded
  and shallow style validation, embedded asset-request and privacy risks,
  deterministic future transport/style limits, exact-server session lifecycle,
  informed external-origin approval, and strict upload/import/generate/edit/
  delete exclusions. No client method, runtime request, style projection, asset
  load, permission, persistence, radio behavior, or HA deployment is added.

- Define the separately gated capability-only elevation contract, including
  global scope and public-auth blockers, provider and server-side external-
  request behavior, cache/resource and privacy limits, and strict exclusion of
  profile, terrain-tile, provider-test, configuration, radio, and runtime work.
- Define the separately gated read-only GeoJSON Map contract, including the
  current global scope, Bearer-authentication and GET-side-effect blockers,
  strict pre-parse list/geometry bounds, property-free session projection,
  external-request behavior, and exclusion of discovery, upload, edit, delete,
  permission, persistence, and runtime work.
- Define the separately gated read-only waypoint Map contract from the stored
  Meshtastic route, including its current missing server-side response bound,
  exact privacy projection, explicit-load lifecycle, and strict exclusion of
  create, update, delete, virtual storage, rebroadcast, permission changes, and
  radio propagation.
- Define the separately gated optional packet-analytics contract: one
  off-by-default bounded stored-list sample per opted-in source every five
  minutes, aggregate-only process memory, strict least-privilege and privacy
  exclusions, and no runtime read, permission grant, entity, event,
  persistence, export, clear, write, radio, or administrative action yet.
- Add a read-only Operations center backed only by the existing shared
  coordinator memory, with a second bounded privacy allow-list, honest
  per-endpoint lifecycle/stale/truncation evidence, responsive dense findings,
  and no new request, entity, event, persistence, scan, clear, export, delete,
  digest, configuration, radio, or write path.
- Add an off-by-default, exact-server-shared operations/security coordinator
  that makes four bounded stored-data reads per opted-in Meshtastic source (or
  three for MeshCore) every five minutes, drops raw mappings, distinguishes
  independent empty/denied/unsupported/error and stale-retained states, and
  exposes no panel, entity, event, persistence, scan, export, clear, delete,
  digest, radio, configuration, or other write path.
- Vendor the typed, source-scoped client contract for stored security issues,
  scanner status, key-mismatch history, and dead-node findings with strict
  caps and response-state coverage, while adding no integration polling,
  permission, panel surface, scan, clear, deletion, digest, or other write.
- Show the existing off-by-default automation coordinator's bounded sanitized
  definitions and recent run outcomes on Overview, preserving explicit empty,
  denied, unsupported, failure, retained, truncation, and history-gap states
  without adding a request, permission, write, radio action, or management UI.
- Emit off-by-default `meshmonitor_automation_executed` events only for newly
  observed completed or failed MeshMonitor runs, with a silent full-sweep
  baseline, hashed bounded restart cursor, 24-hour catch-up and gap safeguards,
  oldest-first scheduling, and an exact privacy-reviewed six-field payload.
- Replace pill navigation with one-row flat, keyboard-traversable tabs in the
  approved Overview, Messages, Nodes, Routes, Map order; retire the duplicate
  Sources view while preserving source identity and operational detail on
  Overview, and deepen Neutral dark into a near-black charcoal basemap without
  filtering semantic overlays.
- Treat node **Last heard** timestamps more than one minute in the future as
  unavailable for display and ordering, while tolerating small clock skew and
  retaining favorite-first deterministic sorting.
- Redesign Messages as a calm full-width conversation workspace with neutral
  dark-theme surfaces, compact aligned provenance, a visible focusable desktop
  scrollbar, touch scrolling, refresh-position preservation, responsive rails
  and controls, clearer lifecycle/filter-empty states, and a non-interactive
  **Reply coming soon** placeholder when outbound messaging is disabled.
- Restore stored Meshtastic and MeshCore conversation history for API-token
  users by reading the verified bounded per-source endpoints, enriching channel
  identity from existing snapshots, merging duplicate receptions, and exposing
  honest ready, partial, stale, and failed history states; the new stable-ID
  cursor silently baselines existing records so deployment cannot replay them.
- Complete deterministic typed-client coverage across topology,
  neighbors, stored routes, node trends, and position history; malformed nested
  collections now fail closed instead of appearing supported-empty.
- Add an accessible responsive node detail drawer with current node context,
  explicit 1-hour to 7-day telemetry and link-quality reads, lightweight local
  trend charts, bounded sanitized payloads, and distinct empty, unavailable,
  permission-denied, and failed states.
- Make every Overview health indicator use one strict reporting model so only
  available, explicitly connected, current, complete sources count; add
  polling-aware stale and honest unknown states plus accessible status copy.
- Replace the cast-prone dark-tile toggle with a browser-local Map style
  selector for unmodified Standard OpenStreetMap, restrained Neutral dark, and
  tile-free privacy mode, including legacy preference migration and responsive
  controls.
- Add an explicit read-only Routes view for bounded stored Meshtastic
  traceroutes and verified-pair history, with sanitized results, honest empty,
  unavailable, denied, and error states, and no active traceroute operation.
- Refresh the representative synthetic Overview, Map, and Conversations
  screenshots after the responsive visual-polish workstream stabilized, with
  current alt text and reproducible browser/privacy provenance.
- Complete the all-tab responsive audit with wrapping tab navigation, shared
  hover/focus/disabled treatment, honest Nodes/Messages/Sources lifecycle
  states, a compact mobile conversation rail and timeline, refined operational
  source cards, and corrected narrow Map control wrapping.
- Recompose Map as a cohesive dark-theme workspace with grouped responsive
  controls, legible tile-free chrome, stronger markers and overlays, styled
  Leaflet controls/popups/tooltips, compact layer evidence, reduced-motion
  handling, and explicit loading, empty, filter-empty, and failed-load states.
- Refine Overview into a deliberate daily-console landing page with an honest
  health headline, useful recent-node and position-coverage metrics, balanced
  source cards, accessible snapshot detail, responsive composition, and
  explicit loading, empty, stale-cache, and error states.
- Add `meshmonitor_source_connection_changed` from existing successful source
  snapshots with a silent first baseline, exact four-field projection,
  duplicate-entry suppression, failure-safe lifecycle behavior, and zero new
  API reads.
- Refine the Nodes inventory with permanent favorite-first grouping, a
  most-recent Last heard default, concise locally refreshed elapsed times with
  exact accessible timestamp detail, deterministic sorting, a focused narrow
  layout, and removal of the redundant per-row MeshMonitor links.
- Add the off-by-default process-shared automation coordinator prerequisite,
  bounded to 25 definitions and ten 20-row histories every five minutes per
  exact server URL, with explicit empty and failure states and no panel view or
  event emission yet.
- Fix the source-connection and terminal automation-run
  event schemas, privacy defaults, lifecycle and deduplication rules, and
  bounded shared polling contract without adding runtime events or reads.
- Inventory API-backed automation transitions and document the
  baseline, deduplication, privacy, recorder-load, and request-boundary rules;
  approve only source-connection and verified terminal automation-run events
  for later schema design.
- Complete the deterministic publication-validation matrix and declare the
  Home Assistant `http` component dependency required by the integration's
  authenticated panel and WebSocket API registration.
- Verify all documented commands and repository-relative links from clean
  integration and client checkouts, and correct the client's pre-publication
  install and source-build instructions.
- Add representative panel screenshots rendered from fully synthetic data,
  with useful alt text and documented privacy provenance; correct the map's
  node-position lookup name so it cannot collide with the playback cursor.
- Complete the publication policy package with contribution, security,
  support, and conduct policies plus privacy-aware bug, feature, and pull
  request templates that preserve the verified API and product boundaries.
- Add a dedicated release-process guide separating source publication, client
  packaging and trusted publishing, integration/HACS releases, clean install,
  upgrade, rollback, removal, verification evidence, and production promotion.
- Add a dedicated development and testing guide covering clean-checkout setup,
  required tools, validation commands, test organization, synthetic fixture
  and privacy rules, and the current Home Assistant typing limitation.
- Add a dedicated privacy and threat model covering data classification,
  authenticated-user and system trust boundaries, retention, external
  disclosures, credential handling, write/radio safety, abuse cases, and
  mitigations for the current API-backed surface.
- Add a dedicated troubleshooting guide for setup, least-privilege access,
  empty visibility, outage recovery, panel/map/history behavior, message
  events, and privacy-safe diagnostic collection; diagnostics now also redact
  the configured URL and source identity.
- Add a dedicated automation examples guide documenting the exact
  `meshmonitor_message_received` schema, restart baselining, direct and channel
  triggers, bounded notification patterns, and event-data privacy.
- Add a dedicated user and panel guide covering Home Assistant entities,
  source and node workflows, map layers and bounded trail playback,
  conversations and channels, gated daily writes, browser-local preferences,
  privacy, and common operator workflows.
- Add dedicated architecture and data-flow documentation covering coordinator
  ownership, shared message polling, authenticated panel transport, privacy
  boundaries, lifecycle behavior, and bounded write paths.
- Rewrite the README as a first-publication guide with a value proposition,
  protocol feature matrix, architecture and product boundary, prerequisites,
  least-privilege permissions, installation, configuration, privacy, usage,
  automation example, troubleshooting, and explicit pre-release status.
- Replace separate message/channel tables with a responsive conversation workspace.
- Add browser-local pinned and muted conversations without storing message content.
- Group messages chronologically with clearer inbound/outbound presentation.
- Refine the map with a dark basemap, compact overlays, stronger markers, and more viewport space.
- Document the verified MeshMonitor 4.14.1 API capability boundary and exact
  least-privilege read contract.
- Vendor the typed client and include topology and stored-neighbor
  data in each serialized Meshtastic coordinator refresh.
- Add authenticated map topology and neighbor/SNR overlays with independent
  browser-local toggles and explicit supported-empty, unavailable, and error states.
- Add on-demand Meshtastic position trails with fixed 1-hour to 7-day ranges,
  a 1,000-fix cap, browser-local playback, and explicit empty, unavailable, and
  permission-denied states.
- Add credential-free links from source and node views to verified MeshMonitor
  detail, node-inventory, and administration pages.
- Document the measured default request budget, serialized source behavior,
  bounded position-history cost, and live HA Lab resource baseline.

## 0.9.0

- Add independently gated, administrator-only server-persistent favorites.
- Add node sorting, favorite/position/protocol filters, and remembered sort views.
- Add richer message sorting, unread and favorite-sender filters.
- Add a read-only, secret-free unified Channels tab.

## 0.8.0

- Add GitHub/HACS release metadata, CI, and release documentation.
- Expand privacy-preserving diagnostics with operational options.
- Clarify shared-polling and transmit-safety comments.

## 0.7.0

- Add server/token reconfiguration and operational options.

## 0.6.0

- Add administrator-only, explicitly gated outbound composition.

## 0.5.0

- Add unified inbound message history and automation events.
