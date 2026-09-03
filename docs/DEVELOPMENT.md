# Development and testing

This page is for contributors changing the integration. If you only want to
install or use it, start with the [README](../README.md) or
[user guide](USER_GUIDE.md).

The steps below create a repeatable development environment and run the same
kinds of checks used by the project. The normal test suite is self-contained:
it does not need a running Home Assistant system, MeshMonitor server, API token,
or radio.

## Required tools

- Git.
- CPython 3.12 or newer, with `venv` and `pip`. Python 3.12 is the runtime
  minimum; continuous integration currently performs strict type checking with
  Python 3.13.
- Node.js 24. The frontend is committed as plain JavaScript; the locked npm
  dependency is used only for Markdown linting, not for bundling frontend code.

Installing the Home Assistant test dependency can require several hundred
megabytes. On platforms without compatible wheels, a compiler and the system
headers required by Home Assistant's dependencies may also be necessary.

## Set up a clean checkout

From a new clone, run:

```bash
git clone <repository-url> home-assistant-meshmonitor
cd home-assistant-meshmonitor
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[test]'
```

Replace `<repository-url>` with the URL for the source you are reviewing. The
editable install includes pytest, the Home Assistant custom-component test
plugin, Ruff, and mypy. The typed MeshMonitor client used by the integration is
committed under `custom_components/meshmonitor/vendor_meshmonitor_client`; do
not install a second client copy or populate Home Assistant's `/config/deps`
directory for local tests.

Recreate `.venv` when the Python minor version or test dependency set changes.
The virtual environment and tool caches are ignored by Git.

## Validation commands

Run the same deterministic checks used by continuous integration from the
repository root:

```bash
.venv/bin/pytest
.venv/bin/ruff check custom_components scripts tests
.venv/bin/mypy custom_components/meshmonitor
.venv/bin/python -m compileall -q custom_components/meshmonitor
.venv/bin/python scripts/repository_checks.py hygiene
.venv/bin/python scripts/repository_checks.py metadata
.venv/bin/python scripts/repository_checks.py links
.venv/bin/python scripts/repository_checks.py screenshots
npm ci --ignore-scripts
npm audit --audit-level=high
npx --no-install markdownlint-cli2
node --check custom_components/meshmonitor/frontend/meshmonitor-panel.js
node --test tests/frontend/*.test.mjs
git diff --check
```

The Python suite blocks unexpected socket use, and all MeshMonitor client
interactions are mocked, so these commands must not contact a live mesh
service. Run a focused test during development with, for example:

```bash
.venv/bin/pytest tests/test_websocket_api.py -k position_history
```

Hassfest and HACS validation run in CI. External links run in a separate
scheduled workflow with retries so remote outages do not make pull requests
nondeterministic. Before publication, review its latest result and follow the
clean-install, upgrade, rollback, removal, and privacy gates in the
[release process](RELEASE_PROCESS.md).

## Type checking

The strict project configuration is exercised with:

```bash
.venv/bin/mypy
```

The current Python 3.13 development environment completes strict mypy analysis
without errors. Type checking is therefore an enforceable validation gate
alongside pytest, Ruff, frontend tests, Hassfest, and HACS validation. Do not
hide new dependency or project errors with broad ignores.

## Test organization

