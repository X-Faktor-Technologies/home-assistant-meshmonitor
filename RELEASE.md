# Release checklist

Use this checklist with the detailed [release process](docs/RELEASE_PROCESS.md).
Publishing requires explicit maintainer approval; a successful build or test run
does not publish anything by itself.

## Prepare

- [ ] Choose the candidate version without reusing a published version or tag.
- [ ] Move the completed `Unreleased` entries under that exact version in
  `CHANGELOG.md`, leaving an empty `Unreleased` section above it.
- [ ] Set the same version in `custom_components/meshmonitor/manifest.json` and
  `pyproject.toml`.
- [ ] Review user documentation, compatibility requirements, and release notes.
- [ ] Confirm fixtures and screenshots are synthetic or irreversibly sanitized.
- [ ] Run every command in the local validation section of
  [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md).
- [ ] Confirm the default-branch validation workflow passes at the release commit.
- [ ] Confirm the `release` GitHub environment requires maintainer approval,
  `main` is protected, and the `v*` ruleset restricts tag creation to the
  environment-approved release automation identity while blocking tag updates
  and deletion. Enable immutable releases where GitHub makes the setting
  available.

## Publish

- [ ] Obtain approval to dispatch the release workflow from the exact current
  `main` commit with the new `v<version>` tag input.
- [ ] Confirm that tag does not already exist; never move or replace a tag.
- [ ] Confirm the release workflow reruns tests, Hassfest, HACS validation,
  documentation checks, and repository hygiene before publication.
- [ ] Review the generated draft release; the workflow must not publish it.
- [ ] Confirm the draft contains `meshmonitor.zip` and `SHA256SUMS`.
- [ ] Verify the archive checksum and GitHub artifact provenance attestation.
- [ ] Obtain separate maintainer approval before publishing the reviewed draft.

## Verify

- [ ] Install the release through HACS in an authorized test environment.
- [ ] Verify a clean install, upgrade from the previous supported release,
  rollback, and removal.
- [ ] Confirm setup, entities, panel views, and documented opt-in actions behave
  as described without exposing credentials or private mesh data.
- [ ] Record only sanitized results and the tested versions.

If any check fails, stop. Fix the issue on the default branch and use a new
version and tag when the failed release was already published.
