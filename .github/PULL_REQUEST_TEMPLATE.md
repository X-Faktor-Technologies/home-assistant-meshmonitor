# Pull request

## Summary

Describe the operator problem and the smallest bounded solution.

## API and product boundary

- MeshMonitor API route and permission (when applicable):
- Stored read, server metadata write, or radio/active operation:
- Why this belongs in the Home Assistant daily console:

## Privacy and operational impact

Describe sensitive data, retention, authenticated-user visibility, external
requests, polling/request-rate changes, write gates, and replay behavior. Write
"None" only after checking each category.

## Validation

List the exact checks run and their results. Include deterministic tests for
new behavior and explain any test that was not run.

## Checklist

- [ ] The change uses a narrow typed API method and adds no generic passthrough.
- [ ] I used only synthetic or irreversibly sanitized fixtures, logs, examples, and screenshots.
- [ ] I added or updated tests in proportion to lifecycle, permission, privacy, and write risk.
- [ ] I updated user documentation and `CHANGELOG.md`, or explained why neither applies.
- [ ] I ran pytest, Ruff, mypy, the frontend checks, and `git diff --check` as applicable.
- [ ] I did not deploy, publish, broaden permissions, transmit, or perform a radio/configuration/admin operation without explicit authorization.
