"""Release metadata regression tests."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_prerelease_metadata_and_workflow_stay_aligned() -> None:
    """Keep the first HACS prerelease explicit and internally consistent."""
    manifest = json.loads(
        (ROOT / "custom_components/meshmonitor/manifest.json").read_text()
    )
    version = manifest["version"]

    assert version == "0.16.0-beta.1"
    assert f"## {version}" in (ROOT / "CHANGELOG.md").read_text()
    assert version in (ROOT / "README.md").read_text()

    release_workflow = (ROOT / ".github/workflows/release.yml").read_text()
    assert 'if [[ "v${version}" != "${GITHUB_REF_NAME}" ]]' in release_workflow
    assert "prerelease: ${{ contains(github.ref_name, '-') }}" in release_workflow
    assert "fail_on_unmatched_files: true" in release_workflow
    assert "unzip -t meshmonitor.zip" in release_workflow
