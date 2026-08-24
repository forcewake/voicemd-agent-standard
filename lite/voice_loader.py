"""Dependency-free VOICE.md loader for plain Markdown use."""

from __future__ import annotations

import os
from pathlib import Path

CANDIDATES = (
    "VOICE.override.md",
    "VOICE.md",
    ".voice/VOICE.override.md",
    ".voice/VOICE.md",
)
ROOT_MARKERS = (".voicemd-root", ".git", ".hg", ".svn")
FALLBACK_ROOT_MARKERS = ("pyproject.toml", "package.json", "go.mod", "Cargo.toml")
MACHINE_OUTPUTS = {
    "code", "patch", "diff", "json", "xml", "yaml", "sql",
    "tool_call", "tool_result", "structured_data", "exact_quote", "raw_data",
}


def _directory(start: str | Path) -> Path:
    value = Path(start).expanduser().resolve()
    return value.parent if value.is_file() else value


def project_root(start: str | Path) -> Path:
    current = _directory(start)
    configured = os.environ.get("VOICE_MD_ROOT")
    if configured:
        root = Path(configured).expanduser().resolve()
        if not root.is_dir() or (root != current and root not in current.parents):
            raise ValueError("VOICE_MD_ROOT must be a directory containing the start path")
        return root
    chain = (current, *current.parents)
    for directory in chain:
        if any((directory / marker).exists() for marker in ROOT_MARKERS):
            return directory
    for directory in chain:
        if any((directory / marker).is_file() for marker in FALLBACK_ROOT_MARKERS):
            return directory
    return current


def discover(start: str | Path = ".") -> list[Path]:
    cwd = _directory(start)
    root = project_root(cwd)
    chain: list[Path] = []
    current = cwd
    while True:
        chain.append(current)
        if current == root:
            break
        if current.parent == current or root not in current.parents:
            break
        current = current.parent
    result: list[Path] = []
    for directory in reversed(chain):
        for name in CANDIDATES:
            candidate = directory / name
            if candidate.is_file() and candidate.stat().st_size:
                result.append(candidate.resolve())
                break
    return result


def load_voice(start: str | Path = ".") -> str:
    paths = discover(start)
    if not paths:
        raise FileNotFoundError("No VOICE.md found")
    return "\n\n".join(path.read_text(encoding="utf-8").strip() for path in paths)


def should_apply(output_kind: str, *, exact_output: bool = False, enabled: bool = True) -> bool:
    return enabled and not exact_output and output_kind not in MACHINE_OUTPUTS
