"""Release metadata regression tests."""

import json
import os
import re
import shutil
import struct
import subprocess
import zipfile
import zlib
from pathlib import Path

from scripts.repository_checks import (
    REQUIRED_ARCHIVE_FILES,
    build_archive,
    release_metadata_problems,
    screenshot_problems,
)

ROOT = Path(__file__).parents[1]


def test_release_metadata_and_workflow_stay_aligned() -> None:
    """Keep release metadata generic and publication behind all validation."""
    manifest = json.loads(
        (ROOT / "custom_components/meshmonitor/manifest.json").read_text()
    )
    version = manifest["version"]

    assert release_metadata_problems(ROOT) == []

    release_workflow = (ROOT / ".github/workflows/release.yml").read_text()
    validate_workflow = (ROOT / ".github/workflows/validate.yml").read_text()
    assert "uses: ./.github/workflows/validate.yml" in release_workflow
    assert "needs: validation" in release_workflow
    assert "workflow_dispatch:" in release_workflow
    assert "github.ref == 'refs/heads/main'" in release_workflow
    assert 'test "${GITHUB_SHA}" = "$(git rev-parse refs/remotes/origin/main)"' in release_workflow
    assert "git ls-remote --tags" in release_workflow
    assert "persist-credentials: false" in release_workflow
    assert "environment: release" in release_workflow
    assert "overwrite_files: false" in release_workflow
    assert "draft: true" in release_workflow
    assert "actions/upload-artifact@" in release_workflow
    assert "actions/download-artifact@" in release_workflow
    assert "RELEASE_TAG: ${{ inputs.tag }}" in release_workflow
    assert 'metadata --tag "${RELEASE_TAG}"' in release_workflow
    assert "github.rest.git.createRef" in release_workflow
    assert "tag_name: ${{ inputs.tag }}" in release_workflow
    assert "target_commitish: ${{ github.sha }}" in release_workflow
    assert "prerelease: ${{ contains(inputs.tag, '-') }}" in release_workflow
    assert "fail_on_unmatched_files: true" in release_workflow
    assert "SHA256SUMS" in release_workflow
    assert "attest-build-provenance@" in release_workflow
    assert "repository_checks.py hygiene" in validate_workflow
    assert "repository_checks.py links" in validate_workflow
    assert "npm ci --ignore-scripts" in validate_workflow
    assert "npx --no-install markdownlint-cli2" in validate_workflow
    assert version in (ROOT / "CHANGELOG.md").read_text()

    workflows = "\n".join(
        path.read_text() for path in (ROOT / ".github/workflows").glob("*.y*ml")
    )
    action_references = re.findall(r"uses:\s+([^\s]+)", workflows)
    assert action_references
    assert all(
        reference.startswith("./") or re.search(r"@[0-9a-f]{40}$", reference)
        for reference in action_references
    )


def _write_release_metadata(root: Path, version: str, unreleased: str = "") -> None:
    component = root / "custom_components/meshmonitor"
    component.mkdir(parents=True, exist_ok=True)
    (component / "manifest.json").write_text(json.dumps({"version": version}))
    (root / "pyproject.toml").write_text(f'[project]\nversion = "{version}"\n')
    (root / "CHANGELOG.md").write_text(
        f"# Changelog\n\n## Unreleased\n\n{unreleased}\n## {version}\n\n- Candidate.\n"
    )


def test_tag_metadata_requires_exact_version_and_finalized_changelog(tmp_path: Path) -> None:
    """Accept only an exact tag whose candidate is first after empty Unreleased."""
    _write_release_metadata(tmp_path, "1.2.3")
    assert release_metadata_problems(tmp_path, "v1.2.3") == []

    assert any(
        "does not match" in problem
        for problem in release_metadata_problems(tmp_path, "v1.2.4")
    )
    _write_release_metadata(tmp_path, "1.2.3", "- Pending work.\n")
    assert any(
        "must be empty" in problem
        for problem in release_metadata_problems(tmp_path, "v1.2.3")
    )


def test_release_metadata_rejects_hidden_duplicate_and_malformed_versions(tmp_path: Path) -> None:
    """Ignore non-rendered headings and reject duplicate or invalid release state."""
    _write_release_metadata(tmp_path, "1.2.3")
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(changelog.read_text() + "\n## 1.2.3\n")
    assert any("exactly one 1.2.3" in item for item in release_metadata_problems(tmp_path))

    _write_release_metadata(tmp_path, "1.2.3")
    changelog.write_text("# Changelog\n\n```text\n## Unreleased\n## 1.2.3\n```\n")
    assert release_metadata_problems(tmp_path)

    _write_release_metadata(tmp_path, "1.2.3-01")
    assert any("leading-zero" in item for item in release_metadata_problems(tmp_path))


