# MeshMonitor API coverage and roadmap

This page is mainly for maintainers and contributors. It answers three
questions: which MeshMonitor features are supported, which permissions they
need, and which features intentionally stay in MeshMonitor instead of Home
Assistant.

The matrix was last audited on 2026-09-19 against MeshMonitor 4.16.1, the
current stable upstream release. The integration supports MeshMonitor 4.14.x
through 4.16.1. Upstream `main` is monitored for compatibility planning but is
not a supported contract until those changes appear in a stable release.

## What the operation types mean

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

MeshMonitor 4.16.1 preserves the source, status, node, source-scoped message,
Reticulum, and automation routes consumed by the integration. Its
cross-source message-permission repair applies to legacy/global reads; this
integration already uses source-scoped and protocol-specific message methods.
The deterministic `meshmonitor_4_16_1_contract.json` fixture records the
stable response shapes without production data.

The leading enhancement candidates are a compact read-only Mesh Issues summary
and typed MeshCore neighbor-age visibility. Device Health automation types can
flow through the existing bounded automation surface after their stable payload
shape is covered. Path-hash writes, neighbor polling, firmware, restore,
scripts, and other server or radio administration remain in MeshMonitor unless
a separate reviewed Home Assistant use case justifies changing that boundary.

MeshMonitor 4.16.1 updates MeshCore `lastHeard` on every receive path and
prevents an older contact timestamp from moving it backward. The integration
continues to use that server value directly. The local MeshCore identity is
still treated separately because a radio cannot RF-hear itself.

The vendored client is reviewed against the standalone
`python-meshmonitor` package. Models, exceptions, and request behavior remain
synchronized. The embedded package intentionally omits only distribution
metadata lookup and its public `__version__`, because it is shipped inside the
Home Assistant integration rather than installed as a Python distribution.

## Release lanes

- **Maintenance:** security, authentication, privacy, unintended transmission,
  regressions, upstream compatibility, CI, packaging, and documentation.
- **Enhancement:** one bounded supported capability at a time, with typed
  client support, tests, documentation, and real Home Assistant validation.

Documentation-only corrections do not require a ceremonial patch release.
The 0.18.0 release line contains the reviewed lifecycle, Messages, Home
Assistant 2026.9 compatibility, route-aware MeshCore events, reliable visual
message actions and triggers, and stable optimistic-send work; subsequent
changes remain one bounded slice at a time.
