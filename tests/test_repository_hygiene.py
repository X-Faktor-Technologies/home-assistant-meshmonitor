"""Regression tests for repository publication hygiene."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from scripts import repository_checks
from scripts.repository_checks import (
    external_link_problems,
    hygiene_problems,
    public_url_problem,
    relative_link_problems,
)


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _repository(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    root.mkdir(parents=True)
    _git(root, "init", "--quiet")
    (root / "README.md").write_text("# Synthetic project\n")
    _git(root, "add", "README.md")
    return root


def test_hygiene_rejects_tracked_repository_debris(tmp_path: Path) -> None:
    """Reject representative prohibited tracked names and content."""
    cases = [
        ("AGENTS.md", "instructions\n", "AI/internal workflow"),
        ("reports/run.log", "safe\n", "archive, database, log, backup"),
        ("src/cache/__pycache__/state", "safe\n", "cache directory"),
        (
            "notes.txt",
            "developer path: /home/" + "alice/project\n",
            "private host path",
        ),
        (
            "network.txt",
            "service = " + ".".join(("192", "168", "4", "20")) + "\n",
            "private-network literal",
        ),
        (
            "ipv6.txt",
            "service = " + "fc00" + "::42\n",
            "private IPv6 literal",
        ),
        (
            "config.txt",
            "api_" + 'key = "ghp_' + 'abcdefghijklmnopqrstuvwxyz1234567890"\n',
            "credential-like content",
        ),
    ]
    for index, (relative, content, expected) in enumerate(cases):
        root = _repository(tmp_path / str(index))
        candidate = root / relative
        candidate.parent.mkdir(parents=True, exist_ok=True)
        candidate.write_text(content)
        _git(root, "add", relative)

        assert any(expected in problem for problem in hygiene_problems(root))


def test_hygiene_allows_reserved_hosts_and_obvious_fixture_credentials(tmp_path: Path) -> None:
    """Do not flag explicit synthetic values used by deterministic tests."""
    root = _repository(tmp_path)
    fixture = root / "fixture.py"
    fixture.write_text(
        'URL = "https://user:secret@mesh.test"\nTOKEN = "synthetic-token"\n'
    )
    _git(root, "add", "fixture.py")

    assert hygiene_problems(root) == []


def test_hygiene_rejects_tracked_symlinks(tmp_path: Path) -> None:
    """Do not permit indirection outside the reviewed tracked tree."""
    root = _repository(tmp_path)
    os.symlink("README.md", root / "linked-readme")
    _git(root, "add", "linked-readme")

    assert any("tracked symlink" in problem for problem in hygiene_problems(root))


def test_hygiene_rejects_nonignored_untracked_debris(tmp_path: Path) -> None:
    """Catch forgotten local files before they can be staged for publication."""
    root = _repository(tmp_path)
    scratch = root / ".openclaw" / "release-notes.md"
    scratch.parent.mkdir()
    scratch.write_text("internal notes\n")

    assert any("AI/internal workflow" in problem for problem in hygiene_problems(root))


def test_hygiene_rejects_common_generic_secret_forms(tmp_path: Path) -> None:
    """Cover JSON, dotenv, authorization-header, and JWT-style credentials."""
    cases = [
        '"to' + 'ken": "abcdefghijklmnop1234567890"\n',
        "TO" + "KEN=abcdefghijklmnop1234567890\n",
        "Authoriza" + "tion: Bearer abcdefghijklmnop1234567890\n",
        "ey" + "Jabcdefghijklmnop.qrstuvwxyzabcdef.ghijklmnopqrstuv\n",
        "AWS_SECRET_ACCESS_" + "KEY=production-secret-abcdefghijklmnop\n",
        "SLACK_TOKEN=xox" + "b-123456789012345678901234\n",
        "api_key: |\n  productionvalueabcdefghijklmnop\n",
    ]
    for index, content in enumerate(cases):
        root = _repository(tmp_path / str(index))
        candidate = root / "candidate.txt"
        candidate.write_text(content)

        assert hygiene_problems(root)


def test_hygiene_rejects_tracked_file_replaced_by_symlink(tmp_path: Path) -> None:
    """Use the worktree file type rather than trusting only the index mode."""
    root = _repository(tmp_path)
    candidate = root / "payload.txt"
    candidate.write_text("reviewed\n")
    _git(root, "add", "payload.txt")
    candidate.unlink()
    os.symlink("README.md", candidate)

    assert any("tracked symlink" in problem for problem in hygiene_problems(root))


def test_hygiene_rejects_tracked_parent_replaced_by_symlink(tmp_path: Path) -> None:
    """Reject files reached through a worktree directory symlink."""
    root = _repository(tmp_path)
    directory = root / "docs"
    directory.mkdir()
    candidate = directory / "guide.md"
    candidate.write_text("# Reviewed\n")
    _git(root, "add", "docs/guide.md")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "guide.md").write_text("# External\n")
    candidate.unlink()
    directory.rmdir()
    os.symlink(outside, directory)

    assert any("tracked symlink" in problem for problem in hygiene_problems(root))


def test_hygiene_scans_plaintext_runs_in_binary_files(tmp_path: Path) -> None:
    """Do not let a NUL byte suppress private-data detection."""
    root = _repository(tmp_path)
    candidate = root / "asset.bin"
    candidate.write_bytes(b"\x00private path /home/" + b"alice/project\x00")

    assert any("private host path" in problem for problem in hygiene_problems(root))


def test_relative_links_cannot_leave_repository(tmp_path: Path) -> None:
    """Reject absolute, traversal, and symlink-escape documentation targets."""
    root = _repository(tmp_path)
    outside = tmp_path / "outside.md"
    outside.write_text("# Outside\n")
    os.symlink(outside, root / "outside-link.md")
    readme = root / "README.md"
    readme.write_text(
        "# Synthetic project\n\n"
        "[absolute](/etc/passwd)\n"
        "[traversal](../outside.md)\n"
        "[symlink](outside-link.md)\n"
    )

    problems = relative_link_problems(root)
    assert len(problems) == 3
    assert all("absolute local target" in item or "leaves repository" in item for item in problems)


def test_external_link_policy_rejects_nonpublic_destinations() -> None:
    """Prevent the scheduled checker from reaching local or private services."""
    assert public_url_problem("http://127.0.0.1/status") is not None
    private_address = ".".join(("192", "168", "10", "4"))
    assert public_url_problem(f"http://{private_address}/status") is not None
    assert public_url_problem("http://[::1]/status") is not None
    assert public_url_problem("http://100.64.0.1/status") is not None
    assert public_url_problem("http://[fec0::1]/status") is not None
    credential_url = "https://user:" + "password@example.com/"
    assert public_url_problem(credential_url) is not None


def test_external_link_failures_are_not_treated_as_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fail closed on HTTP and transport failures after bounded retries."""
    root = _repository(tmp_path)
    (root / "README.md").write_text("[remote](https://docs.example.org/missing)\n")
    attempts = []

    def request_status(_url: str, method: str) -> int:
        attempts.append(method)
        return 404

    monkeypatch.setattr(repository_checks, "public_url_problem", lambda _url: None)
    monkeypatch.setattr(repository_checks, "_request_status", request_status)
    monkeypatch.setattr(repository_checks.time, "sleep", lambda _seconds: None)

    problems = external_link_problems(root)
    assert len(problems) == 1
    assert "HTTP 404" in problems[0]
    assert attempts == ["HEAD", "HEAD", "HEAD"]


def test_external_request_pins_the_validated_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Connect to the validated address without a second DNS lookup."""
    connected = []

    class Socket:
        pass

    monkeypatch.setattr(
        repository_checks,
        "_public_addresses",
        lambda _url: ([repository_checks.ipaddress.ip_address("203.0.113.10")], None),
    )
    monkeypatch.setattr(
        repository_checks.socket,
        "create_connection",
        lambda destination, _timeout: connected.append(destination) or Socket(),
    )
    connection = repository_checks._PinnedHTTPConnection(
        "docs.example.org", 80, "203.0.113.10", 15
    )
    connection.connect()

    assert connected == [("203.0.113.10", 80)]
