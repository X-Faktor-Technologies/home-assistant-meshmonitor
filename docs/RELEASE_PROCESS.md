# Release process

This process is for maintainers publishing the Home Assistant integration. It
keeps source review, automated validation, publication, and installation
verification separate and repeatable.

## 1. Prepare the candidate

1. Start from the intended default-branch commit with no unrelated changes.
2. Select a version that has not been published. Use semantic versioning and
   consider Home Assistant compatibility and user-visible behavior.
3. Move completed entries from `Unreleased` to a new exact version heading in
   `CHANGELOG.md`; leave `Unreleased` present and empty.
4. Set the same version in `custom_components/meshmonitor/manifest.json` and
   `pyproject.toml`. Do not add a release date or tag until the candidate is
   ready.
5. Update concise user documentation for changed configuration, permissions,
   entities, actions, compatibility, or limitations.
6. Review all new fixtures, logs, images, and examples. They must contain only
   synthetic or irreversibly sanitized data.

The release metadata gate requires exact agreement among the requested
`v<version>` tag, the manifest, `pyproject.toml`, and the first changelog entry
after `Unreleased`.

## 2. Validate

Run the complete local sequence in [`DEVELOPMENT.md`](DEVELOPMENT.md), including
tests, type checking, frontend checks, Markdown lint, relative links, metadata,
screenshot integrity, and repository hygiene. Review `git status --short`,
`git diff --check`, and the complete candidate diff.

Open or update the release pull request and require the public validation
workflow at the exact candidate commit. That workflow also runs Hassfest and
HACS validation. External links are checked separately on a schedule because
remote availability is not a deterministic pull-request gate; investigate its
latest result before release.

Validation must not require a Home Assistant instance, MeshMonitor server,
token, or radio. Any optional integration testing must use an explicitly
authorized test environment and must not place private data in logs or release
evidence.

## 3. Tag and publish

After review and explicit maintainer approval, dispatch the release workflow
from the exact current `main` commit and supply the new `v<version>` tag. The
workflow refuses non-`main` refs, stale commits, and existing tags. It then:

- invokes the full validation workflow again at the release commit;
- enforces tag, manifest, project, and changelog agreement;
- builds `meshmonitor.zip` only from the exact tracked integration files listed
  in `release-archive-files.txt`, with stable ordering, timestamps, and
  permissions;
- creates `SHA256SUMS` for the archive;
- records a GitHub build-provenance attestation; and
- creates the new tag and a draft containing both files only after every
  preceding job succeeds and the protected `release` environment is approved.

Before enabling this workflow, install a ruleset for `refs/tags/v*` that
restricts creation to the environment-approved release automation identity and
blocks updates and deletion. This is mandatory because historical commits may
contain older tag-triggered workflows; current workflow code cannot retroactively
change them.

Review the draft, checksum, provenance, and generated notes. Publishing the
draft is a separate maintainer action and approval gate. Do not move a
published tag or replace a published archive. Correct a release with a new
version so users can verify its history and provenance.

## 4. Verify the release

1. Confirm the GitHub release version, prerelease state, and notes.
2. Download `meshmonitor.zip` and verify it against `SHA256SUMS`.
3. Verify the artifact provenance using GitHub's attestation tooling.
4. Inspect the ZIP root for `manifest.json`, `__init__.py`, translations,
   frontend assets, and vendored licenses. It must not contain a parent
   `custom_components` directory, tests, caches, or repository files.
5. In an authorized test environment, verify HACS clean installation, upgrade
   from the previous supported release, rollback, and removal.
6. Exercise the documented setup and principal read-only views. Test opt-in
   write features only when explicitly authorized and appropriately isolated.
7. Review diagnostics and logs for credential or private-data disclosure, then
   record sanitized versions, checksums, and pass/fail results.

If verification fails, mark the release clearly, direct users to a known-good
version, and prepare a corrected version. Never silently replace release
artifacts or expose private evidence while diagnosing a failure.
