# Contributing

Thank you for helping improve MeshMonitor for Home Assistant. By participating,
you agree to follow the [code of conduct](CODE_OF_CONDUCT.md). Use the
[support policy](SUPPORT.md) for setup questions and [SECURITY.md](SECURITY.md)
for vulnerabilities; public issues must never contain sensitive operational
data.

## Before proposing a change

Keep the product boundary intact: Home Assistant is the daily mesh console,
while MeshMonitor owns source, transport, radio, channel-secret, credential,
firmware, backup, and database administration. A new integration capability
must have a documented or verified MeshMonitor API contract and a clear daily
monitoring, messaging, mapping, or automation use case. Generic API
passthroughs are not accepted.

Discuss a substantial feature before investing in an implementation. A feature
proposal should identify the exact API route and permission, say whether it
reads stored data or can transmit or mutate state, and explain its Home
Assistant use case. Do not probe a system or broaden an API user's permissions
to gather that evidence without its owner's authorization.

## Development workflow

1. Start from a focused branch based on the current default branch.
2. Follow the [development and testing guide](docs/DEVELOPMENT.md) for a clean
   environment, test organization, fixture rules, and the full validation
   sequence.
3. Add deterministic tests for behavior changes. Cover unsupported,
   permission-denied, supported-empty, malformed, and populated API results
   where those states apply.
4. Update user documentation and `CHANGELOG.md` in the same pull request as a
   user-visible change.
5. Keep commits coherent and the working tree free of generated files, caches,
   local configuration, and credentials.

The routine local checks are:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/pytest
.venv/bin/ruff check custom_components scripts tests
.venv/bin/mypy custom_components/meshmonitor
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

These repository checks inspect tracked files and non-ignored untracked files.
Do not add AI-assistant or internal workflow material, symlinks, generated
caches, archives, databases, logs, backups, private host paths or network
addresses, or credential-like content. Use reserved example domains and
plainly synthetic fixture values.

## Privacy, safety, and implementation rules

Never commit tokens, authorization headers, cookies, raw API responses,
message bodies, channel secrets, node identities, source identities, private
service addresses, or real coordinates. Fixtures, logs, screenshots, and
examples must be synthetic or irreversibly sanitized.

Documentation links must be relative when they target repository content and
must resolve locally. Use stable canonical URLs for external references. New or
updated screenshots require a focused visual review for names, identifiers,
addresses, coordinates, messages, browser chrome, and embedded metadata. Record
their synthetic-data provenance and SHA-256 digest in
[`docs/images/README.md`](docs/images/README.md).

Public functions and non-obvious lifecycle code need concise docstrings or
comments. Explain why a privacy, permission, scheduling, ownership, or
compatibility boundary exists; do not comment syntax that is already clear.

Outbound features must be administrator-only, independently disabled by
default, narrowly permissioned, rate-limited, replay-safe, and implemented with
an explicit typed client method. Do not add a generic request method or a Home
Assistant transmit service. Never exercise a radio/configuration/admin route as
part of contribution testing without explicit system-owner authorization.

## Pull requests

Use the pull-request template and include:

- the operator problem and the bounded solution;
- API-contract and permission evidence for a new capability;
- privacy, retention, request-rate, and radio/write impact;
- exact local test results and any known limitation; and
- documentation and changelog changes, or why neither applies.

Keep unrelated refactors out of the pull request. Reviewers may ask for a
smaller change when safety or lifecycle behavior is easier to prove in
isolation. Passing local or CI validation never authorizes a deployment or a
publication action.

Release work must follow the staged [release process](docs/RELEASE_PROCESS.md).
Publishing source, a client package, an integration tag, or a production
promotion are separate owner-approved actions.
