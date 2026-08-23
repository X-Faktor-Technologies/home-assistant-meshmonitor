# Release process

This guide separates publishing the source repositories from publishing the
Python client, creating a Home Assistant/HACS release, and promoting the
integration beyond the lab. Each stage has its own approval and verification
gate. Completing one stage does not authorize the next.

The integration and client are pre-1.0 projects. Use the version declared in
`custom_components/meshmonitor/manifest.json` for an integration candidate and
the version declared in the client's `pyproject.toml` for a client candidate.
Before any tag or package publication, remove the relevant `Unreleased`
heading, or move its entries under that exact candidate version, and confirm
that documentation and release notes describe the same surface.

## Authority and release boundaries

| Stage | Result | Required authorization |
| --- | --- | --- |
| Source publication | Sanitized public snapshot and default-branch CI | Explicit owner approval to create and push each public repository |
| Client packaging | A versioned `meshmonitor-api-client` artifact on PyPI | Explicit owner approval plus configured PyPI trusted publishing |
| Integration/HACS release | A GitHub release with `meshmonitor.zip`, usable as a HACS custom repository | Explicit owner approval to push the version tag and publish the release |
| Verification | Clean install, upgrade, rollback, removal, privacy, and lab checks | Approval for the release under test; use only authorized test systems |
| Production promotion | Use outside the lab | Separate explicit owner approval after every promotion gate passes |

Never treat a public repository, a passing CI run, a built local archive, or a
successful HA Lab test as permission to publish the next artifact. Never put a
token, raw response, message body, identity, coordinate, private service URL,
or live-system screenshot in a commit, workflow log, release note, or artifact.

## 1. Prepare and publish source

Do this independently for `python-meshmonitor` and
`home-assistant-meshmonitor`:

1. Start from a clean clone of the intended canonical commit. Confirm the
   default branch is clean and review the complete history for secrets and
   private operational data. The internal histories contain lab addressing and
   host labels, so they must remain private: export the reviewed tracked tree
   without `.git` and create one fresh public initial commit. Do not rewrite or
   push the canonical internal history.
2. Run that repository's documented local validation from the clean clone. For
   the integration, follow [`DEVELOPMENT.md`](DEVELOPMENT.md); for the client,
   run pytest, Ruff, strict mypy, and `python -m build` on every supported
   Python version represented by CI.
3. Verify the license, security policy, contribution/support material, links,
   package metadata, workflow permissions, and release notes. Screenshots and
   fixtures must be synthetic or sanitized.
4. With explicit owner approval, create the public repository and push only the
   reviewed snapshot branch. Compare its tree hash/file manifest with the
   approved export. Do not create a tag or GitHub Release as part of source
   publication.
5. Require the public CI results before continuing. Enable private
   vulnerability reporting and confirm the configured issue links resolve.

Record the public commit SHA and CI run URLs in the release evidence. Source
publication alone produces no installable client package or HACS release.

## 2. Build and publish the client package

The client workflow publishes to PyPI when a GitHub Release is published. A
draft release is therefore a useful review boundary; publishing it is the
package-publication action.

1. Confirm client CI passes on Python 3.12, 3.13, and 3.14 at the exact release
   commit. Confirm `pyproject.toml`, the changelog, and the proposed tag use one
   version and that the version does not already exist on PyPI.
2. Build from a clean clone with `python -m build`. Inspect the source archive
   and wheel contents, then install the wheel into a new virtual environment
   and run a minimal import/version check. The current pure-Python wheel is
   platform-independent, but it must also be installed and exercised on the
   intended ARM64 validation host.
3. Configure the repository's `pypi` environment and PyPI trusted publisher,
   with no long-lived PyPI token. Review the generated artifacts and release
   notes in a draft GitHub Release.
4. With explicit owner approval, publish the GitHub Release. Confirm the
   `Publish` workflow used OIDC and completed successfully, then download the
   artifacts from PyPI and compare their filenames and metadata with the local
   candidate.

If verification fails, stop promotion. Correct the code under a new version;
never replace an existing PyPI file. Yank a broken version when needed so new
installers avoid it, while retaining it for reproducibility. Document the
reason and the replacement version.

## 3. Create the integration and HACS release

The integration release workflow runs for tags matching `v*`, builds
`meshmonitor.zip` from `custom_components/meshmonitor`, and creates a GitHub
Release. Until the separately tracked dependency migration is complete, the
typed client remains vendored and `manifest.json` has no package requirement;
do not claim that publishing the client changes the integration dependency.

1. Confirm the integration manifest version, changelog heading, proposed
   `v<version>` tag, and release notes match. Confirm the manifest's Home
   Assistant minimum and all user-facing compatibility statements are current.
2. From a clean clone, run the full local validation and confirm public CI,
   Hassfest, and HACS validation pass at the exact commit. Inspect the component
   tree for caches, tests, credentials, local configuration, and private data.
3. Complete the authorized HA Lab verification below before tagging. Preserve
   a rollback point and record the deployed file hashes and Home Assistant,
   MeshMonitor, client, and integration versions.
   For the pre-v1 server/source registry redesign, use the owner-approved
   backed-up clean removal/reinstall path: remove source-shaped entries and add
   one exact-server entry only after deterministic gates pass. Do not claim or
   perform legacy registry migration.
4. With explicit owner approval, push the signed or annotated `v<version>` tag.
   Confirm the release workflow succeeds, `meshmonitor.zip` is attached, and
   its archive root contains the integration files expected by HACS.
5. Add the published repository to HACS as a custom **Integration** repository
   and verify the displayed version and metadata. Public HACS default-store
   inclusion, if pursued later, is a separate review and approval action.

A failed archive or lab verification blocks promotion. Fix it under a new
version and tag rather than moving a published tag. Mark a bad GitHub release
as unsuitable and direct users to the last known-good release or the corrected
version; do not silently replace published provenance.

## 4. Verify installation and rollback

Use only the designated HA Lab for project deployment checks. Do not discover,
probe, infer, mention, or interact with any other Home Assistant deployment.
Follow the current [`RELEASE.md`](../RELEASE.md) checklist and retain evidence
for each result.

Verify, in order:

1. a clean HACS install with no pre-populated `/config/deps` and successful
   Home Assistant configuration check and restart;
2. initial setup using the documented least-privilege permissions, entity and
   panel readiness, and no credential or private-data disclosure;
3. upgrade from the last supported release with config entries, options,
   browser preferences, and message baselines preserved;
4. temporary MeshMonitor outage and recovery without request overlap or replay;
5. rollback to the last known-good integration release using HACS, followed by
   configuration check, restart, and core workflow checks;
6. upgrade again to the candidate, then removal through Home Assistant and
   HACS, confirming integration-owned listeners, panels, and files are gone;
7. reinstall of the candidate, the 24-hour request-rate/recorder soak, token
   rotation and reauthentication, diagnostics/log privacy audit, and the one
   separately approved controlled message test.

Record timestamps, commit and tag SHAs, artifact checksum, backup identifier,
test versions, aggregate request/load measurements, sanitized log conclusions,
and pass/fail status. Evidence must not contain secrets or mesh/user identity.

## 5. Promote or hold

Production promotion is a decision, not an automatic deployment step. It is
eligible only when all source, package, integration, verification, and
promotion gates in `RELEASE.md` pass and the owner explicitly approves it.
State the known limitations and rollback version in that approval record.

If any gate fails, leave the candidate in the lab, record the blocker and
owner action, and keep the last known-good release as the rollback target. Do
not broaden MeshMonitor permissions, enable daily writes, perform radio or
administrative operations, or use another Home Assistant system to make a
release pass.
