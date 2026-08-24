#!/usr/bin/env python3
"""Create a deterministic source ZIP from Git-tracked repository files."""

from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import stat
import subprocess
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from pathlib import Path, PurePosixPath
from typing import Any

ARCHIVE_ROOT = "voicemd-agent-standard"
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
MAX_ARCHIVE_MEMBERS = 20_000
MAX_ARCHIVE_SIZE = 256 * 1024 * 1024
REGULAR_GIT_MODES = {"100644": 0o644, "100755": 0o755}
REVISION_PATTERN = re.compile(r"[0-9a-f]{40}")
SOURCE_SNAPSHOT_DOMAIN = b"VoiceMD source snapshot v2\0"
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


class ReleaseBuildError(RuntimeError):
    """Raised when the source tree cannot be packaged safely."""


@dataclass(frozen=True)
class TrackedFile:
    relative: PurePosixPath
    permissions: int
    object_id: str


@dataclass(frozen=True)
class DistributionMetadata:
    name: str
    version: str
    license_expression: str
    requirements: tuple[str, ...]
    artifacts: tuple[Path, ...]


def _forbidden_name(name: str) -> bool:
    folded = name.casefold()
    return name in FORBIDDEN_NAMES or folded == ".env" or folded.startswith(".env.")


def _git(root: Path, *arguments: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", os.fspath(root), *arguments],
        check=False,
        capture_output=True,
    )
    if completed.returncode:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise ReleaseBuildError(detail or "Git command failed")
    return completed.stdout


