# Release checklist

Follow the staged [release process](docs/RELEASE_PROCESS.md). Each publication
or promotion step requires its own explicit owner approval; completing an
earlier section does not authorize a later one. Substitute the exact reviewed
metadata version wherever `<client-version>` or `<integration-version>` appears.

## GitHub publication

- [ ] Confirm the exact GitHub owner/repository names.
- [ ] Export a sanitized, tracked-file-only client snapshot with no internal `.git` history.
- [ ] Create `elier/python-meshmonitor` and push one reviewed initial commit.
- [ ] Confirm client CI passes on Python 3.12, 3.13, and 3.14.
- [ ] Enable private vulnerability reporting.
- [ ] Export a sanitized, tracked-file-only integration snapshot with no internal `.git` history.
- [ ] Create `elier/home-assistant-meshmonitor` and push one reviewed initial commit.
- [ ] Confirm tests, Hassfest, and HACS validation pass.

## Package and integration release

- [ ] Configure PyPI trusted publishing for `meshmonitor-api-client`.
- [ ] Publish client `<client-version>` and verify its wheel on ARM64.
- [ ] Replace the vendored client with the exact pinned PyPI requirement.
- [ ] Test a clean HAOS install with no pre-populated `/config/deps`.
- [ ] Tag integration `v<integration-version>` and verify the attached
      `meshmonitor.zip` checksum and contents.
- [ ] Test HACS install, upgrade, rollback, and removal.

## Promotion gates

- [ ] Complete a 24-hour lab soak with recorder/request-rate measurements.
- [ ] Rotate a token and validate reauthentication end to end.
- [ ] Observe or approve one controlled real message test.
- [ ] Audit diagnostics and logs for sensitive-data leakage.
- [ ] Keep production Home Assistant untouched until every gate passes.