| File | Responsibility |
| --- | --- |
| `tests/conftest.py` | Loads Home Assistant's custom-component pytest plugin and enables the local integration. |
| `tests/test_config_flow.py` | Setup, options, token retention, and reconfiguration behavior. |
| `tests/test_lifecycle.py` | Real platform registration, exact-server/source/node hierarchy, deterministic entity IDs, source failure/reappearance, reload, restart-shaped setup, and registry persistence. |
| `tests/test_coordinator_snapshot.py` | Typed snapshot serialization, explicit endpoint states, and polling intervals. |
| `tests/test_diagnostics.py` | Diagnostic redaction and retention of safe aggregate data. |
| `tests/test_message_coordinator.py` | Message baselining, restart cursors, event replay safety, and shared polling. |
| `tests/test_source_connection.py` | Strict boolean transitions, exact event projection, failed-refresh retention, duplicate-entry ownership, reload, final unload, and zero-added-read behavior. |
| `tests/test_automation_coordinator.py` | Off-by-default shared ownership, request caps, round-robin reads, explicit failure states, truncation, raw-data exclusion, silent baselining, hashed restart cursors, bounded catch-up, gap handling, and exact terminal-event projection. |
| `tests/test_privacy.py` | Static security, packaging, storage, route, branding, and architecture invariants. |
| `tests/test_websocket_api.py` | Bounded allow-listed panel payloads, safe links, history reads, permissions, and explicit daily writes. |
| `tests/frontend/node-table.test.mjs` | Relative-time formatting, future-clock-skew tolerance, favorite-first sorting, unavailable values, and deterministic ties. |
| `tests/frontend/node-detail.test.mjs` | Node-history lifecycle states, numeric normalization, deterministic telemetry grouping, and local trend geometry. |
| `tests/frontend/overview.test.mjs` | Shared Overview/source reporting-health states, mixed and all-connected counts, polling-aware staleness, lifecycle states, recent-node bounds, and honest snapshot-age labels. |
| `tests/frontend/automation-view.test.mjs` | Automation list/history lifecycle states, overview counts, terminal-status presentation, timestamp normalization, and deterministic recent-run ordering. |
| `tests/frontend/map-view.test.mjs` | Map count labels, lifecycle-state selection, and explicit stored-layer empty, unavailable, and partial-failure summaries. |
| `tests/frontend/panel-navigation.test.mjs` | Approved daily-view order with Operations last, retired-route normalization, keyboard traversal, accessible tab semantics, and retention of source identity on Overview. |
| `tests/frontend/message-view.test.mjs` | Primary/All identity, protocol separation, compact provenance, sender/content fallbacks, timestamp normalization, and the focusable visible-scroll contract. |
| `tests/frontend/source-view.test.mjs` | Shared Overview source-card state precedence, stale and unknown values, optional-error handling, and exact snapshot detail. |

`pyproject.toml` owns the pytest, Ruff, and mypy configuration. Node's built-in
test runner owns dependency-free frontend logic tests. Async Python tests use
pytest's automatic asyncio mode. Prefer native Home Assistant fixtures and
`AsyncMock`/`Mock` client boundaries over starting services or sleeping for
timers. Tests should prove lifecycle behavior directly: first-load baselines,
restart persistence, unload cleanup, permission denial, supported-empty data,
and transient errors are distinct states.

The frontend has no generated build output. Keep browser-independent data
shaping and safety invariants in Python tests, and use the Node syntax check for
every JavaScript change. User-visible frontend behavior still needs focused
browser validation when it changes.

## Fixtures and privacy

All test data must be synthetic or irreversibly sanitized. Never commit or
paste into failures:

- API tokens, authorization headers, cookies, or private keys;
- raw MeshMonitor responses or database extracts;
- message bodies or channel secrets;
- real node IDs, names, hardware identities, source IDs, or usernames;
- coordinates, routes, waypoints, or other location histories; or
- private service URLs, hostnames, or addresses.

Use unmistakably fictional hosts such as `mesh.example`, bounded coordinates
created for the test, and minimal records containing only fields needed by the
assertion. Mock the narrow typed client method rather than HTTP generically.
When an API contract requires a new fixture shape, verify it against a
documented or read-only contract, then transcribe only a synthetic structural
example.

Tests for new reads must cover unsupported, permission-denied,
supported-but-empty, malformed, and populated responses where applicable. New
writes require administrator, option-gate, permission, rate, and replay-safety
coverage and must remain explicit client methods; generic API passthroughs and
radio/configuration administration do not belong in this integration.

Before sharing logs, snapshots, screenshots, coverage artifacts, or failure
output, review them using the privacy checklist in
[`PRIVACY_THREAT_MODEL.md`](PRIVACY_THREAT_MODEL.md).

## Documentation and screenshots

Write public documentation for users and maintainers, not for a private
deployment. Repository links must be relative and pass the local link checker;
external links should use canonical HTTPS destinations. Markdown must pass the
committed lint configuration.

Screenshots must show synthetic or irreversibly sanitized data. Before adding
or replacing one, inspect visible content and image metadata for names, host or
network details, node identifiers, coordinates, messages, tokens, and unrelated
browser or desktop content. Update [`images/README.md`](images/README.md) with
the image purpose, sanitization/provenance statement, and SHA-256 digest. A
frontend change that affects layout still needs desktop and mobile review even
when its dependency-free tests pass.
