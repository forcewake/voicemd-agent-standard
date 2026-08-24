#!/usr/bin/env python3
"""Verify a VoiceMD release ZIP and its embedded package artifacts."""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import threading
import unicodedata
import urllib.parse
import zipfile
from collections.abc import Mapping
from datetime import date, datetime
from email.parser import BytesParser
from pathlib import Path, PurePosixPath
from typing import Any

ARCHIVE_ROOT = "voicemd-agent-standard"
ZIP_EOCD_SIGNATURE = b"PK\x05\x06"
ZIP_EOCD_SIZE = 22
ZIP_MAX_COMMENT_SIZE = 65_535
ZIP_LOCAL_HEADER_SIGNATURE = b"PK\x03\x04"
ZIP_LOCAL_HEADER_SIZE = 30
MAX_MEMBER_SIZE = 64 * 1024 * 1024
MAX_TOTAL_SIZE = 256 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 20_000
MAX_SUBPROCESS_OUTPUT = 1024 * 1024
SUBPROCESS_TIMEOUT_SECONDS = 180
SOURCE_SNAPSHOT_DOMAIN = b"VoiceMD source snapshot v2\0"
SUPPLY_CHAIN_FILES = {"SBOM.spdx.json", "PROVENANCE.intoto.jsonl"}
FIXED_RELEASE_FILES = {
    "BUILD_INFO.json",
    "README.md",
    "SHA256SUMS",
    "VERIFICATION.md",
}
GENERATED_SDIST_SETUP_CFG = b"[egg_info]\ntag_build = \ntag_date = 0\n\n"
REQUIRED = {
    ".github/workflows/ci.yml",
    ".github/workflows/pages.yml",
    ".github/workflows/publish.yml",
    "README.md",
    "SPECIFICATION.md",
    "VOICE.md",
    ".voicemd-root",
    "schema/voice.schema.json",
    "conformance/vectors.json",
    "constraints/build.txt",
    "manifest.json",
    "pyproject.toml",
    "MANIFEST.in",
    ".dockerignore",
    "src/voicemd/cli.py",
    "src/voicemd/azure_voice/cli.py",
    "src/voicemd/resources/azure_voice/scenarios.json",
    "src/voicemd/resources/skill/SKILL.md",
    "examples/azure-voice/README.md",
    "examples/azure-voice/evidence.schema.json",
    "examples/azure-voice/contracts/incident_commander/VOICE.md",
    ".agents/skills/voice-contract/SKILL.md",
    "integrations/http/openapi.yaml",
    "integrations/docker/Dockerfile",
    "integrations/mcp/server.py",
    "integrations/nemotron-voicechat/session_update.py",
    "integrations/typescript/generated/conformance-verifier.js",
    "scripts/build_release.py",
    "scripts/verify_pages.py",
    "scripts/verify_release.py",
    "site/assets/app.js",
    "site/assets/site.css",
    "site/audio/calm-support.wav",
    "site/audio/executive-brief.wav",
    "site/audio/incident-commander.wav",
    "site/azure-proof.html",
    "site/index.html",
    "site/proof/azure-2026-08-24/SHA256SUMS",
    "site/proof/azure-2026-08-24/proof-index.json",
    "release/BUILD_INFO.json",
    "release/README.md",
    "release/SBOM.spdx.json",
    "release/SHA256SUMS",
    "release/PROVENANCE.intoto.jsonl",
    "release/VERIFICATION.md",
}
REQUIRED_BINARY_FILES = {
    "site/audio/calm-support.wav",
    "site/audio/executive-brief.wav",
    "site/audio/incident-commander.wav",
}
FORBIDDEN_PARTS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".nox",
    "build",
    "dist",
    "htmlcov",
    "node_modules",
    "bin",
    "obj",
}
FORBIDDEN_NAMES = {".coverage", ".DS_Store", ".env"}
FORBIDDEN_SUFFIXES = {".pyc", ".pyo"}
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
REVISION_PATTERN = re.compile(r"[0-9a-f]{40}")
RUNTIME_ENV_ALLOWLIST = frozenset(
    {
        "ALL_PROXY",
        "COMSPEC",
        "CURL_CA_BUNDLE",
        "HTTPS_PROXY",
        "HTTP_PROXY",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "NO_PROXY",
        "PATHEXT",
        "PIP_CERT",
        "REQUESTS_CA_BUNDLE",
        "SSL_CERT_DIR",
        "SSL_CERT_FILE",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "TMPDIR",
        "WINDIR",
    }
)
PROXY_VARIABLES = frozenset({"ALL_PROXY", "HTTP_PROXY", "HTTPS_PROXY"})
WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{number}" for number in range(1, 10)}
    | {f"LPT{number}" for number in range(1, 10)}
)
SDIST_ROOT_FILES = {
    ".aider.voice.yml",
    ".dockerignore",
    ".gitignore",
    ".voicemd-root",
    "AGENTS.md",
    "CHANGELOG.md",
    "CITATION.cff",
    "CLAUDE.md",
    "CODE_OF_CONDUCT.md",
    "CONTRIBUTING.md",
    "GEMINI.md",
    "GOVERNANCE.md",
    "LICENSE",
    "MANIFEST.in",
    "Makefile",
    "NOTICE",
    "README.md",
    "ROADMAP.md",
    "SECURITY.md",
    "SPECIFICATION.md",
    "VOICE.md",
    "manifest.json",
    "pyproject.toml",
}
SDIST_DIRECTORIES = (
    ".agents",
    ".claude",
    ".cline",
    ".clinerules",
    ".cursor",
    ".github",
    ".voicemd",
    ".windsurf",
    "adapters",
    "conformance",
    "constraints",
    "docs",
    "evals",
    "examples",
    "integrations",
    "lite",
    "rfcs",
    "schema",
    "scripts",
    "src/voicemd",
    "templates",
    "tests",
)
GENERATED_SOURCE_PREFIXES = (PurePosixPath("examples/azure-voice/artifacts"),)


class ReleaseVerificationError(RuntimeError):
    """Raised when release evidence is absent, stale, unsafe, or inconsistent."""


def _forbidden_name(name: str) -> bool:
    folded = name.casefold()
    return name in FORBIDDEN_NAMES or folded == ".env" or folded.startswith(".env.")


def _forbidden_relative(relative: PurePosixPath) -> bool:
    return any(
        part in FORBIDDEN_PARTS or part.endswith(".egg-info")
        for part in relative.parts
    ) or any(_forbidden_name(part) for part in relative.parts) or (
        relative.suffix in FORBIDDEN_SUFFIXES
    )


def _generated_source(relative: PurePosixPath) -> bool:
    return any(
        relative == prefix or relative.is_relative_to(prefix)
        for prefix in GENERATED_SOURCE_PREFIXES
    )


def _portable_member_key(name: str, *, label: str) -> tuple[str, str]:
    stripped = name.rstrip("/")
    parts = stripped.split("/")
    portable_parts: list[str] = []
    for part in parts:
        normalized = unicodedata.normalize("NFC", part)
        windows_normalized = normalized.rstrip(" .")
        if not windows_normalized:
            raise ReleaseVerificationError(f"{label} has an empty portable path component: {name}")
        if windows_normalized != normalized or ":" in normalized or any(
            ord(character) < 32 for character in normalized
        ):
            raise ReleaseVerificationError(f"{label} is not portable across filesystems: {name}")
        stem = windows_normalized.split(".", maxsplit=1)[0].upper()
        if stem in WINDOWS_RESERVED_NAMES:
            raise ReleaseVerificationError(f"{label} uses a Windows-reserved name: {name}")
        portable_parts.append(windows_normalized.casefold())
    return unicodedata.normalize("NFC", stripped), "/".join(portable_parts)


def _validate_member_collisions(names: list[str], *, label: str) -> None:
    if len(names) > MAX_ARCHIVE_MEMBERS:
        raise ReleaseVerificationError(
            f"{label} exceeds the {MAX_ARCHIVE_MEMBERS} member limit"
        )
    exact: set[str] = set()
    nfc: dict[str, str] = {}
    portable: dict[str, str] = {}
    for name in names:
        stripped = name.rstrip("/")
        if stripped in exact:
            raise ReleaseVerificationError(f"duplicate {label} member: {name}")
        exact.add(stripped)
        nfc_key, portable_key = _portable_member_key(name, label=label)
        for key, index, kind in (
            (nfc_key, nfc, "Unicode-normalized"),
            (portable_key, portable, "case-insensitive portable"),
        ):
            previous = index.get(key)
            if previous is not None and previous != name:
                raise ReleaseVerificationError(
                    f"{kind} {label} member collision: {previous!r} and {name!r}"
                )
            index[key] = name


