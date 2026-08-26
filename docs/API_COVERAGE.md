# MeshMonitor API coverage and roadmap

This is the living compatibility map for MeshMonitor for Home Assistant. It
records the supported server contract, the typed Python-client boundary, the
Home Assistant exposure, and capabilities that are intentionally omitted.

The matrix was last audited on 2026-08-26 against MeshMonitor 4.15.1, the
current stable upstream release. The integration supports MeshMonitor 4.14.x
and 4.15.x. Upstream `main` is monitored for compatibility planning but is
not a supported contract until those changes appear in a stable release.

## Classification

- **Read** does not change MeshMonitor or transmit over the mesh.
- **Metadata write** changes stored MeshMonitor state without transmitting.
- **Transmit** can cause radio or network traffic.
- **Administrative/destructive** changes server, source, radio, credentials,
  firmware, or stored data and remains outside this integration.

Every new route must have a narrow typed client method, synthetic contract
coverage, explicit permission and failure-state handling, and a concrete
Home Assistant daily-console use case. Browser code never calls MeshMonitor
directly.

## Supported coverage

| Capability | MeshMonitor route or surface | Permission | Class | Python client | Home Assistant |
| --- | --- | --- | --- | --- | --- |
| Source discovery | `GET /api/v1/sources` | Source visibility | Read | Supported | Setup, source inventory |
| Source status | `GET /api/v1/sources/{sourceId}/status` and protocol-specific status | `info:read` | Read | Supported | Overview, source health, entities |
| Nodes | `GET /api/v1/sources/{sourceId}/nodes` and protocol-specific node routes | `nodes:read` | Read | Supported | Nodes, map, devices, entities |
| Channels | `GET /api/v1/sources/{sourceId}/channels` | Channel visibility | Read | Supported | Messages and channel labels |
| Current telemetry | `GET /api/v1/sources/{sourceId}/telemetry` | `info:read` | Read | Supported | Sensors and node details |
| Telemetry history | Node telemetry and link-quality history routes | `nodes:read` | Read | Supported, bounded | Explicit node-history view |
| Position history | `GET /api/v1/sources/{sourceId}/nodes/{nodeId}/position-history` | `nodes_private:read` when required | Read | Supported, bounded | Explicit map trail |
| Network and topology | Source-scoped network and topology routes | `nodes:read` | Read | Supported | Map links and Operations |
| Neighbors and traceroutes | Stored neighbor and traceroute routes | `nodes:read` | Read | Supported, bounded | Node details, Routes, Operations |
| Messages | Source-scoped Meshtastic, MeshCore, and Reticulum/LXMF history | `messages:read` | Read | Supported, bounded | Conversations and optional events |
| Automations | Automation definitions and bounded run history | `automations:read` | Read | Supported | Optional Overview/Operations state and events |
| Server health and version | `GET /api/health`, `GET /api/version/check` | Public/server access | Read | Supported | Overview and Operations |
| Favorites | Protocol-specific favorite routes | `nodes:write` | Metadata write | Supported | Administrator-only, off by default |
| Ignore state | Meshtastic ignored-node route | `nodes:write` | Metadata write | Supported | Administrator-only node action |
| Node removal | Supported Meshtastic node-removal route | `messages:write` | Transmit/destructive | Supported | Administrator-only explicit action |
| Direct/channel messaging | Protocol-specific message routes | `messages:write` | Transmit | Supported, no retry | Administrator-only, off by default, rate limited |
| Node requests | Source-scoped traceroute, neighbor, telemetry, and position actions | Route-specific write grant | Transmit | Supported | Administrator-only explicit actions |
| MeshCore advert | Source-scoped MeshCore advert route | `messages:write` | Transmit | Supported, no retry | Administrator-only, off by default |

## Deliberate omissions

| Surface | Disposition | Reason |
| --- | --- | --- |
| Raw packet log | Omit | Privacy-heavy technical diagnostics belong in MeshMonitor. |
| Server/source/radio configuration | Omit | Administrative ownership remains in MeshMonitor. |
| Credentials and API-token administration | Omit | Expanding this boundary would increase secret exposure. |
| Firmware update and server restart | Omit | High-impact administration has no daily-console justification. |
| Backup, restore, purge, import, or export | Omit | Destructive/data-management operations remain in MeshMonitor. |
| Prometheus metrics | Defer/omit | Existing HA health and entities cover the useful operator state. |
| Solar analysis | Defer | Useful upstream analysis exists, but HA-specific value is not yet established. |
| Generic API passthrough | Prohibited | It would bypass typing, permission, privacy, and request-budget controls. |

## Compatibility watch

MeshMonitor development after 4.15.1 includes unreleased MeshCore contact,
telemetry, neighbor, and device-action routes. They are promising candidates,
but their schemas and permissions are not treated as stable yet.

When the next stable MeshMonitor release ships:

1. Diff its OpenAPI and supported route documentation against 4.15.1.
2. Classify each change by permission, persistence, transmission, privacy, and
   request cost.
3. Add or update typed client models and synthetic contract tests first.
4. Preserve 4.14.x and 4.15.x behavior unless a documented support decision
   says otherwise.
5. Expose only capabilities that improve daily Home Assistant monitoring.

The leading enhancement candidate is read-only MeshCore contact detail,
telemetry, and neighbor visibility. Device-changing requests must remain a
separate, explicitly reviewed slice with administrator, option, permission,
rate, result, and no-retry safeguards.

## Release lanes

- **Maintenance:** security, authentication, privacy, unintended transmission,
  regressions, upstream compatibility, CI, packaging, and documentation.
- **Enhancement:** one bounded supported capability at a time, with typed
  client support, tests, documentation, and real Home Assistant validation.

Documentation-only corrections do not require a ceremonial patch release.
Stay on 0.16.0 unless a user-visible defect needs 0.16.1; use 0.17.0 for the
next reviewed feature slice.
