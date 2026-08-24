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


def find_project_root(start: Path) -> Path:
    """Find the nearest explicit VCS/VoiceMD root, then a common project marker.

    `VOICE_MD_ROOT` is authoritative when set. `.voicemd-root` provides a
    provider-neutral root marker for source archives and non-Git deployments.
    """
    current = start.expanduser().resolve()
    if current.is_file():
        current = current.parent

    configured = os.environ.get(PROJECT_ROOT_ENV)
    if configured:
        root = Path(configured).expanduser().resolve()
        if not root.is_dir():
            raise DiscoveryError(f"{PROJECT_ROOT_ENV} is not a directory: {root}")
        if root != current and root not in current.parents:
            raise DiscoveryError(
                f"{PROJECT_ROOT_ENV} must contain the discovery start directory: {root}"
            )
        return root

    chain = (current, *current.parents)
    for directory in chain:
        if any((directory / marker).exists() for marker in ROOT_MARKERS):
            return directory
    for directory in chain:
        if any((directory / marker).is_file() for marker in FALLBACK_ROOT_MARKERS):
            return directory
    return current


def _first_candidate(directory: Path) -> Path | None:
    for name in DEFAULT_FILENAMES:
        candidate = directory / name
        if candidate.is_file() and candidate.stat().st_size > 0:
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
    cwd = Path(start or Path.cwd()).expanduser().resolve()
    if cwd.is_file():
        cwd = cwd.parent

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

    root = find_project_root(cwd)
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