def source_snapshot_sha256(root: Path) -> str:
    """Hash non-release paths, canonical executable modes, and bytes."""

    entries: list[tuple[str, Path]] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        relative = PurePosixPath(path.relative_to(root).as_posix())
        if not relative.parts or relative.parts[0] in {".git", "release"}:
            continue
        if _forbidden_relative(relative) or _generated_source(relative):
            continue
        entries.append((relative.as_posix(), path))
    digest = hashlib.sha256(SOURCE_SNAPSHOT_DOMAIN)
    for name, path in sorted(entries, key=lambda item: item[0].encode("utf-8")):
        raw_name = name.encode("utf-8")
        content = path.read_bytes()
        permissions = 0o755 if path.stat().st_mode & 0o111 else 0o644
        digest.update(len(raw_name).to_bytes(8, "big"))
        digest.update(raw_name)
        digest.update(permissions.to_bytes(2, "big"))
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_nonempty_file(path: Path) -> None:
    try:
        metadata = path.lstat()
    except FileNotFoundError as exc:
        raise ReleaseVerificationError(f"required file missing: {path}") from exc
    except OSError as exc:
        raise ReleaseVerificationError(f"could not inspect required file: {path}") from exc
    if not stat.S_ISREG(metadata.st_mode):
        raise ReleaseVerificationError(f"required path is not a regular file: {path}")
    if metadata.st_size <= 0:
        raise ReleaseVerificationError(f"required file is empty: {path}")


def _decode_utf8(content: bytes, *, label: str) -> str:
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ReleaseVerificationError(f"{label} must be valid UTF-8") from exc


def _read_nonempty(path: Path) -> str:
    _require_nonempty_file(path)
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise ReleaseVerificationError(f"could not read required file: {path}") from exc
    return _decode_utf8(content, label=f"required text file {path}")


def _verify_release_inventory(directory: Path, expected: set[str]) -> None:
    try:
        entries = list(directory.iterdir())
    except OSError as exc:
        raise ReleaseVerificationError(
            f"could not inspect release inventory: {directory}"
        ) from exc

    actual: set[str] = set()
    non_files: set[str] = set()
    for entry in entries:
        try:
            metadata = entry.lstat()
        except OSError as exc:
            raise ReleaseVerificationError(
                f"could not inspect release inventory member: {entry}"
            ) from exc
        if stat.S_ISREG(metadata.st_mode):
            actual.add(entry.name)
        else:
            non_files.add(entry.name)

    missing = sorted(expected - actual)
    unexpected = sorted((actual - expected) | non_files)
    if missing or unexpected:
        raise ReleaseVerificationError(
            "release inventory mismatch; "
            f"missing={missing}, unexpected={unexpected}"
        )


def _archive_stream_size(path: Path, archive: zipfile.ZipFile) -> int:
    stream = archive.fp
    if stream is None:
        raise ReleaseVerificationError(f"release ZIP is closed: {path}")
    try:
        position = stream.tell()
        stream.seek(0, os.SEEK_END)
        size = stream.tell()
        stream.seek(position)
    except OSError as exc:
        raise ReleaseVerificationError(f"could not inspect release ZIP: {path}") from exc
    return size


def _read_archive_range(
    path: Path,
    archive: zipfile.ZipFile,
    *,
    offset: int,
    size: int,
) -> bytes:
    stream = archive.fp
    if stream is None:
        raise ReleaseVerificationError(f"release ZIP is closed: {path}")
    try:
        position = stream.tell()
        stream.seek(offset)
        content = stream.read(size)
        stream.seek(position)
    except OSError as exc:
        raise ReleaseVerificationError(f"could not inspect release ZIP: {path}") from exc
    return content


def _strict_json(text: str, *, label: str) -> object:
    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite number {value}")

    try:
        return json.loads(text, parse_constant=reject_constant)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ReleaseVerificationError(f"invalid strict JSON in {label}: {exc}") from exc


