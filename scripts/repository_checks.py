#!/usr/bin/env python3
"""Deterministic repository, documentation, and release checks."""

from __future__ import annotations

import argparse
import hashlib
import http.client
import ipaddress
import json
import os
import re
import socket
import ssl
import struct
import subprocess
import sys
import time
import tomllib
import urllib.parse
import zipfile
import zlib
from collections.abc import Iterable
from pathlib import Path, PurePosixPath

COMPONENT = PurePosixPath("custom_components/meshmonitor")
REQUIRED_ARCHIVE_FILES = {
    "__init__.py",
    "frontend/meshmonitor-panel.js",
    "frontend/vendor/leaflet/LICENSE",
    "manifest.json",
    "services.yaml",
    "strings.json",
    "translations/en.json",
    "vendor_meshmonitor_client/py.typed",
}
DOCUMENTED_SCREENSHOTS = {
    "panel-overview.png": (1440, 900),
    "panel-conversations.png": (1440, 900),
    "panel-nodes.png": (1440, 900),
    "panel-map.png": (1600, 900),
    "setup-connect.png": (580, 404),
    "setup-find-integration.png": (580, 520),
    "setup-options-menu.png": (580, 272),
    "setup-server-settings.png": (580, 520),
}
PNG_PRIVATE_CHUNKS = {b"eXIf", b"iCCP", b"iTXt", b"tEXt", b"zTXt"}
PNG_ALLOWED_CHUNKS = {b"IDAT", b"IEND", b"IHDR"}
FORBIDDEN_PARTS = {
    ".agents",
    ".ai",
    ".claude",
    ".cursor",
    ".hypothesis",
    ".internal",
    ".mypy_cache",
    ".nox",
    ".openclaw",
    ".opencode",
    ".planning",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    ".cache",
    "__pycache__",
    "htmlcov",
    "node_modules",
    "prompts",
}
FORBIDDEN_NAMES = {
    ".coverage",
    ".ds_store",
    "agents.md",
    "ai-notes.md",
    "agent.md",
    "claude.md",
    "copilot-instructions.md",
    "implementation-plan.md",
    "gemini.md",
    "prompt.md",
    "prompts.md",
    "session.md",
}
FORBIDDEN_SUFFIXES = {
    ".7z",
    ".bak",
    ".backup",
    ".bz2",
    ".db",
    ".db-shm",
    ".db-wal",
    ".gz",
    ".key",
    ".log",
    ".orig",
    ".p12",
    ".pem",
    ".pfx",
    ".pyc",
    ".rar",
    ".rej",
    ".sqlite",
    ".sqlite3",
    ".dump",
    ".swp",
    ".tar",
    ".tgz",
    ".tmp",
    ".xz",
    ".zip",
}
PLACEHOLDER_VALUES = {
    "must-not-leak",
    "replacement-secret",
    "secret-token",
    "stored-secret",
}


def _git(root: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(root), *args])


def tracked_files(root: Path) -> list[tuple[str, Path]]:
    """Return mode and path for every tracked entry."""
    output = _git(root, "ls-files", "--stage", "-z")
    entries: list[tuple[str, Path]] = []
    for record in output.split(b"\0"):
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        mode = metadata.split(b" ", 1)[0].decode()
        entries.append((mode, Path(raw_path.decode("utf-8"))))
    return entries


def repository_files(root: Path) -> list[tuple[str, Path]]:
    """Return tracked and non-ignored untracked files for a local hygiene pass."""
    entries = [
        ("120000" if (root / path).is_symlink() else mode, path)
        for mode, path in tracked_files(root)
    ]
    known = {path for _, path in entries}
    output = _git(root, "ls-files", "--others", "--exclude-standard", "-z")
    for raw_path in output.split(b"\0"):
        if not raw_path:
            continue
        path = Path(raw_path.decode("utf-8"))
        if path in known:
            continue
        candidate = root / path
        if candidate.is_symlink():
            mode = "120000"
        else:
            mode = "100755" if os.access(candidate, os.X_OK) else "100644"
        entries.append((mode, path))
    return sorted(entries, key=lambda entry: entry[1].as_posix())


