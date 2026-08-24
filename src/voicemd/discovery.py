from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path

from .constants import (
    DEFAULT_FILENAMES,
    EXPLICIT_PATH_ENV,
    GLOBAL_HOME_ENV,
    PROJECT_ROOT_ENV,
)


class DiscoveryError(FileNotFoundError):
    pass


ROOT_MARKERS = (".voicemd-root", ".git", ".hg", ".svn")
FALLBACK_ROOT_MARKERS = ("pyproject.toml", "package.json", "go.mod", "Cargo.toml")


def _lexical_directory(start: Path) -> Path:
    """Return an absolute discovery directory without following directory symlinks."""

    current = Path(os.path.abspath(start.expanduser()))
    if current.is_file():
        current = current.parent
    return current


def _resolved_directory(path: Path, *, label: str) -> Path:
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise DiscoveryError(f"{label} cannot be resolved safely: {path}") from exc
    if not resolved.is_dir():
        raise DiscoveryError(f"{label} is not a directory: {resolved}")
    return resolved


def _symlink_components(path: Path) -> list[Path]:
    """Return lexical symlink components without following later components."""

    result: list[Path] = []
    cursor = Path(path.anchor)
    for part in path.parts[1:]:
        cursor /= part
        if cursor.is_symlink():
            result.append(cursor)
    return result


def _marker_root(chain: Iterable[Path]) -> Path | None:
    directories = tuple(chain)
    for directory in directories:
        if any((directory / marker).exists() for marker in ROOT_MARKERS):
            return directory
    for directory in directories:
        if any((directory / marker).is_file() for marker in FALLBACK_ROOT_MARKERS):
            return directory
    return None


def find_project_root(start: Path) -> Path:
    """Find the nearest explicit VCS/VoiceMD root, then a common project marker.

    `VOICE_MD_ROOT` is authoritative when set. `.voicemd-root` provides a
    provider-neutral root marker for source archives and non-Git deployments.
    """
    lexical_current = _lexical_directory(start)
    resolved_current = _resolved_directory(lexical_current, label="Discovery start")

    configured = os.environ.get(PROJECT_ROOT_ENV)
    if configured:
        root = _resolved_directory(
            Path(configured).expanduser(), label=PROJECT_ROOT_ENV
        )
        if root != resolved_current and root not in resolved_current.parents:
            raise DiscoveryError(
                f"{PROJECT_ROOT_ENV} must contain the discovery start directory: {root}"
            )
        return root

    chain = (lexical_current, *lexical_current.parents)
    symlinks = _symlink_components(lexical_current)
    protective_chain: list[Path] = []
    if symlinks:
        # A marker visible only through a symlink target cannot redefine the
        # lexical project boundary. Ambient prefix symlinks remain usable when
        # no marker exists at or above the deepest symlink's parent.
        symlink_parent = symlinks[-1].parent
        protective_chain = [
            directory
            for directory in chain
            if directory == symlink_parent or directory in symlink_parent.parents
        ]
    lexical_root = _marker_root(protective_chain) or _marker_root(chain) or lexical_current

    root = _resolved_directory(lexical_root, label="Project root")
    if root != resolved_current and root not in resolved_current.parents:
        raise DiscoveryError(
            "Discovery start resolves outside its lexical project root; "
            f"refusing symlink escape from {lexical_root} to {resolved_current}"
        )
    return root


def _first_candidate(directory: Path) -> Path | None:
    for name in DEFAULT_FILENAMES:
        candidate = directory / name
        if candidate.is_file():
            return candidate.resolve()
    return None


def _parse_explicit_paths(raw: str) -> list[Path]:
    values = [value.strip() for value in raw.split(os.pathsep) if value.strip()]
    return [Path(value).expanduser().resolve() for value in values]


def discover_paths(
    start: Path | str | None = None,
    *,
    explicit: Path | str | Iterable[Path | str] | None = None,
    include_global: bool = True,
) -> list[Path]:
    """Return active VOICE.md sources in broad-to-specific precedence order."""
    lexical_cwd = _lexical_directory(Path(start or Path.cwd()))

    if explicit is not None:
        values = [explicit] if isinstance(explicit, (str, Path)) else list(explicit)
        paths = [Path(value).expanduser().resolve() for value in values]
        missing = [path for path in paths if not path.is_file()]
        if missing:
            raise DiscoveryError("Explicit VOICE.md path not found: " + ", ".join(map(str, missing)))
        return paths

    env_value = os.environ.get(EXPLICIT_PATH_ENV)
    if env_value:
        paths = _parse_explicit_paths(env_value)
        missing = [path for path in paths if not path.is_file()]
        if missing:
            raise DiscoveryError(f"{EXPLICIT_PATH_ENV} points to missing file(s): {missing}")
        return paths

    result: list[Path] = []
    if include_global:
        global_home = Path(
            os.environ.get(GLOBAL_HOME_ENV, "~/.config/voicemd")
        ).expanduser().resolve()
        global_candidate = _first_candidate(global_home)
        if global_candidate:
            result.append(global_candidate)

    root = find_project_root(lexical_cwd)
    cwd = _resolved_directory(lexical_cwd, label="Discovery start")
    chain: list[Path] = []
    current = cwd
    while True:
        chain.append(current)
        if current == root:
            break
        if current.parent == current or root not in current.parents:
            break
        current = current.parent

    for directory in reversed(chain):
        candidate = _first_candidate(directory)
        if candidate and candidate not in result:
            result.append(candidate)
    return result
