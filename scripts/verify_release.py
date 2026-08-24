#!/usr/bin/env python3
"""Verify a VoiceMD release ZIP and its embedded package artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import venv
import zipfile
from datetime import date
from email.parser import BytesParser
from pathlib import Path, PurePosixPath
from typing import Any

ARCHIVE_ROOT = "voicemd-agent-standard"
MAX_MEMBER_SIZE = 64 * 1024 * 1024
MAX_TOTAL_SIZE = 256 * 1024 * 1024
REQUIRED = {
    "README.md",
    "START_HERE_RU.md",
    "PACKAGE_CONTENTS.md",
    "SPECIFICATION.md",
    "VOICE.md",
    ".voicemd-root",
    "schema/voice.schema.json",
    "manifest.json",
    "pyproject.toml",
    "MANIFEST.in",
    ".dockerignore",
    "src/voicemd/cli.py",
    "src/voicemd/resources/skill/SKILL.md",
    ".agents/skills/voice-contract/SKILL.md",
    "integrations/http/openapi.yaml",
    "integrations/docker/Dockerfile",
    "integrations/mcp/server.py",
    "integrations/nemotron-voicechat/session_update.py",
    "scripts/build_release.py",
    "scripts/verify_release.py",
    "release/BUILD_INFO.json",
    "release/README.md",
    "release/SHA256SUMS",
    "release/VERIFICATION.md",
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
    "PACKAGE_CONTENTS.md",
    "README.md",
    "ROADMAP.md",
    "SECURITY.md",
    "SPECIFICATION.md",
    "START_HERE_RU.md",
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


class ReleaseVerificationError(RuntimeError):
    """Raised when release evidence is absent, stale, unsafe, or inconsistent."""


def _forbidden_name(name: str) -> bool:
    return name in FORBIDDEN_NAMES or name.startswith(".env.")


def _forbidden_relative(relative: PurePosixPath) -> bool:
    return any(
        part in FORBIDDEN_PARTS or part.endswith(".egg-info")
        for part in relative.parts
    ) or _forbidden_name(relative.name) or relative.suffix in FORBIDDEN_SUFFIXES


def source_snapshot_sha256(root: Path) -> str:
    """Hash non-release source paths and bytes without depending on Git metadata."""

    entries: list[tuple[str, Path]] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        relative = PurePosixPath(path.relative_to(root).as_posix())
        if not relative.parts or relative.parts[0] in {".git", "release"}:
            continue
        if _forbidden_relative(relative):
            continue
        entries.append((relative.as_posix(), path))
    digest = hashlib.sha256()
    for name, path in sorted(entries, key=lambda item: item[0].encode("utf-8")):
        raw_name = name.encode("utf-8")
        content = path.read_bytes()
        digest.update(len(raw_name).to_bytes(8, "big"))
        digest.update(raw_name)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_nonempty(path: Path) -> str:
    if not path.is_file():
        raise ReleaseVerificationError(f"required file missing: {path}")
    if path.stat().st_size <= 0:
        raise ReleaseVerificationError(f"required file is empty: {path}")
    return path.read_text(encoding="utf-8")


def _strict_json(text: str, *, label: str) -> object:
    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite number {value}")

    try:
        return json.loads(text, parse_constant=reject_constant)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ReleaseVerificationError(f"invalid strict JSON in {label}: {exc}") from exc


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
            manifest.get("release"),
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
    return not _forbidden_relative(relative)


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
        seen: set[str] = set()
        total_size = 0
        for info in wheel.infolist():
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
        _validate_distribution_metadata(
            wheel.read(metadata_names[0]),
            package_name=package_name,
            package_version=package_version,
            artifact_name=path.name,
        )
        if source_root is not None:
            package_root = source_root / "src/voicemd"
            for source in sorted(package_root.rglob("*")):
                if not _is_release_source(source, source_root):
                    continue
                wheel_name = source.relative_to(source_root / "src").as_posix()
                if wheel_name not in seen:
                    raise ReleaseVerificationError(
                        f"wheel is missing current package source: {wheel_name}"
                    )
                if wheel.read(wheel_name) != source.read_bytes():
                    raise ReleaseVerificationError(
                        f"wheel package source is stale: {wheel_name}"
                    )


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
        roots = {member.parts[0] for member in paths}
        if len(roots) != 1:
            raise ReleaseVerificationError(f"sdist must contain exactly one root: {path.name}")
        root_name = next(iter(roots))
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
            for source in _sdist_sync_sources(source_root):
                relative = source.relative_to(source_root).as_posix()
                member_name = f"{root_name}/{relative}"
                if member_name not in names:
                    raise ReleaseVerificationError(
                        f"sdist is missing current release source: {relative}"
                    )
                extracted = archive.extractfile(member_name)
                if extracted is None or extracted.read() != source.read_bytes():
                    raise ReleaseVerificationError(f"sdist release source is stale: {relative}")


def verify_artifacts(root: Path) -> tuple[Path, Path]:
    build_info = load_build_info(root)
    artifact_metadata = build_info["artifacts"]
    declared = set(artifact_metadata)
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
        if actual != artifact_metadata[name]["sha256"]:
            raise ReleaseVerificationError(
                f"BUILD_INFO.json checksum mismatch for {name}: {actual}"
            )

    wheel_name = next(name for name in declared if name.endswith(".whl"))
    sdist_name = next(name for name in declared if name.endswith(".tar.gz"))
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
    return wheel, sdist


def _validate_archive_members(archive: zipfile.ZipFile) -> None:
    seen: set[str] = set()
    relative_files: set[str] = set()
    total_size = 0
    for info in archive.infolist():
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
        if file_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
            raise ReleaseVerificationError(f"unsupported ZIP member type: {name}")
        if info.file_size > MAX_MEMBER_SIZE:
            raise ReleaseVerificationError(f"oversized ZIP member: {name}")
        total_size += info.file_size
        if total_size > MAX_TOTAL_SIZE:
            raise ReleaseVerificationError("release ZIP exceeds uncompressed size limit")

        relative_parts = raw_parts[1:]
        if info.is_dir():
            continue
        if not relative_parts:
            raise ReleaseVerificationError("archive root may not be a file")
        relative = PurePosixPath(*relative_parts)
        if _forbidden_relative(relative):
            raise ReleaseVerificationError(f"forbidden build/cache member: {name}")
        relative_files.add(relative.as_posix())

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


def run(command: list[str], *, cwd: Path, env: dict[str, str]) -> None:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        sys.stderr.write(completed.stdout)
        sys.stderr.write(completed.stderr)
        raise ReleaseVerificationError(
            f"command failed ({completed.returncode}): {' '.join(command)}"
        )


def _venv_python(environment: Path) -> Path:
    directory = "Scripts" if os.name == "nt" else "bin"
    executable = "python.exe" if os.name == "nt" else "python"
    return environment / directory / executable


def verify_runtime(root: Path, wheel: Path, sdist: Path, temporary: Path) -> None:
    base_env = os.environ.copy()
    for variable in ("PYTHONPATH", "VOICE_MD", "VOICE_MD_HOME", "VOICE_MD_ROOT"):
        base_env.pop(variable, None)
    base_env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    smoke_env = {**base_env, "VOICE_MD_ROOT": str(root)}

    wheel_environment = temporary / "wheel-env"
    venv.EnvBuilder(with_pip=True, clear=True).create(wheel_environment)
    wheel_python = _venv_python(wheel_environment)
    run(
        [str(wheel_python), "-m", "pip", "install", str(wheel)],
        cwd=root,
        env=base_env,
    )
    run([str(wheel_python), "-m", "pip", "check"], cwd=root, env=base_env)
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
    prompt = output.read_text(encoding="utf-8")
    if not prompt.isascii() or len(prompt) > 5000:
        raise ReleaseVerificationError("Nemotron smoke output is not valid ASCII within budget")

    sdist_environment = temporary / "sdist-env"
    venv.EnvBuilder(with_pip=True, clear=True).create(sdist_environment)
    sdist_python = _venv_python(sdist_environment)
    run(
        [
            str(sdist_python),
            "-m",
            "pip",
            "install",
            str(sdist),
            "pytest>=8,<9",
        ],
        cwd=root,
        env=base_env,
    )
    run([str(sdist_python), "-m", "pip", "check"], cwd=root, env=base_env)
    run([str(sdist_python), "-m", "pytest", "-q"], cwd=root, env=base_env)


def verify_archive(path: Path, *, install_checks: bool = True) -> None:
    if not path.is_file():
        raise ReleaseVerificationError(f"archive not found: {path}")
    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        raise ReleaseVerificationError(f"invalid release ZIP: {path}") from exc
    with archive:
        _validate_archive_members(archive)
        corrupt = archive.testzip()
        if corrupt:
            raise ReleaseVerificationError(f"corrupt ZIP member: {corrupt}")
        with tempfile.TemporaryDirectory(prefix="voicemd-release-") as directory:
            temporary = Path(directory)
            root = _safe_extract(archive, temporary)
            for relative in REQUIRED:
                _read_nonempty(root / relative)
            wheel, sdist = verify_artifacts(root)
            if install_checks:
                verify_runtime(root, wheel, sdist, temporary)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument(
        "--metadata-only",
        action="store_true",
        help="verify structure, metadata, package formats, and hashes without clean installs",
    )
    args = parser.parse_args()
    archive = args.archive.expanduser().resolve()

    try:
        verify_archive(archive, install_checks=not args.metadata_only)
    except ReleaseVerificationError as exc:
        parser.error(str(exc))
    result = "PASS_METADATA_ONLY" if args.metadata_only else "PASS"
    print(f"{result} {archive} sha256={sha256(archive)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