def _has_symlink_component(root: Path, relative: Path) -> bool:
    """Return whether a worktree path or one of its parents is a symlink."""
    candidate = root
    for part in relative.parts:
        candidate /= part
        if candidate.is_symlink():
            return True
    return False


def _path_problem(path: Path) -> str | None:
    lowered_parts = {part.lower() for part in path.parts}
    name = path.name.lower()
    if lowered_parts & FORBIDDEN_PARTS:
        return "AI/internal workflow or cache directory"
    if name in FORBIDDEN_NAMES:
        return "AI/internal workflow or generated file"
    if name == ".env" or name.startswith(".env."):
        return "local environment file"
    if name.endswith("~"):
        return "backup debris"
    if any(name.endswith(suffix) for suffix in FORBIDDEN_SUFFIXES):
        return "archive, database, log, backup, or cache debris"
    return None


def _is_placeholder_value(value: str) -> bool:
    value = value.strip().lower()
    return value in PLACEHOLDER_VALUES or bool(
        re.fullmatch(
            r"(?:changeme|dummy|example|fake|not-a-real|redacted|synthetic|test)"
            r"(?:[-_](?:credential|key|password|secret|token|value)){0,2}",
            value,
        )
    )


def _content_problems(text: str) -> list[str]:
    problems: list[str] = []
    private_path = re.compile(
        r"(?:/(?:home|Users)/[A-Za-z0-9._-]+/|"
        r"[A-Za-z]:\\Users\\[A-Za-z0-9._-]+\\)"
    )
    if private_path.search(text):
        problems.append("private host path")

    ipv4 = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
    for match in ipv4.finditer(text):
        octets = tuple(int(part) for part in match.group().split("."))
        if any(part > 255 for part in octets):
            continue
        first, second, _, _ = octets
        if (
            first == 10
            or (first == 169 and second == 254)
            or (first == 172 and 16 <= second <= 31)
            or (first == 192 and second == 168)
        ):
            problems.append(f"private-network literal {match.group()}")
            break
    ipv6_private = re.compile(
        r"(?i)(?<![0-9a-f:])"
        r"(?:(?:f[cd][0-9a-f]{2}|fe[89ab][0-9a-f]):[0-9a-f:]+)"
        r"(?![0-9a-f:])"
    )
    if ipv6_private.search(text):
        problems.append("private IPv6 literal")
    high_confidence = (
        re.compile(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----"),
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
        re.compile(r"\bpypi-[A-Za-z0-9_-]{30,}\b"),
        re.compile(r"\bgithub_pat_[A-Za-z0-9_]{30,}\b"),
        re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b"),
        re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
        re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"),
    )
    if any(pattern.search(text) for pattern in high_confidence):
        problems.append("credential-like content")

    userinfo = re.compile(r"https?://[^\s\"'<>]+:[^\s\"'<>/@]+@[^\s\"'<>]+")
    for match in userinfo.finditer(text):
        host = (urllib.parse.urlsplit(match.group()).hostname or "").lower()
        if not host.endswith((".example", ".example.com", ".invalid", ".test")):
            problems.append("credential-like URL")
            break

    assignment = re.compile(
        r"(?im)[\"']?(?:[A-Z0-9]+[_-])*"
        r"(?:api[_-]?key|password|passwd|secret(?:[_-]?access)?[_-]?key|token)[\"']?"
        r"\s*[:=]\s*(?:\"([^\"\r\n]+)\"|'([^'\r\n]+)'|"
        r"([^\s,#}\]\"'()\[=]+))"
    )
    for match in assignment.finditer(text):
        value = next(group for group in match.groups() if group is not None).lower()
        if len(value) < 16:
            continue
        if re.fullmatch(r"[a-z ()_-]+", value) and any(character.isspace() for character in value):
            continue
        if not _is_placeholder_value(value):
            problems.append("credential-like assignment")
            break
    block_assignment = re.compile(
        r"(?im)^[ \t]*(?:[A-Z0-9]+[_-])*(?:api[_-]?key|password|passwd|"
        r"secret(?:[_-]?access)?[_-]?key|token)[ \t]*:[ \t]*[>|][-+0-9]*[ \t]*\n"
        r"[ \t]+([^\r\n]+)"
    )
    for match in block_assignment.finditer(text):
        value = match.group(1).strip().lower()
        if len(value) >= 16 and not _is_placeholder_value(value):
            problems.append("credential-like block assignment")
            break
    authorization = re.compile(r"(?im)^\s*authorization\s*:\s*bearer\s+([^\s]{16,})")
    for match in authorization.finditer(text):
        value = match.group(1).lower()
        if not _is_placeholder_value(value):
            problems.append("credential-like authorization header")
            break
    jwt = re.compile(r"\beyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{8,}\b")
    if jwt.search(text):
        problems.append("credential-like JWT")
    return problems


def _binary_content_problems(data: bytes) -> list[str]:
    """Inspect printable binary runs for accidental plain-text private data."""
    printable = b"\n".join(re.findall(rb"[\x20-\x7e]{8,}", data)).decode("ascii")
    return _content_problems(printable)


def hygiene_problems(root: Path) -> list[str]:
    """Inspect tracked and non-ignored untracked entries for publication debris."""
    problems: list[str] = []
    for mode, relative in repository_files(root):
        if mode == "120000" or _has_symlink_component(root, relative):
            problems.append(f"{relative}: tracked symlink")
            continue
        if mode not in {"100644", "100755"}:
            problems.append(f"{relative}: unsupported tracked mode {mode}")
            continue
        if problem := _path_problem(relative):
            problems.append(f"{relative}: {problem}")
        candidate = root / relative
        if not candidate.is_file():
            problems.append(f"{relative}: tracked file missing from worktree")
            continue
        data = candidate.read_bytes()
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            problems.extend(
                f"{relative}: {problem}" for problem in _binary_content_problems(data)
            )
            continue
        if b"\0" in data:
            problems.extend(
                f"{relative}: {problem}" for problem in _binary_content_problems(data)
            )
            continue
        problems.extend(f"{relative}: {problem}" for problem in _content_problems(text))
    return problems


def _markdown_files(root: Path) -> list[Path]:
    return [
        root / path
        for mode, path in repository_files(root)
        if mode != "120000" and path.suffix.lower() == ".md"
    ]


def _without_code_fences(text: str) -> str:
    lines: list[str] = []
    in_fence = False
    marker = ""
    for line in text.splitlines():
        stripped = line.lstrip()
        fence = re.match(r"(`{3,}|~{3,})", stripped)
        if fence:
            candidate = fence.group(1)
            if not in_fence:
                in_fence, marker = True, candidate
            elif candidate[0] == marker[0] and len(candidate) >= len(marker):
                in_fence = False
            lines.append("")
        else:
            lines.append("" if in_fence else line)
    return "\n".join(lines)


def _links(text: str) -> set[str]:
    text = re.sub(r"<!--.*?-->", "", _without_code_fences(text), flags=re.DOTALL)
    text = re.sub(r"`[^`\n]*`", "", text)
    links = {
        match.group(1).strip("<>")
        for match in re.finditer(
            r"!?\[[^\]]*\]\((<[^>]+>|[^\s)]+)(?:\s+[^)]*)?\)", text
        )
    }
    links.update(
        match.group(1)
        for match in re.finditer(
            r"^\s*\[[^\]]+\]:\s*<?([^\s>]+)>?", text, re.MULTILINE
        )
    )
    links.update(
        match.group(1)
        for match in re.finditer(r"<(https?://[^>]+)>", text)
    )
    links.update(
        match.group(2)
        for match in re.finditer(
            r"<(?:a|img)\b[^>]+(?:href|src)=([\"'])(.*?)\1", text, re.IGNORECASE
        )
    )
    links.update(
        match.group(1)
        for match in re.finditer(
            r"<(?:a|img)\b[^>]+(?:href|src)=([^\s>]+)", text, re.IGNORECASE
        )
    )
    links.update(
        match.group(0).rstrip(".,;:!?")
        for match in re.finditer(r"(?<![<(])https?://[^\s<>\"']+", text)
    )
    return links


def _slug(value: str) -> str:
    value = re.sub(r"<[^>]+>", "", value).strip().lower()
    value = re.sub(r"[^\w\- ]", "", value)
    return re.sub(r"[ ]+", "-", value)


def _anchors(text: str) -> set[str]:
    anchors: set[str] = set()
    counts: dict[str, int] = {}
    for match in re.finditer(
        r"^#{1,6}\s+(.+?)\s*#*\s*$", _without_code_fences(text), re.MULTILINE
    ):
        base = _slug(match.group(1))
        count = counts.get(base, 0)
        anchors.add(base if count == 0 else f"{base}-{count}")
        counts[base] = count + 1
    anchors.update(
        match.group(1)
        for match in re.finditer(
            r"<a\s+(?:name|id)=[\"']([^\"']+)", text, re.IGNORECASE
        )
    )
    return anchors


def relative_link_problems(root: Path) -> list[str]:
    """Check tracked Markdown file targets and anchors without network access."""
    problems: list[str] = []
    for markdown in _markdown_files(root):
        for target in sorted(_links(markdown.read_text(encoding="utf-8"))):
            parsed = urllib.parse.urlsplit(target)
            if target.startswith("//"):
                problems.append(
                    f"{markdown.relative_to(root)}: protocol-relative target {target}"
                )
                continue
            if parsed.scheme:
                if parsed.scheme.lower() in {"http", "https", "mailto"}:
                    continue
                problems.append(
                    f"{markdown.relative_to(root)}: unsupported target scheme {target}"
                )
                continue
            raw_path = urllib.parse.unquote(parsed.path)
            if Path(raw_path).is_absolute():
                problems.append(f"{markdown.relative_to(root)}: absolute local target {target}")
                continue
            destination = (markdown if not raw_path else markdown.parent / raw_path).resolve()
            try:
                destination.relative_to(root.resolve())
            except ValueError:
                problems.append(f"{markdown.relative_to(root)}: target leaves repository {target}")
                continue
            if not destination.exists():
                problems.append(f"{markdown.relative_to(root)}: missing target {target}")
                continue
            if (
                parsed.fragment
                and destination.is_file()
                and destination.suffix.lower() == ".md"
            ):
                anchors = _anchors(destination.read_text(encoding="utf-8"))
                fragment = urllib.parse.unquote(parsed.fragment).lower()
                if fragment not in anchors:
                    problems.append(
                        f"{markdown.relative_to(root)}: missing anchor #{fragment} in "
                        f"{destination.relative_to(root)}"
                    )
    return problems


def _external_urls(root: Path) -> set[str]:
    urls: set[str] = set()
    for markdown in _markdown_files(root):
        for target in _links(markdown.read_text(encoding="utf-8")):
            if urllib.parse.urlsplit(target).scheme in {"http", "https"}:
                urls.add(target)
    return urls


def _public_addresses(
    url: str,
) -> tuple[list[ipaddress.IPv4Address | ipaddress.IPv6Address], str | None]:
    """Resolve a URL once and return only verified public destination addresses."""
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return [], "unsupported or missing URL host"
    if parsed.username is not None or parsed.password is not None:
        return [], "credential-bearing URL"
    host = parsed.hostname.lower().rstrip(".")
    if host == "localhost" or host.endswith((".localhost", ".local")):
        return [], "local hostname"
    try:
        addresses = {ipaddress.ip_address(host)}
    except ValueError:
        try:
            addresses = {
                ipaddress.ip_address(item[4][0])
                for item in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
            }
        except OSError as err:
            return [], f"DNS lookup failed: {err}"
    if any(
        not address.is_global or getattr(address, "is_site_local", False)
        for address in addresses
    ):
        return [], "host resolves to a non-public address"
    return sorted(addresses, key=str), None


def public_url_problem(url: str) -> str | None:
    """Reject external-check destinations that may reach a private network."""
    return _public_addresses(url)[1]


class _PinnedHTTPConnection(http.client.HTTPConnection):
    """Connect to a previously validated address without resolving again."""

    def __init__(self, host: str, port: int, address: str, timeout: int) -> None:
        super().__init__(host, port=port, timeout=timeout)
        self._validated_address = address

    def connect(self) -> None:
        self.sock = socket.create_connection(
            (self._validated_address, self.port), self.timeout
        )


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """Use public pinned routing while retaining hostname TLS verification."""

    def __init__(self, host: str, port: int, address: str, timeout: int) -> None:
        super().__init__(
            host,
            port=port,
            timeout=timeout,
            context=ssl.create_default_context(),
        )
        self._validated_address = address

    def connect(self) -> None:
        raw = socket.create_connection(
            (self._validated_address, self.port), self.timeout
        )
        self.sock = self._context.wrap_socket(raw, server_hostname=self.host)


def _request_status(url: str, method: str, redirects: int = 5) -> int:
    """Request one URL using a DNS-pinned public address and safe redirects."""
    if redirects < 0:
        raise OSError("too many redirects")
    parsed = urllib.parse.urlsplit(url)
    addresses, problem = _public_addresses(url)
    if problem:
        raise OSError(problem)
    host = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    connection_type = (
        _PinnedHTTPSConnection if parsed.scheme == "https" else _PinnedHTTPConnection
    )
    connection = connection_type(host, port, str(addresses[0]), 15)
    path = urllib.parse.urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
    try:
        connection.request(
            method,
            path,
            headers={"Range": "bytes=0-0", "User-Agent": "MeshMonitor-link-check/1.0"},
        )
        response = connection.getresponse()
        status = response.status
        location = response.getheader("Location")
        response.read(1)
    finally:
        connection.close()
    if status in {301, 302, 303, 307, 308}:
        if not location:
            raise OSError(f"HTTP {status} redirect has no Location header")
        return _request_status(urllib.parse.urljoin(url, location), method, redirects - 1)
    return status


def external_link_problems(root: Path) -> list[str]:
    """Check public links conservatively for the scheduled CI job."""
    problems: list[str] = []
    for url in sorted(_external_urls(root)):
        host = (urllib.parse.urlsplit(url).hostname or "").lower()
        if host.endswith((".example", ".example.com", ".invalid", ".test")):
            continue
        if problem := public_url_problem(url):
            problems.append(f"{url}: {problem}")
            continue
        last_error = "unknown error"
        reachable = False
        for attempt in range(3):
            for method in ("HEAD", "GET"):
                try:
                    status = _request_status(url, method)
                    if status < 400:
                        reachable = True
                        break
                    last_error = f"HTTP {status}"
                    if status in {401, 403, 429}:
                        reachable = True
                        break
                    if status == 405 and method == "HEAD":
                        continue
                except OSError as err:
                    last_error = str(err)
                break
            if reachable:
                break
            if attempt < 2:
                time.sleep(2**attempt)
        if not reachable:
            problems.append(f"{url}: {last_error}")
    return problems


def release_metadata_problems(root: Path, tag: str | None = None) -> list[str]:
    """Validate shared version metadata and stricter tag release state."""
    manifest = json.loads((root / COMPONENT / "manifest.json").read_text())
    project = tomllib.loads((root / "pyproject.toml").read_text())
    manifest_version = manifest.get("version")
    project_version = project.get("project", {}).get("version")
    problems: list[str] = []
    semver = re.compile(
        r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
        r"(?:-(?:[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    )
    if manifest_version != project_version:
        problems.append(
            f"manifest version {manifest_version!r} does not match "
            f"pyproject version {project_version!r}"
        )
    if not isinstance(manifest_version, str) or not semver.fullmatch(
        manifest_version
    ):
        problems.append(f"manifest version {manifest_version!r} is not supported SemVer")
        return problems

    changelog = re.sub(
        r"<!--.*?-->",
        "",
        _without_code_fences((root / "CHANGELOG.md").read_text()),
        flags=re.DOTALL,
    )
    if isinstance(manifest_version, str) and "-" in manifest_version:
        for identifier in manifest_version.split("-", 1)[1].split("."):
            if identifier.isdigit() and len(identifier) > 1 and identifier.startswith("0"):
                problems.append(
                    f"manifest version {manifest_version!r} has a leading-zero "
                    "prerelease identifier"
                )
                break
    if not re.search(
        rf"^## {re.escape(manifest_version)}$", changelog, re.MULTILINE
    ):
        problems.append(f"CHANGELOG.md has no exact {manifest_version} heading")
    if len(re.findall(r"^## Unreleased$", changelog, re.MULTILINE)) != 1:
        problems.append("CHANGELOG.md must contain exactly one Unreleased heading")
    if len(
        re.findall(rf"^## {re.escape(manifest_version)}$", changelog, re.MULTILINE)
    ) != 1:
        problems.append(f"CHANGELOG.md must contain exactly one {manifest_version} heading")
    if tag is None:
        return problems
    if tag != f"v{manifest_version}":
        problems.append(f"tag {tag!r} does not match v{manifest_version}")
    unreleased = re.search(
        r"^## Unreleased\s*$\n(?P<body>.*?)(?=^## |\Z)",
        changelog,
        re.MULTILINE | re.DOTALL,
    )
    if unreleased is None:
        problems.append("CHANGELOG.md must retain an Unreleased heading")
    elif unreleased.group("body").strip():
        problems.append("CHANGELOG.md Unreleased section must be empty before tagging")
    headings = re.findall(r"^## (.+)$", changelog, re.MULTILINE)
    if len(headings) < 2 or headings[:2] != ["Unreleased", manifest_version]:
        problems.append("candidate version must be the first entry after Unreleased")
    return problems


def screenshot_problems(root: Path) -> list[str]:
    """Verify documented panel screenshot hashes and required viewport sizes."""
    image_dir = root / "docs" / "images"
    notes = (image_dir / "README.md").read_text(encoding="utf-8")
    documented = {
        filename: digest
        for digest, filename in re.findall(
            r"`([0-9a-f]{64})`\s*\n\s*\(`([^`]+\.png)`\)", notes
        )
    }
    problems: list[str] = []
    actual_names = {path.name for path in image_dir.glob("*.png")}
    if actual_names != set(DOCUMENTED_SCREENSHOTS):
        for filename in sorted(actual_names - set(DOCUMENTED_SCREENSHOTS)):
            problems.append(f"undocumented screenshot {filename}")
        for filename in sorted(set(DOCUMENTED_SCREENSHOTS) - actual_names):
            problems.append(f"missing documentation screenshot {filename}")
    for filename, dimensions in DOCUMENTED_SCREENSHOTS.items():
        path = image_dir / filename
        if not path.is_file():
            problems.append(f"missing documentation screenshot {filename}")
            continue
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if documented.get(filename) != digest:
            problems.append(f"{filename}: SHA-256 does not match docs/images/README.md")
        if data[:8] != b"\x89PNG\r\n\x1a\n" or len(data) < 33:
            problems.append(f"{filename}: not a valid PNG")
            continue
        offset = 8
        chunks: list[bytes] = []
        while offset + 12 <= len(data):
            length = struct.unpack(">I", data[offset : offset + 4])[0]
            end = offset + 12 + length
            if end > len(data):
                problems.append(f"{filename}: truncated PNG chunk")
                break
            chunk_type = data[offset + 4 : offset + 8]
            chunk_data = data[offset + 8 : offset + 8 + length]
            expected_crc = struct.unpack(">I", data[offset + 8 + length : end])[0]
            actual_crc = zlib.crc32(chunk_type + chunk_data) & 0xFFFFFFFF
            if actual_crc != expected_crc:
                problems.append(f"{filename}: invalid PNG chunk checksum")
                break
            chunks.append(chunk_type)
            offset = end
            if chunk_type == b"IEND":
                break
        if not chunks or chunks[0] != b"IHDR" or chunks[-1:] != [b"IEND"]:
            problems.append(f"{filename}: malformed PNG chunk structure")
        if offset != len(data):
            problems.append(f"{filename}: trailing PNG data")
        private_chunks = PNG_PRIVATE_CHUNKS.intersection(chunks)
        if private_chunks:
            names = ", ".join(sorted(chunk.decode("ascii") for chunk in private_chunks))
            problems.append(f"{filename}: embedded metadata chunks ({names})")
        unknown_chunks = set(chunks) - PNG_ALLOWED_CHUNKS
        if unknown_chunks:
            names = ", ".join(sorted(chunk.decode("ascii") for chunk in unknown_chunks))
            problems.append(f"{filename}: unapproved PNG chunks ({names})")
        actual = struct.unpack(">II", data[16:24])
        if actual != dimensions:
            problems.append(
                f"{filename}: expected {dimensions[0]}x{dimensions[1]}, "
                f"found {actual[0]}x{actual[1]}"
            )
    return problems


def archive_files(root: Path) -> list[tuple[PurePosixPath, Path]]:
    """Return the explicitly allowlisted tracked integration files."""
    manifest_lines = (root / "release-archive-files.txt").read_text().splitlines()
    if not manifest_lines or manifest_lines != sorted(set(manifest_lines)):
        raise ValueError("release archive manifest must be nonempty, unique, and sorted")
    allowed = {PurePosixPath(line) for line in manifest_lines}
    tracked: dict[PurePosixPath, tuple[str, Path]] = {}
    prefix = COMPONENT.as_posix() + "/"
    for mode, relative in tracked_files(root):
        value = relative.as_posix()
        if not value.startswith(prefix):
            continue
        archive_path = PurePosixPath(value.removeprefix(prefix))
        tracked[archive_path] = (mode, root / relative)
    unexpected = set(tracked) - allowed
    missing = allowed - set(tracked)
    if unexpected:
        raise ValueError(
            "component files are absent from release-archive-files.txt: "
            + ", ".join(sorted(path.as_posix() for path in unexpected))
        )
    if missing:
        raise ValueError(
            "release archive manifest lists missing files: "
            + ", ".join(sorted(path.as_posix() for path in missing))
        )
    required_missing = REQUIRED_ARCHIVE_FILES - {path.as_posix() for path in allowed}
    if required_missing:
        raise ValueError(
            f"release archive is missing required files: {', '.join(sorted(required_missing))}"
        )
    files: list[tuple[PurePosixPath, Path]] = []
    for archive_path in sorted(allowed, key=PurePosixPath.as_posix):
        mode, source = tracked[archive_path]
        relative = source.relative_to(root)
        if (
            mode not in {"100644", "100755"}
            or _has_symlink_component(root, relative)
            or not source.is_file()
        ):
            raise ValueError(f"unsafe release archive file: {source.relative_to(root)}")
        files.append((archive_path, source))
    return files


def build_archive(root: Path, output: Path) -> str:
    """Build a reproducible HACS ZIP and SHA256SUMS file."""
    files = archive_files(root)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for archive_path, source in files:
            info = zipfile.ZipInfo(
                archive_path.as_posix(), date_time=(1980, 1, 1, 0, 0, 0)
            )
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, source.read_bytes())
    with zipfile.ZipFile(output) as archive:
        if bad_file := archive.testzip():
            raise ValueError(f"release archive has a corrupt member: {bad_file}")
        if archive.namelist() != [path.as_posix() for path, _ in files]:
            raise ValueError("release archive contents do not match the allowlist")
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    (output.parent / "SHA256SUMS").write_text(f"{digest}  {output.name}\n")
    return digest


def _report(problems: Iterable[str]) -> int:
    findings = list(problems)
    if findings:
        for problem in findings:
            print(f"ERROR: {problem}", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=(
            "hygiene",
            "links",
            "external-links",
            "metadata",
            "screenshots",
            "build",
        ),
    )
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--tag")
    parser.add_argument("--output", type=Path, default=Path("meshmonitor.zip"))
    args = parser.parse_args()
    root = args.root.resolve()
    if args.command == "hygiene":
        return _report(hygiene_problems(root))
    if args.command == "links":
        return _report(relative_link_problems(root))
    if args.command == "external-links":
        return _report(external_link_problems(root))
    if args.command == "metadata":
        return _report(release_metadata_problems(root, args.tag))
    if args.command == "screenshots":
        return _report(screenshot_problems(root))
    output = args.output if args.output.is_absolute() else root / args.output
    digest = build_archive(root, output)
    print(f"Built {output.name}: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