def test_hacs_archive_is_allowlisted_reproducible_and_checksummed(tmp_path: Path) -> None:
    """Build identical archives containing exactly tracked component files."""
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"

    first_digest = build_archive(ROOT, first)
    second_digest = build_archive(ROOT, second)

    assert first_digest == second_digest
    assert first.read_bytes() == second.read_bytes()
    assert (tmp_path / "SHA256SUMS").read_text() == f"{second_digest}  second.zip\n"
    with zipfile.ZipFile(first) as archive:
        names = archive.namelist()
        assert "manifest.json" in names
        assert "frontend/meshmonitor-panel.js" in names
        assert all(not name.startswith(("/", "custom_components/")) for name in names)
        assert all(".." not in Path(name).parts for name in names)


def test_archive_rejects_unallowlisted_component_file(tmp_path: Path) -> None:
    """Fail closed when a new component file has not been reviewed for packaging."""
    root = tmp_path / "repository"
    component = root / "custom_components/meshmonitor"
    component.mkdir(parents=True)
    for relative in (
        "__init__.py",
        "frontend/meshmonitor-panel.js",
        "frontend/vendor/leaflet/LICENSE",
        "manifest.json",
        "services.yaml",
        "strings.json",
        "translations/en.json",
        "vendor_meshmonitor_client/py.typed",
        "unexpected.txt",
    ):
        path = component / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}" if path.suffix == ".json" else "fixture\n")
    subprocess.run(["git", "init", "--quiet", str(root)], check=True)
    allowed = [
        path.relative_to(component).as_posix()
        for path in component.rglob("*")
        if path.is_file() and path.name != "unexpected.txt"
    ]
    (root / "release-archive-files.txt").write_text("\n".join(sorted(allowed)) + "\n")
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)

    try:
        build_archive(root, root / "meshmonitor.zip")
    except ValueError as err:
        assert "absent from release-archive-files.txt" in str(err)
    else:
        raise AssertionError("unallowlisted component file was packaged")


def test_archive_rejects_symlinked_parent_directory(tmp_path: Path) -> None:
    """Do not package tracked files through an external directory symlink."""
    root = tmp_path / "repository"
    component = root / "custom_components/meshmonitor"
    for relative in sorted(REQUIRED_ARCHIVE_FILES):
        path = component / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}" if path.suffix == ".json" else "fixture\n")
    (root / "release-archive-files.txt").write_text(
        "\n".join(sorted(REQUIRED_ARCHIVE_FILES)) + "\n"
    )
    subprocess.run(["git", "init", "--quiet", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)

    outside = tmp_path / "external-frontend"
    shutil.copytree(component / "frontend", outside)
    shutil.rmtree(component / "frontend")
    os.symlink(outside, component / "frontend")

    try:
        build_archive(root, root / "meshmonitor.zip")
    except ValueError as err:
        assert "unsafe release archive file" in str(err)
    else:
        raise AssertionError("symlinked parent directory was packaged")


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


def test_documentation_screenshots_match_reviewed_hashes_and_sizes() -> None:
    """Keep generated panel images aligned with their public provenance notes."""
    assert screenshot_problems(ROOT) == []


def test_documentation_screenshots_reject_trailing_data(tmp_path: Path) -> None:
    """Reject PNG payloads that can hide unreviewed trailing content."""
    image_dir = tmp_path / "docs" / "images"
    shutil.copytree(ROOT / "docs" / "images", image_dir)
    screenshot = image_dir / "panel-overview.png"
    screenshot.write_bytes(screenshot.read_bytes() + b"private trailing data")

    problems = screenshot_problems(tmp_path)
    assert any("trailing PNG data" in item for item in problems)


def test_documentation_screenshots_reject_unknown_ancillary_chunks(
    tmp_path: Path,
) -> None:
    """Reject unreviewed PNG chunks even when their CRC is valid."""
    image_dir = tmp_path / "docs" / "images"
    shutil.copytree(ROOT / "docs" / "images", image_dir)
    screenshot = image_dir / "panel-overview.png"
    data = screenshot.read_bytes()
    payload = b"hidden metadata"
    chunk_type = b"vpAg"
    chunk = (
        struct.pack(">I", len(payload))
        + chunk_type
        + payload
        + struct.pack(">I", zlib.crc32(chunk_type + payload) & 0xFFFFFFFF)
    )
    iend = data.rfind(b"\x00\x00\x00\x00IEND")
    screenshot.write_bytes(data[:iend] + chunk + data[iend:])

    problems = screenshot_problems(tmp_path)
    assert any("unapproved PNG chunks" in item for item in problems)
