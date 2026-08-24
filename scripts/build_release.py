#!/usr/bin/env python3
"""Create a deterministic source ZIP from Git-tracked repository files."""

from __future__ import annotations

import argparse
import os
import stat
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

ARCHIVE_ROOT = "voicemd-agent-standard"
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
REGULAR_GIT_MODES = {"100644": 0o644, "100755": 0o755}
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


def _forbidden_name(name: str) -> bool:
    return name in FORBIDDEN_NAMES or name.startswith(".env.")


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


def _validate_repository_root(root: Path) -> None:
    if not root.is_dir():
        raise ReleaseBuildError(f"repository root is not a directory: {root}")
    top_level = Path(
        _git(root, "rev-parse", "--show-toplevel").decode("utf-8", errors="strict").strip()
    ).resolve()
    if top_level != root:
        raise ReleaseBuildError(f"--root must be the Git repository root: {top_level}")


def tracked_files(root: Path) -> list[TrackedFile]:
    """Return safe regular files from the Git index in deterministic order."""

    _validate_repository_root(root)
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
    tracked_changes = _git(root, "status", "--porcelain=v1", "--untracked-files=no")
    if tracked_changes:
        preview = tracked_changes.decode("utf-8", errors="replace").strip().splitlines()[:10]
        raise ReleaseBuildError(
            "tracked source and index must match HEAD before a release build: "
            + ", ".join(preview)
        )
    output = _git(root, "ls-files", "--cached", "--stage", "-z")
    files: list[TrackedFile] = []
    for record in output.split(b"\0"):
        if not record:
            continue
        try:
            metadata, raw_path = record.split(b"\t", maxsplit=1)
            mode, _object_id, stage = metadata.split(maxsplit=2)
            relative_text = raw_path.decode("utf-8", errors="strict")
        except (UnicodeDecodeError, ValueError) as exc:
            raise ReleaseBuildError("could not parse a Git index entry") from exc
        if stage != b"0":
            raise ReleaseBuildError(f"unmerged Git index entry: {relative_text}")

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
        if _forbidden_name(relative.name) or relative.suffix in FORBIDDEN_SUFFIXES:
            raise ReleaseBuildError(f"forbidden tracked release file: {relative_text}")

        mode_text = mode.decode("ascii", errors="strict")
        if mode_text not in REGULAR_GIT_MODES:
            kind = {
                "120000": "symbolic link",
                "160000": "Git submodule",
            }.get(mode_text, f"unsupported mode {mode_text}")
            raise ReleaseBuildError(
                f"tracked {kind} is not allowed in a release ZIP: {relative_text}"
            )

        source = root.joinpath(*relative.parts)
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
            raise ReleaseBuildError(
                f"tracked path escapes the repository: {relative_text}"
            ) from exc

        files.append(
            TrackedFile(relative=relative, permissions=REGULAR_GIT_MODES[mode_text])
        )

    if not files:
        raise ReleaseBuildError("Git index contains no files")
    return sorted(files, key=lambda item: item.relative.as_posix().encode("utf-8"))


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
                source = root.joinpath(*tracked.relative.parts)
                archive_name = (
                    PurePosixPath(ARCHIVE_ROOT) / tracked.relative
                ).as_posix()
                info = zipfile.ZipInfo(archive_name, ZIP_TIMESTAMP)
                info.create_system = 3
                info.compress_type = zipfile.ZIP_STORED
                info.external_attr = (stat.S_IFREG | tracked.permissions) << 16
                info.flag_bits |= 0x800  # UTF-8 file names.
                archive.writestr(info, source.read_bytes())
        os.replace(temporary, output)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", default="dist/voicemd-agent-standard.zip")
    args = parser.parse_args()

    try:
        output = build_release(Path(args.root), Path(args.output))
    except ReleaseBuildError as exc:
        parser.error(str(exc))
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
