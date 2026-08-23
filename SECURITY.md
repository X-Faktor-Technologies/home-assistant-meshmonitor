# Security policy

## Supported versions

This project is pre-1.0 and currently has no published release. After release,
only the latest published version will receive security fixes; older versions
should be upgraded before support is requested.

| Version | Security fixes |
| --- | --- |
| Latest published release, once available | Yes |
| Older releases and development snapshots | No |

The current source may describe an unreleased candidate. Its presence in the
repository is not a release or a support commitment.

## Report a vulnerability privately

After the public repository enables it, use GitHub **Private vulnerability
reporting** from the repository's **Security** tab. Do not open a public issue,
discussion, or pull request for a suspected vulnerability. Before that private
reporting route exists, arrange a private channel with the project owner before
sending details; if no private channel is available, retain the report rather
than disclosing live-system or exploit details publicly.

Include:

- the affected integration and Home Assistant versions;
- the security impact and affected trust boundary;
- minimal, sanitized reproduction steps;
- whether transmission, a write, credential access, or data disclosure is
  involved; and
- any suggested mitigation, without testing it against systems you do not own
  or administer.

The maintainer will acknowledge the report, validate the affected scope,
coordinate a fix and disclosure plan when appropriate, and credit reporters
who want attribution. Response and release timing depend on severity and the
ability to reproduce the issue; no fixed remediation SLA is promised. Wait for
coordinated disclosure before publishing details.

## Sensitive data and testing boundary

Never include API tokens, authorization headers, private message bodies,
channel secrets, node/source identities, coordinates, routes, private service
addresses, raw API responses, database extracts, or vulnerable live-system
details. Sanitized Home Assistant diagnostics remain confidential operational
material and should be reviewed locally before sharing.

Do not test transmit, radio, configuration, discovery, firmware, reboot,
credential, permission, or administrative behavior on infrastructure you do
not own or explicitly administer. Do not broaden MeshMonitor permissions to
demonstrate an issue without owner authorization.

The [privacy and threat model](docs/PRIVACY_THREAT_MODEL.md) documents the
current data classes, trust boundaries, retention, external disclosures,
credential handling, write/radio controls, and residual risks. General setup
and compatibility requests belong in the channels described by
[SUPPORT.md](SUPPORT.md), not in a private vulnerability report.