def _canonical_json(data: object) -> bytes:
    return (
        json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _revision(root: Path, value: str | None) -> str:
    revision = value or _git(root, "rev-parse", "HEAD").decode("ascii", errors="strict").strip()
    if REVISION_PATTERN.fullmatch(revision) is None:
        raise ReleaseBuildError(f"revision must be a full lowercase Git SHA-1: {revision!r}")
    _git(root, "cat-file", "-e", f"{revision}^{{commit}}")
    return revision


def _created_timestamp(root: Path, revision: str) -> str:
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if epoch is not None:
        try:
            instant = datetime.fromtimestamp(int(epoch), tz=timezone.utc)
        except (OverflowError, ValueError) as exc:
            raise ReleaseBuildError("SOURCE_DATE_EPOCH must be an integer Unix timestamp") from exc
    else:
        raw = _git(root, "show", "-s", "--format=%cI", revision).decode(
            "ascii", errors="strict"
        ).strip()
        try:
            instant = datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError as exc:
            raise ReleaseBuildError(f"could not parse Git commit timestamp: {raw!r}") from exc
    return instant.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _source_snapshot_sha256(root: Path, files: list[TrackedFile]) -> str:
    """Hash source paths, canonical executable modes, and Git blob bytes outside release/."""

    digest = hashlib.sha256(SOURCE_SNAPSHOT_DOMAIN)
    for tracked in files:
        if tracked.relative.parts[0] == "release":
            continue
        name = tracked.relative.as_posix().encode("utf-8")
        content = _git(root, "cat-file", "blob", tracked.object_id)
        digest.update(len(name).to_bytes(8, "big"))
        digest.update(name)
        digest.update(tracked.permissions.to_bytes(2, "big"))
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def normalize_sdist(path: Path, *, epoch: int) -> Path:
    """Rewrite a trusted setuptools sdist into deterministic tar/gzip bytes."""

    path = path.expanduser().resolve()
    if not path.is_file():
        raise ReleaseBuildError(f"source distribution does not exist: {path}")
    if epoch < 0 or epoch > 0xFFFFFFFF:
        raise ReleaseBuildError("source distribution epoch must fit an unsigned 32-bit value")
    try:
        source = tarfile.open(path, mode="r:gz")  # noqa: SIM115
    except (tarfile.TarError, OSError) as exc:
        raise ReleaseBuildError(f"invalid source distribution: {path}") from exc

    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with source, temporary.open("wb") as raw_output:
            members = source.getmembers()
            if not members or len(members) > MAX_ARCHIVE_MEMBERS:
                raise ReleaseBuildError("source distribution has an invalid member count")
            if sum(member.size for member in members) > MAX_ARCHIVE_SIZE:
                raise ReleaseBuildError("source distribution exceeds the normalization size limit")
            names: set[str] = set()
            for member in members:
                normalized_name = member.name.rstrip("/")
                parts = normalized_name.split("/")
                if (
                    normalized_name in names
                    or "\\" in member.name
                    or member.name.startswith("/")
                    or not parts
                    or any(part in {"", ".", ".."} for part in parts)
                    or not (member.isfile() or member.isdir())
                ):
                    raise ReleaseBuildError(
                        f"unsafe source distribution member: {member.name}"
                    )
                names.add(normalized_name)

            with gzip.GzipFile(
                filename="",
                mode="wb",
                compresslevel=9,
                fileobj=raw_output,
                mtime=epoch,
            ) as compressed, tarfile.open(
                fileobj=compressed,
                mode="w",
                format=tarfile.PAX_FORMAT,
            ) as normalized_archive:
                for member in sorted(members, key=lambda item: item.name.encode("utf-8")):
                    normalized = copy.copy(member)
                    normalized.uid = 0
                    normalized.gid = 0
                    normalized.uname = ""
                    normalized.gname = ""
                    normalized.mtime = epoch
                    normalized.mode = (
                        0o755 if member.isdir() or member.mode & 0o111 else 0o644
                    )
                    normalized.pax_headers = {}
                    normalized.devmajor = 0
                    normalized.devminor = 0
                    if member.isfile():
                        extracted = source.extractfile(member)
                        if extracted is None:
                            raise ReleaseBuildError(
                                f"could not read source distribution member: {member.name}"
                            )
                        with extracted:
                            normalized_archive.addfile(normalized, extracted)
                    else:
                        normalized_archive.addfile(normalized)
            raw_output.flush()
            os.fsync(raw_output.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return path


def _validate_repository_root(root: Path) -> None:
    if not root.is_dir():
        raise ReleaseBuildError(f"repository root is not a directory: {root}")
    top_level = Path(
        _git(root, "rev-parse", "--show-toplevel").decode("utf-8", errors="strict").strip()
    ).resolve()
    if top_level != root:
        raise ReleaseBuildError(f"--root must be the Git repository root: {top_level}")


def _parse_tree_files(root: Path, revision: str) -> list[TrackedFile]:
    output = _git(root, "ls-tree", "-r", "-z", "--full-tree", revision)
    files: list[TrackedFile] = []
    for record in output.split(b"\0"):
        if not record:
            continue
        try:
            metadata, raw_path = record.split(b"\t", maxsplit=1)
            mode, object_type, raw_object_id = metadata.split(maxsplit=2)
            relative_text = raw_path.decode("utf-8", errors="strict")
            object_id = raw_object_id.decode("ascii", errors="strict")
        except (UnicodeDecodeError, ValueError) as exc:
            raise ReleaseBuildError("could not parse a Git tree entry") from exc

        relative = PurePosixPath(relative_text)
        if (
            relative.is_absolute()
            or not relative.parts
            or any(part in {"", ".", ".."} for part in relative.parts)
        ):
            raise ReleaseBuildError(f"unsafe tracked path: {relative_text}")
        if any(
            part in FORBIDDEN_PARTS or part.endswith(".egg-info") for part in relative.parts
        ):
            raise ReleaseBuildError(f"forbidden tracked release path: {relative_text}")
        if any(_forbidden_name(part) for part in relative.parts) or (
            relative.suffix in FORBIDDEN_SUFFIXES
        ):
            raise ReleaseBuildError(f"forbidden tracked release file: {relative_text}")

        mode_text = mode.decode("ascii", errors="strict")
        if object_type != b"blob" or mode_text not in REGULAR_GIT_MODES:
            kind = {
                "120000": "symbolic link",
                "160000": "Git submodule",
            }.get(mode_text, f"unsupported mode {mode_text}")
            raise ReleaseBuildError(f"tracked {kind} is not allowed in a release: {relative_text}")
        files.append(
            TrackedFile(
                relative=relative,
                permissions=REGULAR_GIT_MODES[mode_text],
                object_id=object_id,
            )
        )
    if not files:
        raise ReleaseBuildError("Git tree contains no files")
    return sorted(files, key=lambda item: item.relative.as_posix().encode("utf-8"))


def _parse_index(root: Path) -> dict[str, tuple[str, str]]:
    output = _git(root, "ls-files", "--cached", "--stage", "-z")
    entries: dict[str, tuple[str, str]] = {}
    for record in output.split(b"\0"):
        if not record:
            continue
        try:
            metadata, raw_path = record.split(b"\t", maxsplit=1)
            mode, object_id, stage = metadata.split(maxsplit=2)
            relative_text = raw_path.decode("utf-8", errors="strict")
            mode_text = mode.decode("ascii", errors="strict")
            object_id_text = object_id.decode("ascii", errors="strict")
        except (UnicodeDecodeError, ValueError) as exc:
            raise ReleaseBuildError("could not parse a Git index entry") from exc
        if stage != b"0":
            raise ReleaseBuildError(f"unmerged Git index entry: {relative_text}")
        entries[relative_text] = (mode_text, object_id_text)
    return entries


def _validate_clean_checkout(root: Path, files: list[TrackedFile]) -> None:
    """Prove that index and worktree content match the selected commit tree."""

    untracked = [
        path.decode("utf-8", errors="replace")
        for path in _git(root, "ls-files", "--others", "--exclude-standard", "-z").split(b"\0")
        if path
    ]
    if untracked:
        preview = ", ".join(sorted(untracked)[:10])
        raise ReleaseBuildError(
            "untracked files are not allowed in a release source tree; "
            f"add, ignore, or remove them first: {preview}"
        )

    expected_index = {
        item.relative.as_posix(): (
            "100755" if item.permissions & 0o111 else "100644",
            item.object_id,
        )
        for item in files
    }
    actual_index = _parse_index(root)
    if actual_index != expected_index:
        raise ReleaseBuildError("Git index must exactly match the selected release revision")

    for tracked in files:
        relative_text = tracked.relative.as_posix()
        source = root.joinpath(*tracked.relative.parts)
        try:
            source_mode = source.lstat().st_mode
        except FileNotFoundError as exc:
            raise ReleaseBuildError(
                f"tracked file is missing from the worktree: {relative_text}"
            ) from exc
        if not stat.S_ISREG(source_mode):
            raise ReleaseBuildError(f"tracked path is not a regular file: {relative_text}")
        resolved = source.resolve(strict=True)
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise ReleaseBuildError(f"tracked path escapes the repository: {relative_text}") from exc
        # Hash through Git's clean-filter pipeline so a checkout using a native
        # CRLF representation remains equivalent to the canonical blob. This
        # still reads the worktree even for assume-unchanged entries and does
        # not add the candidate object to Git's object database.
        worktree_object_id = _git(
            root,
            "hash-object",
            f"--path={relative_text}",
            "--",
            relative_text,
        ).decode("ascii", errors="strict").strip()
        if worktree_object_id != tracked.object_id:
            raise ReleaseBuildError(
                "tracked source and index must match the selected release revision: "
                f"{relative_text}"
            )


def tracked_files(root: Path, revision: str | None = None) -> list[TrackedFile]:
    """Return safe regular files from a commit after proving checkout equivalence."""

    _validate_repository_root(root)
    revision = _revision(root, revision)
    files = _parse_tree_files(root, revision)
    _validate_clean_checkout(root, files)
    return files


def _distribution_metadata(directory: Path) -> DistributionMetadata:
    directory = directory.expanduser().resolve()
    if not directory.is_dir():
        raise ReleaseBuildError(f"distribution directory does not exist: {directory}")
    wheels = sorted(directory.glob("*.whl"))
    sdists = sorted(directory.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise ReleaseBuildError(
            "distribution directory must contain exactly one wheel and one .tar.gz sdist"
        )
    wheel = wheels[0]
    try:
        with zipfile.ZipFile(wheel) as archive:
            metadata_names = [
                name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
            ]
            if len(metadata_names) != 1:
                raise ReleaseBuildError(f"wheel must contain exactly one METADATA: {wheel.name}")
            metadata = BytesParser(policy=policy.default).parsebytes(
                archive.read(metadata_names[0])
            )
    except zipfile.BadZipFile as exc:
        raise ReleaseBuildError(f"invalid wheel: {wheel.name}") from exc
    name = metadata.get("Name")
    version = metadata.get("Version")
    if not name or not version:
        raise ReleaseBuildError(f"wheel METADATA lacks Name or Version: {wheel.name}")
    license_expression = metadata.get("License-Expression") or "NOASSERTION"
    requirements = tuple(sorted(metadata.get_all("Requires-Dist", [])))
    return DistributionMetadata(
        name=name,
        version=version,
        license_expression=license_expression,
        requirements=requirements,
        artifacts=(wheel, sdists[0]),
    )


def _spdx_id(prefix: str, value: str) -> str:
    suffix = hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]
    return f"SPDXRef-{prefix}-{suffix}"


def _requirement_name(requirement: str) -> str:
    match = re.match(r"[A-Za-z0-9][A-Za-z0-9._-]*", requirement)
    if match is None:
        raise ReleaseBuildError(f"cannot identify dependency name: {requirement!r}")
    return match.group(0)


def _spdx_document(
    metadata: DistributionMetadata,
    *,
    source_revision: str,
    source_snapshot: str,
    created: str,
    artifact_digests: dict[str, str] | None = None,
) -> dict[str, Any]:
    expected_artifacts = {path.name for path in metadata.artifacts}
    if artifact_digests is None:
        artifact_digests = {path.name: _sha256(path) for path in metadata.artifacts}
    elif set(artifact_digests) != expected_artifacts:
        raise ReleaseBuildError("SPDX artifact digest inventory does not match distributions")
    namespace_seed = "\0".join(
        [source_revision, source_snapshot]
        + [f"{name}:{artifact_digests[name]}" for name in sorted(artifact_digests)]
    )
    namespace_digest = hashlib.sha256(namespace_seed.encode("utf-8")).hexdigest()
    package_id = _spdx_id("Package", f"{metadata.name}@{metadata.version}")
    files: list[dict[str, Any]] = []
    relationships: list[dict[str, str]] = [
        {
            "spdxElementId": "SPDXRef-DOCUMENT",
            "relationshipType": "DESCRIBES",
            "relatedSpdxElement": package_id,
        }
    ]
    for path in sorted(metadata.artifacts, key=lambda item: item.name.encode("utf-8")):
        file_id = _spdx_id("Artifact", path.name)
        files.append(
            {
                "SPDXID": file_id,
                "checksums": [
                    {"algorithm": "SHA256", "checksumValue": artifact_digests[path.name]}
                ],
                "copyrightText": "NOASSERTION",
                "fileName": f"./{path.name}",
                "licenseConcluded": "NOASSERTION",
            }
        )
        relationships.append(
            {
                "spdxElementId": package_id,
                "relationshipType": "CONTAINS",
                "relatedSpdxElement": file_id,
            }
        )

    packages: list[dict[str, Any]] = [
        {
            "SPDXID": package_id,
            "copyrightText": "NOASSERTION",
            "downloadLocation": "NOASSERTION",
            "externalRefs": [
                {
                    "referenceCategory": "PACKAGE-MANAGER",
                    "referenceLocator": f"pkg:pypi/{metadata.name}@{metadata.version}",
                    "referenceType": "purl",
                }
            ],
            "filesAnalyzed": False,
            "licenseConcluded": "NOASSERTION",
            "licenseDeclared": metadata.license_expression,
            "name": metadata.name,
            "sourceInfo": (
                f"Git source revision {source_revision}; "
                f"VoiceMD source snapshot SHA-256 {source_snapshot}"
            ),
            "versionInfo": metadata.version,
        }
    ]
    for requirement in metadata.requirements:
        dependency_name = _requirement_name(requirement)
        dependency_id = _spdx_id("Dependency", requirement)
        packages.append(
            {
                "SPDXID": dependency_id,
                "copyrightText": "NOASSERTION",
                "downloadLocation": "NOASSERTION",
                "externalRefs": [
                    {
                        "referenceCategory": "PACKAGE-MANAGER",
                        "referenceLocator": f"pkg:pypi/{dependency_name}",
                        "referenceType": "purl",
                    }
                ],
                "filesAnalyzed": False,
                "licenseConcluded": "NOASSERTION",
                "licenseDeclared": "NOASSERTION",
                "name": dependency_name,
                "summary": f"Declared Python requirement: {requirement}",
                "versionInfo": requirement,
            }
        )
        relationships.append(
            {
                "spdxElementId": package_id,
                "relationshipType": "DEPENDS_ON",
                "relatedSpdxElement": dependency_id,
            }
        )

    return {
        "SPDXID": "SPDXRef-DOCUMENT",
        "creationInfo": {
            "created": created,
            "creators": ["Tool: VoiceMD scripts/build_release.py"],
        },
        "dataLicense": "CC0-1.0",
        "documentDescribes": [package_id],
        "documentNamespace": (
            f"https://spdx.org/spdxdocs/{metadata.name}-{metadata.version}-{namespace_digest}"
        ),
        "files": files,
        "name": f"{metadata.name}-{metadata.version}-release",
        "packages": packages,
        "relationships": relationships,
        "spdxVersion": "SPDX-2.3",
    }


def _provenance_statement(
    subjects: dict[str, str],
    *,
    package_name: str,
    package_version: str,
    source_revision: str,
    release_revision: str,
    source_snapshot: str,
    build_type: str,
    build_tool_versions: dict[str, str] | None = None,
) -> dict[str, Any]:
    return {
        "_type": "https://in-toto.io/Statement/v1",
        "predicate": {
            "buildDefinition": {
                "buildType": build_type,
                "externalParameters": {
                    "packageName": package_name,
                    "packageVersion": package_version,
                },
                "internalParameters": {
                    "buildToolVersions": build_tool_versions or {},
                    "releaseRevision": release_revision,
                    "sourceRevision": source_revision,
                    "sourceSnapshotSha256": source_snapshot,
                },
                "resolvedDependencies": [
                    {
                        "digest": {"sha1": source_revision},
                        "uri": f"urn:git:commit:{source_revision}",
                    }
                ],
            },
            "runDetails": {
                "builder": {"id": "urn:voicemd:builder:scripts-build-release-py:v1"}
            },
        },
        "predicateType": "https://slsa.dev/provenance/v1",
        "subject": [
            {"digest": {"sha256": digest}, "name": name}
            for name, digest in sorted(subjects.items(), key=lambda item: item[0].encode("utf-8"))
        ],
    }


def _build_tool_versions() -> dict[str, str]:
    versions = {"python": platform.python_version()}
    for distribution in ("build", "packaging", "pyproject-hooks", "setuptools", "wheel"):
        try:
            versions[distribution] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            continue
    return versions


def _require_source_tree_matches(
    root: Path,
    *,
    source_revision: str,
    checkout_files: list[TrackedFile],
) -> tuple[list[TrackedFile], str]:
    source_files = _parse_tree_files(root, source_revision)
    source_snapshot = _source_snapshot_sha256(root, source_files)
    checkout_snapshot = _source_snapshot_sha256(root, checkout_files)
    if source_snapshot != checkout_snapshot:
        raise ReleaseBuildError(
            "the checkout's non-release source snapshot does not match --source-revision"
        )
    return source_files, source_snapshot


def generate_release_metadata(
    root: Path,
    distributions: Path,
    output: Path,
    *,
    source_revision: str | None = None,
    release_revision: str | None = None,
) -> tuple[Path, Path]:
    """Generate a deterministic SPDX SBOM and unsigned in-toto provenance statement."""

    root = root.expanduser().resolve()
    checkout_revision = _revision(root, None)
    files = tracked_files(root, checkout_revision)
    source_revision = _revision(root, source_revision)
    release_revision = _revision(root, release_revision)
    if release_revision != checkout_revision:
        raise ReleaseBuildError("--release-revision must identify the current clean checkout")
    initial_artifact_digests = {
        path.name: _sha256(path)
        for path in sorted(
            (
                *distributions.expanduser().resolve().glob("*.whl"),
                *distributions.expanduser().resolve().glob("*.tar.gz"),
            ),
            key=lambda item: item.name.encode("utf-8"),
        )
    }
    metadata = _distribution_metadata(distributions)
    artifact_digests = {path.name: _sha256(path) for path in metadata.artifacts}
    if artifact_digests != initial_artifact_digests:
        raise ReleaseBuildError("distribution artifacts changed while metadata was being read")
    _source_files, snapshot = _require_source_tree_matches(
        root,
        source_revision=source_revision,
        checkout_files=files,
    )
    created = _created_timestamp(root, source_revision)

    output = output.expanduser().resolve()
    sbom_path = output / "SBOM.spdx.json"
    provenance_path = output / "PROVENANCE.intoto.jsonl"
    sbom = _spdx_document(
        metadata,
        source_revision=source_revision,
        source_snapshot=snapshot,
        created=created,
        artifact_digests=artifact_digests,
    )
    _atomic_write(sbom_path, _canonical_json(sbom))
    subjects = dict(artifact_digests)
    subjects[sbom_path.name] = _sha256(sbom_path)
    provenance = _provenance_statement(
        subjects,
        package_name=metadata.name,
        package_version=metadata.version,
        source_revision=source_revision,
        release_revision=release_revision,
        source_snapshot=snapshot,
        build_type="urn:voicemd:build:python-distributions:v1",
        build_tool_versions=_build_tool_versions(),
    )
    _atomic_write(provenance_path, _canonical_json(provenance))
    if {path.name: _sha256(path) for path in metadata.artifacts} != artifact_digests:
        raise ReleaseBuildError("distribution artifacts changed during metadata generation")
    return sbom_path, provenance_path


def _require_archive_matches_tree(
    root: Path,
    archive: Path,
    files: list[TrackedFile],
) -> None:
    expected = {
        (PurePosixPath(ARCHIVE_ROOT) / tracked.relative).as_posix(): tracked
        for tracked in files
    }
    try:
        with zipfile.ZipFile(archive) as packaged:
            infos = packaged.infolist()
            if len(infos) != len(expected) or set(packaged.namelist()) != set(expected):
                raise ReleaseBuildError(
                    "release archive inventory does not match the selected release revision"
                )
            for info in infos:
                tracked = expected[info.filename]
                archived_mode = (info.external_attr >> 16) & 0xFFFF
                expected_mode = stat.S_IFREG | tracked.permissions
                if archived_mode != expected_mode or packaged.read(info) != _git(
                    root, "cat-file", "blob", tracked.object_id
                ):
                    raise ReleaseBuildError(
                        "release archive bytes or modes do not match the selected release "
                        f"revision: {tracked.relative.as_posix()}"
                    )
            corrupt = packaged.testzip()
            if corrupt is not None:
                raise ReleaseBuildError(f"release archive contains a corrupt member: {corrupt}")
    except zipfile.BadZipFile as exc:
        raise ReleaseBuildError(f"release archive is not a valid ZIP: {archive}") from exc


def generate_archive_provenance(root: Path, archive: Path, output: Path) -> Path:
    """Bind an outer ZIP to its exact Git release revision without self-reference."""

    root = root.expanduser().resolve()
    archive = archive.expanduser().resolve()
    if not archive.is_file():
        raise ReleaseBuildError(f"release archive does not exist: {archive}")
    release_revision = _revision(root, None)
    files = tracked_files(root, release_revision)
    _require_archive_matches_tree(root, archive, files)
    source_revision = release_revision
    package_name = "voicemd"
    package_version = "unknown"
    build_info_file = next(
        (item for item in files if item.relative == PurePosixPath("release/BUILD_INFO.json")),
        None,
    )
    if build_info_file is not None:
        try:
            build_info = json.loads(
                _git(root, "cat-file", "blob", build_info_file.object_id).decode("utf-8")
            )
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ReleaseBuildError("release/BUILD_INFO.json is not valid JSON") from exc
        if not isinstance(build_info, dict):
            raise ReleaseBuildError("release/BUILD_INFO.json must contain an object")
        recorded_source_revision = build_info.get("source_revision")
        if not isinstance(recorded_source_revision, str):
            raise ReleaseBuildError("release/BUILD_INFO.json requires source_revision")
        source_revision = _revision(root, recorded_source_revision)
        recorded_package_name = build_info.get("package_name")
        recorded_package_version = build_info.get("package_version")
        if not isinstance(recorded_package_name, str) or not recorded_package_name:
            raise ReleaseBuildError("release/BUILD_INFO.json requires package_name")
        if not isinstance(recorded_package_version, str) or not recorded_package_version:
            raise ReleaseBuildError("release/BUILD_INFO.json requires package_version")
        package_name = recorded_package_name
        package_version = recorded_package_version
    _source_files, source_snapshot = _require_source_tree_matches(
        root,
        source_revision=source_revision,
        checkout_files=files,
    )
    statement = _provenance_statement(
        {archive.name: _sha256(archive)},
        package_name=package_name,
        package_version=package_version,
        source_revision=source_revision,
        release_revision=release_revision,
        source_snapshot=source_snapshot,
        build_type="urn:voicemd:build:source-release-zip:v1",
        build_tool_versions=_build_tool_versions(),
    )
    output = output.expanduser().resolve()
    _atomic_write(output, _canonical_json(statement))
    return output


def build_release(root: Path, output: Path) -> Path:
    root = root.expanduser().resolve()
    output = output.expanduser().resolve()
    files = tracked_files(root)

    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and not output.is_file():
        raise ReleaseBuildError(f"output is not a regular file: {output}")

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.", dir=output.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(
            temporary,
            "w",
            # Stored members avoid zlib-version drift in release hashes.
            compression=zipfile.ZIP_STORED,
            strict_timestamps=True,
        ) as archive:
            for tracked in files:
                archive_name = (
                    PurePosixPath(ARCHIVE_ROOT) / tracked.relative
                ).as_posix()
                info = zipfile.ZipInfo(archive_name, ZIP_TIMESTAMP)
                info.create_system = 3
                info.compress_type = zipfile.ZIP_STORED
                info.external_attr = (stat.S_IFREG | tracked.permissions) << 16
                info.flag_bits |= 0x800  # UTF-8 file names.
                archive.writestr(info, _git(root, "cat-file", "blob", tracked.object_id))
        os.replace(temporary, output)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", default="dist/voicemd-agent-standard.zip")
    parser.add_argument(
        "--distributions",
        type=Path,
        help="generate release metadata for the wheel and sdist in this directory",
    )
    parser.add_argument(
        "--metadata-output",
        type=Path,
        help="directory for SBOM.spdx.json and PROVENANCE.intoto.jsonl",
    )
    parser.add_argument("--source-revision")
    parser.add_argument("--release-revision")
    parser.add_argument(
        "--normalize-sdist",
        type=Path,
        help="rewrite a trusted setuptools sdist deterministically using SOURCE_DATE_EPOCH",
    )
    parser.add_argument(
        "--provenance-output",
        type=Path,
        help="write an external unsigned in-toto statement for the outer source ZIP",
    )
    args = parser.parse_args()

    try:
        root = Path(args.root)
        if args.normalize_sdist is not None:
            if any(
                value is not None
                for value in (
                    args.distributions,
                    args.metadata_output,
                    args.source_revision,
                    args.release_revision,
                    args.provenance_output,
                )
            ):
                raise ReleaseBuildError(
                    "--normalize-sdist cannot be combined with other build modes"
                )
            raw_epoch = os.environ.get("SOURCE_DATE_EPOCH")
            if raw_epoch is None:
                raise ReleaseBuildError(
                    "SOURCE_DATE_EPOCH is required with --normalize-sdist"
                )
            try:
                epoch = int(raw_epoch)
            except ValueError as exc:
                raise ReleaseBuildError(
                    "SOURCE_DATE_EPOCH must be an integer Unix timestamp"
                ) from exc
            output = normalize_sdist(args.normalize_sdist, epoch=epoch)
            print(output)
            return 0
        if args.distributions is not None:
            if args.metadata_output is None:
                raise ReleaseBuildError("--metadata-output is required with --distributions")
            if args.provenance_output is not None:
                raise ReleaseBuildError(
                    "--provenance-output cannot be combined with --distributions"
                )
            sbom, provenance = generate_release_metadata(
                root,
                args.distributions,
                args.metadata_output,
                source_revision=args.source_revision,
                release_revision=args.release_revision,
            )
            print(sbom)
            print(provenance)
            return 0
        if args.metadata_output is not None or args.source_revision or args.release_revision:
            raise ReleaseBuildError(
                "--metadata-output and revision options require --distributions"
            )
        output = build_release(root, Path(args.output))
        if args.provenance_output is not None:
            provenance = generate_archive_provenance(root, output, args.provenance_output)
            print(provenance)
    except ReleaseBuildError as exc:
        parser.error(str(exc))
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