def _canonical_json(data: object) -> bytes:
    return (
        json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _project_field(pyproject: str, field: str) -> str:
    section = re.search(r"(?ms)^\[project\]\s*(.*?)(?=^\[|\Z)", pyproject)
    if section is None:
        raise ReleaseVerificationError("pyproject.toml is missing [project]")
    match = re.search(rf'(?m)^{re.escape(field)}\s*=\s*"([^"]+)"\s*$', section.group(1))
    if match is None:
        raise ReleaseVerificationError(f"pyproject.toml is missing project.{field}")
    return match.group(1)


def _verify_source_metadata(root: Path, build_info: dict[str, Any]) -> None:
    manifest = _strict_json(_read_nonempty(root / "manifest.json"), label="manifest.json")
    if not isinstance(manifest, dict):
        raise ReleaseVerificationError("manifest.json must contain an object")
    implementation = manifest.get("reference_implementation")
    if not isinstance(implementation, dict):
        raise ReleaseVerificationError("manifest.json requires reference_implementation")
    expected_pairs = {
        "project": (manifest.get("project"), build_info["project"]),
        "specification version": (
            manifest.get("specification_version"),
            build_info["specification_version"],
        ),
        "package name": (implementation.get("package"), build_info["package_name"]),
        "package version": (implementation.get("version"), build_info["package_version"]),
    }
    for label, (actual, expected) in expected_pairs.items():
        if actual != expected:
            raise ReleaseVerificationError(
                f"{label} mismatch between manifest.json and BUILD_INFO.json"
            )

    pyproject = _read_nonempty(root / "pyproject.toml")
    if _project_field(pyproject, "name") != build_info["package_name"]:
        raise ReleaseVerificationError("package name mismatch in pyproject.toml")
    if _project_field(pyproject, "version") != build_info["package_version"]:
        raise ReleaseVerificationError("package version mismatch in pyproject.toml")

    specification = _read_nonempty(root / "SPECIFICATION.md")
    version_match = re.search(r"(?m)^Version: `([^`]+)`", specification)
    if version_match is None or version_match.group(1) != build_info["specification_version"]:
        raise ReleaseVerificationError("specification version mismatch in SPECIFICATION.md")


def _safe_artifact_name(name: object) -> str:
    if not isinstance(name, str) or not name or name != Path(name).name:
        raise ReleaseVerificationError(f"unsafe artifact name in BUILD_INFO.json: {name!r}")
    if "/" in name or "\\" in name or name in {".", ".."}:
        raise ReleaseVerificationError(f"unsafe artifact name in BUILD_INFO.json: {name!r}")
    return name


def load_build_info(root: Path) -> dict[str, Any]:
    path = root / "release/BUILD_INFO.json"
    data = _strict_json(_read_nonempty(path), label=str(path))
    if not isinstance(data, dict):
        raise ReleaseVerificationError("BUILD_INFO.json must contain a JSON object")

    for field in ("project", "specification_version", "built_at"):
        value = data.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ReleaseVerificationError(f"BUILD_INFO.json requires {field}")
    try:
        date.fromisoformat(data["built_at"])
    except ValueError as exc:
        raise ReleaseVerificationError("BUILD_INFO.json built_at must be an ISO date") from exc
    tests_passed = data.get("tests_passed")
    if not isinstance(tests_passed, int) or isinstance(tests_passed, bool) or tests_passed <= 0:
        raise ReleaseVerificationError("BUILD_INFO.json requires a positive tests_passed count")

    status = data.get("artifact_status")
    if status != "current":
        raise ReleaseVerificationError(
            f"release artifacts are not current (artifact_status={status!r})"
        )
    revision = data.get("source_revision")
    if not isinstance(revision, str) or REVISION_PATTERN.fullmatch(revision) is None:
        raise ReleaseVerificationError("BUILD_INFO.json requires a full Git source_revision")
    release_revision = data.get("release_revision")
    if release_revision is not None and (
        not isinstance(release_revision, str)
        or REVISION_PATTERN.fullmatch(release_revision) is None
    ):
        raise ReleaseVerificationError(
            "BUILD_INFO.json release_revision must be null or a full Git revision"
        )
    source_digest = data.get("source_sha256")
    if not isinstance(source_digest, str) or SHA256_PATTERN.fullmatch(source_digest) is None:
        raise ReleaseVerificationError("BUILD_INFO.json requires a source_sha256")
    package_name = data.get("package_name")
    package_version = data.get("package_version")
    if not isinstance(package_name, str) or not package_name.strip():
        raise ReleaseVerificationError("BUILD_INFO.json requires package_name")
    if not isinstance(package_version, str) or not package_version.strip():
        raise ReleaseVerificationError("BUILD_INFO.json requires package_version")
    verification = data.get("verification")
    if not isinstance(verification, list) or not verification or not all(
        isinstance(item, str) and item.strip() for item in verification
    ):
        raise ReleaseVerificationError("BUILD_INFO.json requires non-empty verification records")

    artifacts = data.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts:
        raise ReleaseVerificationError("BUILD_INFO.json requires named artifacts")
    names = [_safe_artifact_name(name) for name in artifacts]
    wheels = [name for name in names if name.endswith(".whl")]
    sdists = [name for name in names if name.endswith(".tar.gz")]
    if len(wheels) != 1 or len(sdists) != 1:
        raise ReleaseVerificationError(
            "BUILD_INFO.json must name exactly one wheel and one .tar.gz source distribution"
        )
    for name, metadata in artifacts.items():
        if not isinstance(metadata, dict):
            raise ReleaseVerificationError(f"artifact metadata must be an object: {name}")
        digest = metadata.get("sha256")
        if not isinstance(digest, str) or SHA256_PATTERN.fullmatch(digest) is None:
            raise ReleaseVerificationError(f"artifact requires a lowercase SHA-256: {name}")
    release_metadata = data.get("release_metadata")
    if not isinstance(release_metadata, dict) or set(release_metadata) != SUPPLY_CHAIN_FILES:
        raise ReleaseVerificationError(
            "BUILD_INFO.json release_metadata must name the SPDX SBOM and provenance statement"
        )
    if set(release_metadata) & set(artifacts):
        raise ReleaseVerificationError("release_metadata and artifacts must not overlap")
    for name, metadata in release_metadata.items():
        _safe_artifact_name(name)
        if not isinstance(metadata, dict):
            raise ReleaseVerificationError(f"release metadata must be an object: {name}")
        digest = metadata.get("sha256")
        if not isinstance(digest, str) or SHA256_PATTERN.fullmatch(digest) is None:
            raise ReleaseVerificationError(
                f"release metadata requires a lowercase SHA-256: {name}"
            )
    _verify_source_metadata(root, data)
    actual_source_digest = source_snapshot_sha256(root)
    if source_digest != actual_source_digest:
        raise ReleaseVerificationError(
            "source_sha256 does not match the embedded non-release source snapshot"
        )
    return data


def _parse_checksums(text: str) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        fields = line.split(maxsplit=1)
        if len(fields) != 2:
            raise ReleaseVerificationError(f"invalid SHA256SUMS line {number}")
        expected, name = fields
        name = name.lstrip("*")
        _safe_artifact_name(name)
        if SHA256_PATTERN.fullmatch(expected) is None:
            raise ReleaseVerificationError(f"invalid SHA-256 on line {number}")
        if name in checksums:
            raise ReleaseVerificationError(f"duplicate SHA256SUMS entry: {name}")
        checksums[name] = expected
    if not checksums:
        raise ReleaseVerificationError("SHA256SUMS contains no artifact checksums")
    return checksums


def _normalized_distribution_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def _is_release_source(path: Path, root: Path) -> bool:
    if not path.is_file():
        return False
    relative = PurePosixPath(path.relative_to(root).as_posix())
    return not (_forbidden_relative(relative) or _generated_source(relative))


def _validate_distribution_metadata(
    raw_metadata: bytes,
    *,
    package_name: str,
    package_version: str,
    artifact_name: str,
) -> None:
    metadata = BytesParser().parsebytes(raw_metadata)
    actual_name = metadata.get("Name")
    actual_version = metadata.get("Version")
    normalized_actual = _normalized_distribution_name(actual_name) if actual_name else None
    normalized_expected = _normalized_distribution_name(package_name)
    if normalized_actual != normalized_expected:
        raise ReleaseVerificationError(
            f"package name mismatch in {artifact_name}: {actual_name!r} != {package_name!r}"
        )
    if actual_version != package_version:
        raise ReleaseVerificationError(
            f"package version mismatch in {artifact_name}: "
            f"{actual_version!r} != {package_version!r}"
        )


def _wheel_identity(path: Path) -> tuple[str, str]:
    try:
        with zipfile.ZipFile(path) as wheel:
            metadata_names = [
                name for name in wheel.namelist() if name.endswith(".dist-info/METADATA")
            ]
            if len(metadata_names) != 1:
                raise ReleaseVerificationError(
                    f"wheel must contain one METADATA file: {path.name}"
                )
            metadata = BytesParser().parsebytes(wheel.read(metadata_names[0]))
    except zipfile.BadZipFile as exc:
        raise ReleaseVerificationError(f"wheel is not a valid ZIP: {path.name}") from exc
    name = metadata.get("Name")
    version = metadata.get("Version")
    if not name or not version:
        raise ReleaseVerificationError(f"wheel METADATA lacks Name or Version: {path.name}")
    return name, version


def _record_digest(content: bytes) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=").decode("ascii")


def _verify_wheel_record(wheel: zipfile.ZipFile, record_name: str, file_names: set[str]) -> None:
    try:
        text = wheel.read(record_name).decode("utf-8")
    except (KeyError, UnicodeDecodeError) as exc:
        raise ReleaseVerificationError("wheel RECORD must be valid UTF-8") from exc
    rows: dict[str, tuple[str, str]] = {}
    try:
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        for row in reader:
            if len(row) != 3:
                raise ReleaseVerificationError("wheel RECORD rows must contain three fields")
            name, digest, size = row
            if name in rows:
                raise ReleaseVerificationError(f"duplicate wheel RECORD entry: {name}")
            rows[name] = (digest, size)
    except csv.Error as exc:
        raise ReleaseVerificationError(f"invalid wheel RECORD CSV: {exc}") from exc
    if set(rows) != file_names:
        raise ReleaseVerificationError("wheel RECORD inventory does not match wheel files")
    for name in sorted(file_names):
        digest, size = rows[name]
        if name == record_name:
            if digest or size:
                raise ReleaseVerificationError("wheel RECORD must leave its own hash and size empty")
            continue
        content = wheel.read(name)
        expected_digest = f"sha256={_record_digest(content)}"
        if digest != expected_digest or size != str(len(content)):
            raise ReleaseVerificationError(f"wheel RECORD hash or size mismatch: {name}")


def _expected_wheel_sources(source_root: Path) -> dict[str, Path]:
    package_root = source_root / "src/voicemd"
    return {
        source.relative_to(source_root / "src").as_posix(): source
        for source in sorted(package_root.rglob("*"))
        if _is_release_source(source, source_root)
    }


def verify_wheel(
    path: Path,
    *,
    package_name: str,
    package_version: str,
    source_root: Path | None = None,
) -> None:
    if not zipfile.is_zipfile(path):
        raise ReleaseVerificationError(f"wheel is not a valid ZIP: {path.name}")
    with zipfile.ZipFile(path) as wheel:
        infos = wheel.infolist()
        seen: set[str] = set()
        file_names: set[str] = set()
        total_size = 0
        for info in infos:
            name = info.filename
            raw_parts = name.rstrip("/").split("/")
            if (
                name in seen
                or "\\" in name
                or name.startswith("/")
                or not raw_parts
                or any(part in {"", ".", ".."} for part in raw_parts)
            ):
                raise ReleaseVerificationError(f"unsafe or duplicate wheel member: {name}")
            if _forbidden_relative(PurePosixPath(*raw_parts)):
                raise ReleaseVerificationError(f"forbidden build/cache member in wheel: {name}")
            seen.add(name)
            mode = (info.external_attr >> 16) & 0xFFFF
            if stat.S_IFMT(mode) == stat.S_IFLNK:
                raise ReleaseVerificationError(f"symbolic link in wheel: {name}")
            if info.flag_bits & 0x1:
                raise ReleaseVerificationError(f"encrypted wheel member: {name}")
            if info.file_size > MAX_MEMBER_SIZE:
                raise ReleaseVerificationError(f"oversized wheel member: {name}")
            total_size += info.file_size
            if total_size > MAX_TOTAL_SIZE:
                raise ReleaseVerificationError(f"wheel exceeds size limit: {path.name}")
            if info.is_dir():
                raise ReleaseVerificationError(f"wheel directory entries are not allowed: {name}")
            file_type = stat.S_IFMT(mode)
            if file_type and file_type != stat.S_IFREG:
                raise ReleaseVerificationError(f"unsupported wheel member type: {name}")
            file_names.add(name)
        _validate_member_collisions(
            [info.filename for info in infos],
            label="wheel",
        )
        if wheel.testzip() is not None:
            raise ReleaseVerificationError(f"wheel contains a corrupt member: {path.name}")
        metadata_names = [
            name
            for name in wheel.namelist()
            if name.endswith(".dist-info/METADATA") and not name.startswith("/")
        ]
        record_names = [name for name in wheel.namelist() if name.endswith(".dist-info/RECORD")]
        if len(metadata_names) != 1 or len(record_names) != 1:
            raise ReleaseVerificationError(
                f"wheel must contain one METADATA and one RECORD file: {path.name}"
            )
        dist_info_root = metadata_names[0].removesuffix("/METADATA")
        if record_names[0] != f"{dist_info_root}/RECORD":
            raise ReleaseVerificationError("wheel METADATA and RECORD use different dist-info roots")
        _validate_distribution_metadata(
            wheel.read(metadata_names[0]),
            package_name=package_name,
            package_version=package_version,
            artifact_name=path.name,
        )
        allowed_dist_info = {
            "METADATA",
            "RECORD",
            "WHEEL",
            "entry_points.txt",
            "top_level.txt",
            "licenses/LICENSE",
            "licenses/NOTICE",
        }
        required_dist_info = {
            f"{dist_info_root}/METADATA",
            f"{dist_info_root}/RECORD",
            f"{dist_info_root}/WHEEL",
            f"{dist_info_root}/entry_points.txt",
            f"{dist_info_root}/top_level.txt",
            f"{dist_info_root}/licenses/LICENSE",
            f"{dist_info_root}/licenses/NOTICE",
        }
        missing_dist_info = required_dist_info - file_names
        if missing_dist_info:
            raise ReleaseVerificationError(
                "wheel is missing required metadata files: "
                + ", ".join(sorted(missing_dist_info))
            )
        expected_sources: dict[str, Path] = {}
        if source_root is not None:
            expected_sources = _expected_wheel_sources(source_root)
            for wheel_name, source in expected_sources.items():
                if wheel_name not in seen:
                    raise ReleaseVerificationError(
                        f"wheel is missing current package source: {wheel_name}"
                    )
                if wheel.read(wheel_name) != source.read_bytes():
                    raise ReleaseVerificationError(
                        f"wheel package source is stale: {wheel_name}"
                    )
        unexpected = {
            name
            for name in file_names
            if name not in expected_sources
            and not (
                name.startswith(f"{dist_info_root}/")
                and name.removeprefix(f"{dist_info_root}/") in allowed_dist_info
            )
        }
        if unexpected:
            raise ReleaseVerificationError(
                "wheel contains unexpected files: " + ", ".join(sorted(unexpected))
            )
        if source_root is not None:
            expected_license_files = {
                f"{dist_info_root}/licenses/LICENSE": source_root / "LICENSE",
                f"{dist_info_root}/licenses/NOTICE": source_root / "NOTICE",
            }
            for wheel_name, source in expected_license_files.items():
                if wheel_name not in file_names or wheel.read(wheel_name) != source.read_bytes():
                    raise ReleaseVerificationError(f"wheel license file is missing or stale: {wheel_name}")
            entry_points = f"{dist_info_root}/entry_points.txt"
            if _decode_utf8(
                wheel.read(entry_points),
                label="wheel console entry point",
            ).strip() != (
                "[console_scripts]\n"
                "voicemd = voicemd.cli:main\n"
                "voicemd-azure = voicemd.azure_voice.cli:main"
            ):
                raise ReleaseVerificationError("wheel console entry point is unexpected")
            top_level = f"{dist_info_root}/top_level.txt"
            if _decode_utf8(
                wheel.read(top_level),
                label="wheel top-level package declaration",
            ).strip() != "voicemd":
                raise ReleaseVerificationError("wheel top-level package declaration is unexpected")
        _verify_wheel_record(wheel, record_names[0], file_names)


def _safe_tar_member(member: tarfile.TarInfo) -> PurePosixPath:
    if "\\" in member.name or member.name.startswith("/"):
        raise ReleaseVerificationError(f"unsafe sdist member: {member.name}")
    raw_parts = member.name.rstrip("/").split("/")
    if not raw_parts or any(part in {"", ".", ".."} for part in raw_parts):
        raise ReleaseVerificationError(f"unsafe sdist member: {member.name}")
    if member.issym() or member.islnk() or not (member.isfile() or member.isdir()):
        raise ReleaseVerificationError(f"unsupported sdist member type: {member.name}")
    if member.size > MAX_MEMBER_SIZE:
        raise ReleaseVerificationError(f"oversized sdist member: {member.name}")
    path = PurePosixPath(*raw_parts)
    relative = PurePosixPath(*path.parts[1:]) if len(path.parts) > 1 else path
    expected_egg_info = (
        len(relative.parts) >= 2
        and relative.parts[0] == "src"
        and relative.parts[1] == "voicemd.egg-info"
    )
    egg_info_inner = PurePosixPath(*relative.parts[2:]) if len(relative.parts) > 2 else None
    if expected_egg_info and egg_info_inner is not None and _forbidden_relative(egg_info_inner):
        raise ReleaseVerificationError(f"forbidden build/cache member in sdist: {member.name}")
    if not expected_egg_info and _forbidden_relative(relative):
        raise ReleaseVerificationError(f"forbidden build/cache member in sdist: {member.name}")
    return path


def _sdist_sync_sources(root: Path) -> list[Path]:
    sources = [root / relative for relative in SDIST_ROOT_FILES if (root / relative).is_file()]
    for relative in SDIST_DIRECTORIES:
        directory = root / relative
        if directory.is_dir():
            sources.extend(path for path in directory.rglob("*") if _is_release_source(path, root))
    return sorted(set(sources))


def verify_sdist(
    path: Path,
    *,
    package_name: str,
    package_version: str,
    source_root: Path | None = None,
) -> None:
    try:
        # Keep error translation outside the context manager so invalid gzip/tar
        # input is reported as a release-verification failure.
        archive = tarfile.open(path, mode="r:gz")  # noqa: SIM115
    except (tarfile.TarError, OSError) as exc:
        raise ReleaseVerificationError(f"invalid source distribution: {path.name}") from exc
    with archive:
        members = archive.getmembers()
        if not members:
            raise ReleaseVerificationError(f"empty source distribution: {path.name}")
        names_in_order = [member.name.rstrip("/") for member in members]
        if len(names_in_order) != len(set(names_in_order)):
            raise ReleaseVerificationError(f"duplicate source distribution member: {path.name}")
        if sum(member.size for member in members) > MAX_TOTAL_SIZE:
            raise ReleaseVerificationError(f"source distribution exceeds size limit: {path.name}")
        paths = [_safe_tar_member(member) for member in members]
        _validate_member_collisions(
            [member.name for member in members],
            label="source distribution",
        )
        roots = {member.parts[0] for member in paths}
        if len(roots) != 1:
            raise ReleaseVerificationError(f"sdist must contain exactly one root: {path.name}")
        root_name = next(iter(roots))
        expected_root_name = f"{package_name.replace('-', '_')}-{package_version}"
        if root_name != expected_root_name:
            raise ReleaseVerificationError(
                f"sdist root mismatch: {root_name!r} != {expected_root_name!r}"
            )
        pyproject_name = f"{root_name}/pyproject.toml"
        pkg_info_name = f"{root_name}/PKG-INFO"
        names = set(names_in_order)
        if pyproject_name not in names or pkg_info_name not in names:
            raise ReleaseVerificationError(
                f"sdist is missing pyproject.toml or PKG-INFO: {path.name}"
            )
        pkg_info = archive.extractfile(pkg_info_name)
        if pkg_info is None:
            raise ReleaseVerificationError(f"could not read PKG-INFO from {path.name}")
        _validate_distribution_metadata(
            pkg_info.read(),
            package_name=package_name,
            package_version=package_version,
            artifact_name=path.name,
        )
        if source_root is not None:
            expected_sources = {
                source.relative_to(source_root).as_posix(): source
                for source in _sdist_sync_sources(source_root)
            }
            generated_files = {
                "PKG-INFO",
                "setup.cfg",
                "src/voicemd.egg-info/PKG-INFO",
                "src/voicemd.egg-info/SOURCES.txt",
                "src/voicemd.egg-info/dependency_links.txt",
                "src/voicemd.egg-info/entry_points.txt",
                "src/voicemd.egg-info/requires.txt",
                "src/voicemd.egg-info/top_level.txt",
            }
            actual_files = {
                PurePosixPath(name).relative_to(root_name).as_posix()
                for name, member in zip(names_in_order, members, strict=True)
                if member.isfile()
            }
            expected_files = set(expected_sources) | generated_files
            unexpected = actual_files - expected_files
            missing = set(expected_sources) - actual_files
            if unexpected or missing:
                raise ReleaseVerificationError(
                    "sdist inventory mismatch; "
                    f"missing={sorted(missing)}, unexpected={sorted(unexpected)}"
                )
            generated_setup = archive.extractfile(f"{root_name}/setup.cfg")
            if (
                generated_setup is None
                or generated_setup.read() != GENERATED_SDIST_SETUP_CFG
            ):
                raise ReleaseVerificationError(
                    "sdist generated setup.cfg is missing or unexpected"
                )
            allowed_directories = {"."}
            for relative in actual_files:
                parent = PurePosixPath(relative).parent
                while parent != PurePosixPath("."):
                    allowed_directories.add(parent.as_posix())
                    parent = parent.parent
            actual_directories = {
                PurePosixPath(name).relative_to(root_name).as_posix()
                for name, member in zip(names_in_order, members, strict=True)
                if member.isdir() and name != root_name
            }
            if not actual_directories <= allowed_directories:
                raise ReleaseVerificationError(
                    "sdist contains unexpected directories: "
                    + ", ".join(sorted(actual_directories - allowed_directories))
                )
            for relative, source in expected_sources.items():
                relative = source.relative_to(source_root).as_posix()
                member_name = f"{root_name}/{relative}"
                if member_name not in names:
                    raise ReleaseVerificationError(
                        f"sdist is missing current release source: {relative}"
                    )
                extracted = archive.extractfile(member_name)
                if extracted is None or extracted.read() != source.read_bytes():
                    raise ReleaseVerificationError(f"sdist release source is stale: {relative}")


def _canonical_json_file(path: Path, *, label: str) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ReleaseVerificationError(f"could not read UTF-8 {label}: {path}") from exc
    data = _strict_json(text, label=label)
    if not isinstance(data, dict):
        raise ReleaseVerificationError(f"{label} must contain a JSON object")
    if raw != _canonical_json(data):
        raise ReleaseVerificationError(
            f"{label} must use deterministic canonical JSON with one trailing newline"
        )
    return data


def _checksum_from_spdx(entry: object, *, label: str) -> str:
    if not isinstance(entry, list) or len(entry) != 1 or not isinstance(entry[0], dict):
        raise ReleaseVerificationError(f"{label} requires exactly one checksum")
    checksum = entry[0]
    if checksum.get("algorithm") != "SHA256":
        raise ReleaseVerificationError(f"{label} checksum must use SHA256")
    value = checksum.get("checksumValue")
    if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
        raise ReleaseVerificationError(f"{label} has an invalid SHA-256")
    return value


def verify_spdx_sbom(
    path: Path,
    *,
    package_name: str,
    package_version: str,
    source_revision: str,
    source_snapshot: str,
    artifacts: dict[str, str],
) -> None:
    data = _canonical_json_file(path, label="SPDX SBOM")
    expected_header = {
        "SPDXID": "SPDXRef-DOCUMENT",
        "dataLicense": "CC0-1.0",
        "spdxVersion": "SPDX-2.3",
    }
    for field, expected in expected_header.items():
        if data.get(field) != expected:
            raise ReleaseVerificationError(f"SPDX SBOM has invalid {field}")
    namespace = data.get("documentNamespace")
    if not isinstance(namespace, str) or not namespace.startswith(
        "https://spdx.org/spdxdocs/"
    ):
        raise ReleaseVerificationError("SPDX SBOM requires a stable documentNamespace")
    creation = data.get("creationInfo")
    if not isinstance(creation, dict):
        raise ReleaseVerificationError("SPDX SBOM requires creationInfo")
    created = creation.get("created")
    if not isinstance(created, str) or not created.endswith("Z"):
        raise ReleaseVerificationError("SPDX SBOM creationInfo.created must be UTC")
    try:
        datetime.fromisoformat(created.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReleaseVerificationError("SPDX SBOM has an invalid creation timestamp") from exc
    if creation.get("creators") != ["Tool: VoiceMD scripts/build_release.py"]:
        raise ReleaseVerificationError("SPDX SBOM creator is not the release builder")

    files = data.get("files")
    if not isinstance(files, list):
        raise ReleaseVerificationError("SPDX SBOM files must be an array")
    described_artifacts: dict[str, str] = {}
    file_ids: set[str] = set()
    for item in files:
        if not isinstance(item, dict):
            raise ReleaseVerificationError("SPDX SBOM file entry must be an object")
        name = item.get("fileName")
        file_id = item.get("SPDXID")
        if not isinstance(name, str) or not name.startswith("./") or "/" in name[2:]:
            raise ReleaseVerificationError("SPDX SBOM contains an unsafe artifact name")
        if not isinstance(file_id, str) or not file_id.startswith("SPDXRef-Artifact-"):
            raise ReleaseVerificationError("SPDX SBOM contains an invalid artifact SPDXID")
        if file_id in file_ids or name[2:] in described_artifacts:
            raise ReleaseVerificationError("SPDX SBOM contains a duplicate artifact")
        file_ids.add(file_id)
        described_artifacts[name[2:]] = _checksum_from_spdx(
            item.get("checksums"), label=f"SPDX artifact {name}"
        )
    if described_artifacts != artifacts:
        raise ReleaseVerificationError("SPDX SBOM artifact inventory or checksum mismatch")

    packages = data.get("packages")
    if not isinstance(packages, list):
        raise ReleaseVerificationError("SPDX SBOM packages must be an array")
    package_ids: set[str] = set()
    matching_packages: list[dict[str, Any]] = []
    for item in packages:
        if not isinstance(item, dict):
            raise ReleaseVerificationError("SPDX SBOM package entry must be an object")
        package_id = item.get("SPDXID")
        if not isinstance(package_id, str) or not package_id.startswith("SPDXRef-"):
            raise ReleaseVerificationError("SPDX SBOM contains an invalid package SPDXID")
        if package_id in package_ids or package_id in file_ids:
            raise ReleaseVerificationError("SPDX SBOM contains a duplicate SPDXID")
        package_ids.add(package_id)
        if item.get("name") == package_name and item.get("versionInfo") == package_version:
            matching_packages.append(item)
    if len(matching_packages) != 1:
        raise ReleaseVerificationError("SPDX SBOM must describe the released package exactly once")
    package = matching_packages[0]
    source_info = package.get("sourceInfo")
    if (
        not isinstance(source_info, str)
        or source_revision not in source_info
        or source_snapshot not in source_info
    ):
        raise ReleaseVerificationError("SPDX SBOM source provenance mismatch")
    package_id = package["SPDXID"]
    if data.get("documentDescribes") != [package_id]:
        raise ReleaseVerificationError("SPDX SBOM documentDescribes mismatch")
    external_refs = package.get("externalRefs")
    expected_purl = f"pkg:pypi/{package_name}@{package_version}"
    if not isinstance(external_refs, list) or not any(
        isinstance(item, dict) and item.get("referenceLocator") == expected_purl
        for item in external_refs
    ):
        raise ReleaseVerificationError("SPDX SBOM package purl mismatch")
    relationships = data.get("relationships")
    if not isinstance(relationships, list):
        raise ReleaseVerificationError("SPDX SBOM relationships must be an array")
    contained = {
        item.get("relatedSpdxElement")
        for item in relationships
        if isinstance(item, dict)
        and item.get("spdxElementId") == package_id
        and item.get("relationshipType") == "CONTAINS"
    }
    if contained != file_ids:
        raise ReleaseVerificationError("SPDX SBOM artifact relationships are incomplete")


def verify_provenance_statement(
    path: Path,
    *,
    package_name: str,
    package_version: str,
    source_revision: str,
    release_revision: str | None,
    source_snapshot: str,
    subjects: dict[str, str],
    build_type: str,
) -> None:
    data = _canonical_json_file(path, label="in-toto provenance")
    if data.get("_type") != "https://in-toto.io/Statement/v1":
        raise ReleaseVerificationError("provenance statement has an invalid in-toto type")
    if data.get("predicateType") != "https://slsa.dev/provenance/v1":
        raise ReleaseVerificationError("provenance statement has an invalid predicate type")
    raw_subjects = data.get("subject")
    if not isinstance(raw_subjects, list):
        raise ReleaseVerificationError("provenance statement subjects must be an array")
    actual_subjects: dict[str, str] = {}
    for item in raw_subjects:
        if not isinstance(item, dict):
            raise ReleaseVerificationError("provenance subject must be an object")
        name = item.get("name")
        digest = item.get("digest")
        if (
            not isinstance(name, str)
            or name != Path(name).name
            or not isinstance(digest, dict)
            or set(digest) != {"sha256"}
            or not isinstance(digest.get("sha256"), str)
            or SHA256_PATTERN.fullmatch(digest["sha256"]) is None
            or name in actual_subjects
        ):
            raise ReleaseVerificationError("provenance statement contains an invalid subject")
        actual_subjects[name] = digest["sha256"]
    if actual_subjects != subjects:
        raise ReleaseVerificationError("provenance subjects or checksums do not match release files")

    predicate = data.get("predicate")
    build_definition = predicate.get("buildDefinition") if isinstance(predicate, dict) else None
    run_details = predicate.get("runDetails") if isinstance(predicate, dict) else None
    if not isinstance(build_definition, dict) or not isinstance(run_details, dict):
        raise ReleaseVerificationError("provenance statement requires SLSA build details")
    if build_definition.get("buildType") != build_type:
        raise ReleaseVerificationError("provenance statement build type mismatch")
    external = build_definition.get("externalParameters")
    if not isinstance(external, dict) or external != {
        "packageName": package_name,
        "packageVersion": package_version,
    }:
        raise ReleaseVerificationError("provenance package parameters mismatch")
    internal = build_definition.get("internalParameters")
    if not isinstance(internal, dict):
        raise ReleaseVerificationError("provenance statement requires internalParameters")
    if internal.get("sourceRevision") != source_revision:
        raise ReleaseVerificationError("provenance source revision mismatch")
    if internal.get("sourceSnapshotSha256") != source_snapshot:
        raise ReleaseVerificationError("provenance source snapshot mismatch")
    tool_versions = internal.get("buildToolVersions")
    if not isinstance(tool_versions, dict) or not all(
        isinstance(name, str)
        and name
        and isinstance(version, str)
        and version
        for name, version in tool_versions.items()
    ):
        raise ReleaseVerificationError("provenance build tool versions are invalid")
    actual_release_revision = internal.get("releaseRevision")
    if (
        not isinstance(actual_release_revision, str)
        or REVISION_PATTERN.fullmatch(actual_release_revision) is None
    ):
        raise ReleaseVerificationError("provenance release revision must be a full Git revision")
    if release_revision is not None and actual_release_revision != release_revision:
        raise ReleaseVerificationError("provenance release revision mismatch")
    dependencies = build_definition.get("resolvedDependencies")
    if not isinstance(dependencies, list) or not any(
        isinstance(item, dict)
        and item.get("uri") == f"urn:git:commit:{source_revision}"
        and item.get("digest") == {"sha1": source_revision}
        for item in dependencies
    ):
        raise ReleaseVerificationError("provenance source dependency mismatch")
    builder = run_details.get("builder")
    if not isinstance(builder, dict) or builder.get("id") != (
        "urn:voicemd:builder:scripts-build-release-py:v1"
    ):
        raise ReleaseVerificationError("provenance builder identity mismatch")


def verify_supply_chain_metadata(
    directory: Path,
    *,
    package_name: str,
    package_version: str,
    source_revision: str,
    release_revision: str | None,
    source_snapshot: str,
    artifacts: dict[str, str],
) -> None:
    sbom_path = directory / "SBOM.spdx.json"
    provenance_path = directory / "PROVENANCE.intoto.jsonl"
    verify_spdx_sbom(
        sbom_path,
        package_name=package_name,
        package_version=package_version,
        source_revision=source_revision,
        source_snapshot=source_snapshot,
        artifacts=artifacts,
    )
    subjects = {**artifacts, sbom_path.name: sha256(sbom_path)}
    verify_provenance_statement(
        provenance_path,
        package_name=package_name,
        package_version=package_version,
        source_revision=source_revision,
        release_revision=release_revision,
        source_snapshot=source_snapshot,
        subjects=subjects,
        build_type="urn:voicemd:build:python-distributions:v1",
    )


def verify_artifacts(root: Path) -> tuple[Path, Path]:
    build_info = load_build_info(root)
    artifact_metadata = build_info["artifacts"]
    release_metadata = build_info["release_metadata"]
    declared = set(artifact_metadata) | set(release_metadata)
    _verify_release_inventory(
        root / "release",
        FIXED_RELEASE_FILES | declared,
    )
    checksums = _parse_checksums(_read_nonempty(root / "release/SHA256SUMS"))
    if set(checksums) != declared:
        missing = sorted(declared - set(checksums))
        unexpected = sorted(set(checksums) - declared)
        raise ReleaseVerificationError(
            "SHA256SUMS does not match BUILD_INFO artifacts; "
            f"missing={missing}, unexpected={unexpected}"
        )

    for name in sorted(declared):
        target = root / "release" / name
        if not target.is_file() or target.stat().st_size <= 0:
            raise ReleaseVerificationError(f"release artifact missing or empty: {name}")
        actual = sha256(target)
        if actual != checksums[name]:
            raise ReleaseVerificationError(
                f"SHA256SUMS mismatch for {name}: {actual} != {checksums[name]}"
            )
        expected_metadata = artifact_metadata.get(name) or release_metadata.get(name)
        if not isinstance(expected_metadata, dict):
            raise ReleaseVerificationError(f"missing BUILD_INFO.json metadata for {name}")
        if actual != expected_metadata["sha256"]:
            raise ReleaseVerificationError(
                f"BUILD_INFO.json checksum mismatch for {name}: {actual}"
            )

    wheel_name = next(name for name in artifact_metadata if name.endswith(".whl"))
    sdist_name = next(name for name in artifact_metadata if name.endswith(".tar.gz"))
    wheel = root / "release" / wheel_name
    sdist = root / "release" / sdist_name
    package_name = build_info["package_name"]
    package_version = build_info["package_version"]
    verify_wheel(
        wheel,
        package_name=package_name,
        package_version=package_version,
        source_root=root,
    )
    verify_sdist(
        sdist,
        package_name=package_name,
        package_version=package_version,
        source_root=root,
    )
    verify_supply_chain_metadata(
        root / "release",
        package_name=package_name,
        package_version=package_version,
        source_revision=build_info["source_revision"],
        release_revision=build_info.get("release_revision"),
        source_snapshot=build_info["source_sha256"],
        artifacts={name: metadata["sha256"] for name, metadata in artifact_metadata.items()},
    )
    return wheel, sdist


def _validate_canonical_zip_container(path: Path, archive: zipfile.ZipFile) -> None:
    try:
        archive_size = path.stat().st_size
        tail_size = min(archive_size, ZIP_EOCD_SIZE + ZIP_MAX_COMMENT_SIZE)
        with path.open("rb") as stream:
            stream.seek(archive_size - tail_size)
            tail = stream.read(tail_size)
    except OSError as exc:
        raise ReleaseVerificationError(f"could not inspect release ZIP: {path}") from exc

    eocd_index = tail.rfind(ZIP_EOCD_SIGNATURE)
    if eocd_index < 0 or len(tail) - eocd_index < ZIP_EOCD_SIZE:
        raise ReleaseVerificationError(f"release ZIP has no valid end record: {path}")
    eocd_offset = archive_size - tail_size + eocd_index
    comment_size = int.from_bytes(tail[eocd_index + 20 : eocd_index + 22], "little")
    if comment_size or archive.comment:
        raise ReleaseVerificationError("release ZIP comments are not allowed")
    if eocd_offset + ZIP_EOCD_SIZE != archive_size:
        raise ReleaseVerificationError("release ZIP contains trailing bytes")

    disk_number = int.from_bytes(tail[eocd_index + 4 : eocd_index + 6], "little")
    central_disk = int.from_bytes(tail[eocd_index + 6 : eocd_index + 8], "little")
    disk_members = int.from_bytes(tail[eocd_index + 8 : eocd_index + 10], "little")
    total_members = int.from_bytes(tail[eocd_index + 10 : eocd_index + 12], "little")
    central_size = int.from_bytes(tail[eocd_index + 12 : eocd_index + 16], "little")
    central_offset = int.from_bytes(tail[eocd_index + 16 : eocd_index + 20], "little")
    if disk_number or central_disk or disk_members != total_members:
        raise ReleaseVerificationError("multi-disk release ZIPs are not allowed")
    if total_members == 0xFFFF or central_size == 0xFFFFFFFF or central_offset == 0xFFFFFFFF:
        raise ReleaseVerificationError("ZIP64 release containers are not allowed")

    infos = archive.infolist()
    if total_members != len(infos):
        raise ReleaseVerificationError("release ZIP member count does not match its end record")
    if archive.start_dir != central_offset or any(info.header_offset < 0 for info in infos):
        raise ReleaseVerificationError("release ZIP contains a prefix or prepended data")
    if infos and min(info.header_offset for info in infos) != 0:
        raise ReleaseVerificationError("release ZIP contains a prefix or prepended data")
    if central_offset + central_size != eocd_offset:
        raise ReleaseVerificationError("release ZIP contains unaccounted container data")
    if any(info.comment for info in infos):
        raise ReleaseVerificationError("release ZIP member comments are not allowed")
    if any(info.extra for info in infos):
        raise ReleaseVerificationError("release ZIP member extra fields are not allowed")

    ordered_infos = sorted(infos, key=lambda info: info.header_offset)
    expected_offset = 0
    try:
        with path.open("rb") as stream:
            for info in ordered_infos:
                if info.header_offset != expected_offset:
                    raise ReleaseVerificationError(
                        "release ZIP contains data between local member records"
                    )
                stream.seek(info.header_offset)
                header = stream.read(ZIP_LOCAL_HEADER_SIZE)
                if (
                    len(header) != ZIP_LOCAL_HEADER_SIZE
                    or header[:4] != ZIP_LOCAL_HEADER_SIGNATURE
                ):
                    raise ReleaseVerificationError(
                        f"invalid local ZIP header: {info.filename}"
                    )
                flags = int.from_bytes(header[6:8], "little")
                compression = int.from_bytes(header[8:10], "little")
                crc = int.from_bytes(header[14:18], "little")
                compressed_size = int.from_bytes(header[18:22], "little")
                uncompressed_size = int.from_bytes(header[22:26], "little")
                name_size = int.from_bytes(header[26:28], "little")
                extra_size = int.from_bytes(header[28:30], "little")
                if flags & 0x08:
                    raise ReleaseVerificationError(
                        f"ZIP data descriptors are not allowed: {info.filename}"
                    )
                if extra_size:
                    raise ReleaseVerificationError(
                        f"local ZIP extra fields are not allowed: {info.filename}"
                    )
                encoded_name = stream.read(name_size)
                expected_name = info.filename.encode(
                    "utf-8" if flags & 0x800 else "cp437"
                )
                if encoded_name != expected_name:
                    raise ReleaseVerificationError(
                        f"local ZIP filename mismatch: {info.filename}"
                    )
                if (
                    flags != info.flag_bits
                    or compression != info.compress_type
                    or crc != info.CRC
                    or compressed_size != info.compress_size
                    or uncompressed_size != info.file_size
                ):
                    raise ReleaseVerificationError(
                        f"local and central ZIP metadata differ: {info.filename}"
                    )
                expected_offset = (
                    info.header_offset
                    + ZIP_LOCAL_HEADER_SIZE
                    + name_size
                    + extra_size
                    + compressed_size
                )
    except ReleaseVerificationError:
        raise
    except (OSError, UnicodeError) as exc:
        raise ReleaseVerificationError(f"could not inspect local ZIP records: {path}") from exc
    if expected_offset != central_offset:
        raise ReleaseVerificationError(
            "release ZIP contains data before its central directory"
        )


def _validate_archive_members(archive: zipfile.ZipFile) -> None:
    infos = archive.infolist()
    seen: set[str] = set()
    relative_files: set[str] = set()
    total_size = 0
    for info in infos:
        name = info.filename
        if name in seen:
            raise ReleaseVerificationError(f"duplicate ZIP member: {name}")
        seen.add(name)
        if "\\" in name or name.startswith("/") or "\x00" in name:
            raise ReleaseVerificationError(f"unsafe ZIP member: {name}")
        raw_parts = name.rstrip("/").split("/")
        if not raw_parts or any(part in {"", ".", ".."} for part in raw_parts):
            raise ReleaseVerificationError(f"unsafe ZIP member: {name}")
        if raw_parts[0] != ARCHIVE_ROOT:
            raise ReleaseVerificationError(
                f"archive root must be {ARCHIVE_ROOT!r}, found {raw_parts[0]!r}"
            )
        if info.flag_bits & 0x1:
            raise ReleaseVerificationError(f"encrypted ZIP member is not allowed: {name}")

        mode = (info.external_attr >> 16) & 0xFFFF
        file_type = stat.S_IFMT(mode)
        if file_type == stat.S_IFLNK:
            raise ReleaseVerificationError(f"symbolic link in release ZIP: {name}")
        is_directory = info.is_dir()
        if is_directory != (file_type == stat.S_IFDIR):
            raise ReleaseVerificationError(
                f"ZIP member name/type mismatch: {name}"
            )
        if is_directory:
            raise ReleaseVerificationError(f"directory entries are not allowed: {name}")
        if info.create_system != 3 or file_type != stat.S_IFREG:
            raise ReleaseVerificationError(
                f"release ZIP member must be a Unix regular file: {name}"
            )
        if info.file_size > MAX_MEMBER_SIZE:
            raise ReleaseVerificationError(f"oversized ZIP member: {name}")
        total_size += info.file_size
        if total_size > MAX_TOTAL_SIZE:
            raise ReleaseVerificationError("release ZIP exceeds uncompressed size limit")

        relative_parts = raw_parts[1:]
        if not relative_parts:
            raise ReleaseVerificationError("archive root may not be a file")
        relative = PurePosixPath(*relative_parts)
        if _forbidden_relative(relative):
            raise ReleaseVerificationError(f"forbidden build/cache member: {name}")
        relative_files.add(relative.as_posix())

    _validate_member_collisions(
        [info.filename for info in infos],
        label="release ZIP",
    )

    if not seen:
        raise ReleaseVerificationError("release ZIP is empty")
    missing = sorted(REQUIRED - relative_files)
    if missing:
        raise ReleaseVerificationError("required archive members missing: " + ", ".join(missing))


def _safe_extract(archive: zipfile.ZipFile, destination: Path) -> Path:
    root = destination / ARCHIVE_ROOT
    for info in archive.infolist():
        parts = info.filename.rstrip("/").split("/")
        target = destination.joinpath(*parts)
        if info.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(info) as source, target.open("wb") as sink:
            shutil.copyfileobj(source, sink)
        archived_mode = (info.external_attr >> 16) & 0xFFFF
        # Preserve only the executable intent needed by tracked scripts. Avoid
        # restoring special or overly broad permission bits from an archive.
        target.chmod(0o755 if archived_mode & 0o111 else 0o644)
    return root


def _verify_zip_integrity(path: Path, archive: zipfile.ZipFile) -> None:
    _validate_canonical_zip_container(path, archive)
    _validate_archive_members(archive)
    try:
        corrupt = archive.testzip()
    except (OSError, EOFError, RuntimeError, NotImplementedError, zipfile.BadZipFile) as exc:
        raise ReleaseVerificationError(f"could not verify release ZIP members: {path}") from exc
    if corrupt:
        raise ReleaseVerificationError(f"corrupt ZIP member: {corrupt}")


def _bounded_process_output(content: bytes, *, truncated: bool) -> str:
    text = content.decode("utf-8", errors="replace")
    if truncated:
        text += "\n[release verifier truncated subprocess output]\n"
    return text


def _drain_process_stream(stream, captured: bytearray, state: dict[str, bool]) -> None:
    while True:
        chunk = stream.read(64 * 1024)
        if not chunk:
            return
        remaining = MAX_SUBPROCESS_OUTPUT - len(captured)
        if remaining > 0:
            captured.extend(chunk[:remaining])
        if len(chunk) > remaining:
            state["truncated"] = True


def run(command: list[str], *, cwd: Path, env: dict[str, str]) -> None:
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdout is not None and process.stderr is not None
    stdout = bytearray()
    stderr = bytearray()
    stdout_state = {"truncated": False}
    stderr_state = {"truncated": False}
    threads = [
        threading.Thread(
            target=_drain_process_stream,
            args=(process.stdout, stdout, stdout_state),
            daemon=True,
        ),
        threading.Thread(
            target=_drain_process_stream,
            args=(process.stderr, stderr, stderr_state),
            daemon=True,
        ),
    ]
    for thread in threads:
        thread.start()
    timed_out = False
    try:
        returncode = process.wait(timeout=SUBPROCESS_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()
        returncode = process.wait()
    finally:
        for thread in threads:
            thread.join(timeout=5)
        process.stdout.close()
        process.stderr.close()
    captured_stdout = _bounded_process_output(
        bytes(stdout), truncated=stdout_state["truncated"]
    )
    captured_stderr = _bounded_process_output(
        bytes(stderr), truncated=stderr_state["truncated"]
    )
    if timed_out:
        raise ReleaseVerificationError(
            f"command timed out after {SUBPROCESS_TIMEOUT_SECONDS}s: {' '.join(command)}"
        )
    if returncode:
        sys.stderr.write(captured_stdout)
        sys.stderr.write(captured_stderr)
        raise ReleaseVerificationError(
            f"command failed ({returncode}): {' '.join(command)}"
        )


def runtime_subprocess_environment(
    source: Mapping[str, str] | None = None,
    *,
    home: Path | None = None,
) -> dict[str, str]:
    """Build a minimal environment for explicitly trusted release runtime checks."""

    inherited = os.environ if source is None else source
    path = next(
        (value for key, value in inherited.items() if key.upper() == "PATH" and value),
        os.defpath,
    )
    environment = {
        key: value
        for key, value in inherited.items()
        if key.upper() in RUNTIME_ENV_ALLOWLIST and value
    }
    for key, value in environment.items():
        if key.upper() not in PROXY_VARIABLES:
            continue
        candidate = value if "://" in value else f"//{value}"
        try:
            parsed = urllib.parse.urlsplit(candidate)
        except ValueError as exc:
            raise ReleaseVerificationError(
                f"invalid proxy variable for runtime checks: {key}"
            ) from exc
        if parsed.username is not None or parsed.password is not None:
            raise ReleaseVerificationError(
                f"credential-bearing proxy variable is not allowed for runtime checks: {key}"
            )
    environment["PATH"] = path
    environment.update(
        {
            "PIP_CONFIG_FILE": os.devnull,
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            "PIP_NO_INPUT": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
        }
    )
    if home is not None:
        home = home.resolve()
        environment.update(
            {
                "HOME": str(home),
                "USERPROFILE": str(home),
                "XDG_CACHE_HOME": str(home / ".cache"),
                "XDG_CONFIG_HOME": str(home / ".config"),
                "XDG_DATA_HOME": str(home / ".local/share"),
            }
        )
    return environment


def _pip_command(python: Path, command: str, *arguments: str) -> list[str]:
    result = [
        str(python),
        "-m",
        "pip",
        "--isolated",
        "--disable-pip-version-check",
        command,
    ]
    if command == "install":
        result.extend(["--no-input", "--no-cache-dir"])
    result.extend(arguments)
    return result


def _venv_python(environment: Path) -> Path:
    directory = "Scripts" if os.name == "nt" else "bin"
    executable = "python.exe" if os.name == "nt" else "python"
    return environment / directory / executable


def _venv_script(environment: Path, name: str) -> Path:
    directory = "Scripts" if os.name == "nt" else "bin"
    suffix = ".exe" if os.name == "nt" else ""
    return environment / directory / f"{name}{suffix}"


def verify_runtime(root: Path, wheel: Path, sdist: Path, temporary: Path) -> None:
    runtime_home = temporary / "runtime-home"
    runtime_home.mkdir(mode=0o700)
    base_env = runtime_subprocess_environment(home=runtime_home)
    smoke_env = {**base_env, "VOICE_MD_ROOT": str(root)}

    wheel_environment = temporary / "wheel-env"
    run(
        [sys.executable, "-I", "-m", "venv", "--clear", str(wheel_environment)],
        cwd=root,
        env=base_env,
    )
    wheel_python = _venv_python(wheel_environment)
    run(
        _pip_command(wheel_python, "install", f"{wheel}[azure-voice]"),
        cwd=root,
        env=base_env,
    )
    run(_pip_command(wheel_python, "check"), cwd=root, env=base_env)
    run(
        [str(wheel_python), "-m", "voicemd", "validate", "--path", "VOICE.md", "--strict"],
        cwd=root,
        env=smoke_env,
    )
    output = root / ".voice/verify-nemotron.txt"
    run(
        [
            str(wheel_python),
            "-m",
            "voicemd",
            "compile",
            "--path",
            "VOICE.md",
            "--profile",
            "nemotron_voicechat",
            "--format",
            "nemotron-ascii",
            "--compact",
            "--max-chars",
            "5000",
            "--output",
            str(output),
        ],
        cwd=root,
        env=smoke_env,
    )
    prompt = _read_nonempty(output)
    if not prompt.isascii() or len(prompt) > 5000:
        raise ReleaseVerificationError("Nemotron smoke output is not valid ASCII within budget")

    azure_smoke_env = {
        **base_env,
        "AZURE_OPENAI_ENDPOINT": "https://release-smoke.openai.azure.invalid",
        "AZURE_OPENAI_API_KEY": "release-smoke-placeholder",
    }
    run(
        [str(_venv_script(wheel_environment, "voicemd-azure")), "doctor"],
        cwd=root,
        env=azure_smoke_env,
    )

    node = shutil.which("node", path=base_env.get("PATH"))
    if node is None:
        raise ReleaseVerificationError(
            "Node.js is required for the independent TypeScript conformance verifier"
        )
    run(
        [
            node,
            "integrations/typescript/generated/conformance-verifier.js",
            "conformance/vectors.json",
        ],
        cwd=root,
        env=base_env,
    )

    sdist_environment = temporary / "sdist-env"
    run(
        [sys.executable, "-I", "-m", "venv", "--clear", str(sdist_environment)],
        cwd=root,
        env=base_env,
    )
    sdist_python = _venv_python(sdist_environment)
    run(
        _pip_command(sdist_python, "install", str(sdist), "pytest>=8,<9"),
        cwd=root,
        env=base_env,
    )
    run(_pip_command(sdist_python, "check"), cwd=root, env=base_env)
    run([str(sdist_python), "-m", "pytest", "-q"], cwd=root, env=base_env)


def verify_distribution_bundle(
    distributions: Path,
    metadata: Path,
    source_root: Path,
    *,
    source_revision: str,
    release_revision: str | None = None,
) -> None:
    """Verify freshly built distributions and deterministic supply-chain metadata."""

    distributions = distributions.expanduser().resolve()
    metadata = metadata.expanduser().resolve()
    source_root = source_root.expanduser().resolve()
    if REVISION_PATTERN.fullmatch(source_revision) is None:
        raise ReleaseVerificationError("--source-revision must be a full lowercase Git revision")
    if release_revision is not None and REVISION_PATTERN.fullmatch(release_revision) is None:
        raise ReleaseVerificationError("--release-revision must be a full lowercase Git revision")
    if not distributions.is_dir() or not metadata.is_dir() or not source_root.is_dir():
        raise ReleaseVerificationError("distribution, metadata, and source directories must exist")
    wheels = sorted(distributions.glob("*.whl"))
    sdists = sorted(distributions.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise ReleaseVerificationError(
            "distribution directory must contain exactly one wheel and one .tar.gz sdist"
        )
    wheel, sdist = wheels[0], sdists[0]
    package_name, package_version = _wheel_identity(wheel)
    verify_wheel(
        wheel,
        package_name=package_name,
        package_version=package_version,
        source_root=source_root,
    )
    verify_sdist(
        sdist,
        package_name=package_name,
        package_version=package_version,
        source_root=source_root,
    )
    artifacts = {wheel.name: sha256(wheel), sdist.name: sha256(sdist)}
    verify_supply_chain_metadata(
        metadata,
        package_name=package_name,
        package_version=package_version,
        source_revision=source_revision,
        release_revision=release_revision,
        source_snapshot=source_snapshot_sha256(source_root),
        artifacts=artifacts,
    )


def verify_archive(path: Path, *, install_checks: bool = False) -> None:
    if not path.is_file():
        raise ReleaseVerificationError(f"archive not found: {path}")
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
        raise ReleaseVerificationError(f"invalid release ZIP: {path}") from exc
    try:
        with archive:
            _verify_zip_integrity(path, archive)
            with tempfile.TemporaryDirectory(prefix="voicemd-release-") as directory:
                temporary = Path(directory)
                try:
                    root = _safe_extract(archive, temporary)
                except (
                    OSError,
                    EOFError,
                    RuntimeError,
                    NotImplementedError,
                    zipfile.BadZipFile,
                ) as exc:
                    raise ReleaseVerificationError(
                        f"could not extract release ZIP: {path}"
                    ) from exc
                for relative in REQUIRED:
                    required_path = root / relative
                    if relative in REQUIRED_BINARY_FILES:
                        _require_nonempty_file(required_path)
                    else:
                        _read_nonempty(required_path)
                wheel, sdist = verify_artifacts(root)
                if install_checks:
                    verify_runtime(root, wheel, sdist, temporary)
    except ReleaseVerificationError:
        raise
    except OSError as exc:
        raise ReleaseVerificationError(f"could not verify release ZIP: {path}") from exc


def verify_archive_provenance(
    archive_path: Path,
    provenance_path: Path,
    *,
    expected_release_revision: str,
) -> None:
    """Verify the external statement that can bind a ZIP to its non-self-referential commit."""

    if REVISION_PATTERN.fullmatch(expected_release_revision) is None:
        raise ReleaseVerificationError(
            "expected release revision must be a full lowercase Git revision"
        )
    if not archive_path.is_file():
        raise ReleaseVerificationError(f"archive not found: {archive_path}")
    try:
        archive = zipfile.ZipFile(archive_path)
    except (zipfile.BadZipFile, OSError) as exc:
        raise ReleaseVerificationError(f"invalid release ZIP: {archive_path}") from exc
    with archive:
        _verify_zip_integrity(archive_path, archive)
        try:
            raw = archive.read(f"{ARCHIVE_ROOT}/release/BUILD_INFO.json")
        except (
            KeyError,
            OSError,
            EOFError,
            RuntimeError,
            NotImplementedError,
            zipfile.BadZipFile,
        ) as exc:
            raise ReleaseVerificationError(
                "could not read BUILD_INFO.json from release archive"
            ) from exc
    build_info = _strict_json(
        _decode_utf8(raw, label="embedded BUILD_INFO.json"),
        label="embedded BUILD_INFO.json",
    )
    if not isinstance(build_info, dict):
        raise ReleaseVerificationError("embedded BUILD_INFO.json must contain an object")
    source_revision = build_info.get("source_revision")
    source_snapshot = build_info.get("source_sha256")
    package_name = build_info.get("package_name")
    package_version = build_info.get("package_version")
    if not isinstance(source_revision, str) or REVISION_PATTERN.fullmatch(source_revision) is None:
        raise ReleaseVerificationError("embedded BUILD_INFO.json has invalid source_revision")
    if not isinstance(source_snapshot, str) or SHA256_PATTERN.fullmatch(source_snapshot) is None:
        raise ReleaseVerificationError("embedded BUILD_INFO.json has invalid source_sha256")
    if not isinstance(package_name, str) or not isinstance(package_version, str):
        raise ReleaseVerificationError("embedded BUILD_INFO.json has invalid package identity")
    verify_provenance_statement(
        provenance_path,
        package_name=package_name,
        package_version=package_version,
        source_revision=source_revision,
        release_revision=expected_release_revision,
        source_snapshot=source_snapshot,
        subjects={archive_path.name: sha256(archive_path)},
        build_type="urn:voicemd:build:source-release-zip:v1",
    )


def verify_release_archive(
    archive_path: Path,
    *,
    install_checks: bool,
    provenance_path: Path | None = None,
    expected_release_revision: str | None = None,
) -> None:
    """Verify optional external provenance before extraction or runtime execution."""

    if provenance_path is not None:
        if expected_release_revision is None:
            raise ReleaseVerificationError(
                "--expected-release-revision is required with --provenance"
            )
        verify_archive_provenance(
            archive_path,
            provenance_path,
            expected_release_revision=expected_release_revision,
        )
    elif expected_release_revision is not None:
        raise ReleaseVerificationError("--expected-release-revision requires --provenance")
    verify_archive(archive_path, install_checks=install_checks)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path, nargs="?")
    parser.add_argument(
        "--metadata-only",
        action="store_true",
        help="deprecated compatibility flag; metadata-only verification is now the default",
    )
    parser.add_argument(
        "--trusted-runtime-checks",
        action="store_true",
        help=(
            "execute clean installs and tests for a self-built or otherwise trusted archive; "
            "this is not a sandbox or authenticity check"
        ),
    )
    parser.add_argument("--distributions", type=Path)
    parser.add_argument("--metadata", type=Path)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--source-revision")
    parser.add_argument("--release-revision")
    parser.add_argument("--provenance", type=Path)
    parser.add_argument("--expected-release-revision")
    args = parser.parse_args()

    try:
        if args.distributions is not None:
            if (
                args.archive is not None
                or args.metadata_only
                or args.trusted_runtime_checks
                or args.provenance is not None
                or args.expected_release_revision is not None
            ):
                raise ReleaseVerificationError(
                    "archive and --metadata-only cannot be combined with --distributions"
                )
            if args.metadata is None or args.source_root is None or args.source_revision is None:
                raise ReleaseVerificationError(
                    "--metadata, --source-root, and --source-revision are required "
                    "with --distributions"
                )
            verify_distribution_bundle(
                args.distributions,
                args.metadata,
                args.source_root,
                source_revision=args.source_revision,
                release_revision=args.release_revision,
            )
            print(f"PASS_DISTRIBUTIONS {args.distributions.expanduser().resolve()}")
            return 0
        if args.archive is None:
            raise ReleaseVerificationError("archive is required unless --distributions is used")
        if any(
            value is not None
            for value in (
                args.metadata,
                args.source_root,
                args.source_revision,
                args.release_revision,
            )
        ):
            raise ReleaseVerificationError(
                "distribution metadata options require --distributions"
            )
        if args.metadata_only and args.trusted_runtime_checks:
            raise ReleaseVerificationError(
                "--metadata-only and --trusted-runtime-checks cannot be combined"
            )
        archive = args.archive.expanduser().resolve()
        if args.trusted_runtime_checks:
            sys.stderr.write(
                "WARNING: --trusted-runtime-checks executes code from the release archive on "
                "the host. Use it only for self-built or otherwise trusted artifacts; "
                "environment sanitization is not a sandbox or authenticity check.\n"
            )
        verify_release_archive(
            archive,
            install_checks=args.trusted_runtime_checks,
            provenance_path=(
                args.provenance.expanduser().resolve()
                if args.provenance is not None
                else None
            ),
            expected_release_revision=args.expected_release_revision,
        )
    except ReleaseVerificationError as exc:
        parser.error(str(exc))
    result = "PASS_TRUSTED_RUNTIME" if args.trusted_runtime_checks else "PASS_METADATA_ONLY"
    print(f"{result} {archive} sha256={sha256(archive)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
