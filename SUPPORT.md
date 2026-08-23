# Support policy

MeshMonitor for Home Assistant is a pre-1.0 community integration. There is
currently no supported public distribution. After release, support will be
best effort and cover the latest published integration on its documented
minimum Home Assistant version or newer, using a MeshMonitor version compatible
with the verified API contract in the README. Development snapshots and older
releases may be useful for testing but are not supported versions.

## Choose the right route

- Read the [user guide](docs/USER_GUIDE.md) and symptom-based
  [troubleshooting guide](docs/TROUBLESHOOTING.md) for installation,
  permissions, missing data, recovery, panel, map, history, and message-event
  questions.
- After the public repository exists, use its bug-report issue form for a
  reproducible integration defect and its feature-request form for a bounded,
  API-backed daily-console proposal.
- Follow [SECURITY.md](SECURITY.md) for vulnerabilities. Never use a public
  issue for a security report, credential exposure, or sensitive operational
  data.
- Use MeshMonitor, Home Assistant, Meshtastic, or MeshCore support channels for
  behavior owned by those projects. This project cannot troubleshoot radio
  firmware, RF coverage, channel keys, MeshMonitor installation, source or
  transport administration, backups, or database maintenance.

There is no authorized public repository or package yet. Until publication,
the future issue routes above are unavailable and this repository does not
promise an alternative public support channel.

## Information to include

Provide the integration, Home Assistant, and MeshMonitor versions; protocol;
expected and actual behavior; minimal reproduction steps; relevant option and
least-privilege permission names; and the result of the documented diagnostic
steps. State whether the problem began after an upgrade or recovers after an
integration reload.

Do not post tokens, cookies, authorization headers, message bodies, channel
secrets, node/source IDs or names, coordinates, routes, private hostnames or
addresses, raw API responses, database extracts, or unreviewed logs and
diagnostics. Replace identities with stable fictional labels and describe
counts or shapes instead of pasting records. Review even redacted diagnostics
locally before sharing them.

## Scope and expectations

Maintainers may close requests that cannot be reproduced, concern unsupported
versions, lack the requested sanitized evidence, duplicate an existing report,
or fall outside the integration's product boundary. Feature requests must name
a daily Home Assistant use case and documented or verified MeshMonitor API
support; a generic passthrough or technical-administration feature is out of
scope.

Support does not authorize anyone to deploy code, broaden permissions, enable
writes, transmit over radio, change configuration, or probe a system. Keep
monitoring read-only while diagnosing unless the system owner separately and
explicitly authorizes the specific operation. Response times are not
guaranteed.
