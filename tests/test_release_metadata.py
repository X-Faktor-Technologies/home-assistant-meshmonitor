"""Release metadata regression tests."""

import json
import struct
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_stable_release_metadata_and_workflow_stay_aligned() -> None:
    """Keep the first stable HACS release explicit and internally consistent."""
    manifest = json.loads(
        (ROOT / "custom_components/meshmonitor/manifest.json").read_text()
    )
    version = manifest["version"]

    assert version == "0.16.0"
    assert f"## {version}" in (ROOT / "CHANGELOG.md").read_text()
    assert version in (ROOT / "README.md").read_text()

    release_workflow = (ROOT / ".github/workflows/release.yml").read_text()
    assert 'if [[ "v${version}" != "${GITHUB_REF_NAME}" ]]' in release_workflow
    assert "prerelease: ${{ contains(github.ref_name, '-') }}" in release_workflow
    assert "fail_on_unmatched_files: true" in release_workflow
    assert "unzip -t meshmonitor.zip" in release_workflow


def test_stable_install_does_not_require_prerelease_tracking() -> None:
    """Keep the normal HACS install path free of beta-only setup steps."""
    readme = " ".join((ROOT / "README.md").read_text().split())

    assert "HACS selects the latest stable release automatically" in readme
    assert "prerelease tracking is not required" in readme
    assert "MeshMonitor pre-release" not in readme


def test_brand_icons_have_expected_sizes_and_alpha() -> None:
    """Prevent opaque or incorrectly sized brand exports from shipping."""
    brand_dir = ROOT / "custom_components/meshmonitor/brand"

    for filename, expected_size in (("icon.png", 256), ("icon@2x.png", 512)):
        data = (brand_dir / filename).read_bytes()
        assert data[:8] == b"\x89PNG\r\n\x1a\n"
        width, height, _depth, color_type = struct.unpack(">IIBB", data[16:26])

        assert (width, height) == (expected_size, expected_size)
        assert color_type in {4, 6} or b"tRNS" in data, (
            f"{filename} must include transparency"
        )
