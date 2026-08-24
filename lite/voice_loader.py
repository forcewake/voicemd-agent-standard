"""Dependency-free VOICE.md loader for plain Markdown use."""

from __future__ import annotations

import os
import sys
from pathlib import Path

CANDIDATES = (
    "VOICE.override.md",
    "VOICE.md",
    ".voice/VOICE.override.md",
    ".voice/VOICE.md",
)
ROOT_MARKERS = (".voicemd-root", ".git", ".hg", ".svn")
FALLBACK_ROOT_MARKERS = ("pyproject.toml", "package.json", "go.mod", "Cargo.toml")
VOICE_TRIM_CHARS = " \t\n\r"
MACHINE_OUTPUTS = {
    "code", "patch", "diff", "json", "xml", "yaml", "sql",
    "tool_call", "tool_result", "structured_data", "exact_quote", "raw_data",
}
HUMAN_OUTPUTS = {
    "chat", "message", "email", "document", "report", "summary",
    "explanation", "ui_copy", "spoken", "speech",
}


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _contains_secret_env_component(path: Path) -> bool:
    return any(
        part.casefold() == ".env" or part.casefold().startswith(".env.")
        for part in path.parts
    )


def _lexical_directory(start: str | Path) -> Path:
    """Return the lexical start directory without following its symlinks."""
    value = Path(os.path.abspath(Path(start).expanduser()))
    try:
        resolved = value.resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError(f"Discovery start cannot be resolved safely: {value}") from exc
    if resolved.is_file():
        return value.parent
    if not resolved.is_dir():
        raise ValueError(f"Discovery start is not a file or directory: {value}")
    return value


def _resolve_directory(path: Path, *, label: str) -> Path:
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError(f"{label} cannot be resolved safely: {path}") from exc
    if not resolved.is_dir():
        raise ValueError(f"{label} is not a directory: {resolved}")
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


def _marker_root(chain: tuple[Path, ...] | list[Path]) -> Path | None:
    for directory in chain:
        if any((directory / marker).exists() for marker in ROOT_MARKERS):
            return directory
    for directory in chain:
        if any((directory / marker).is_file() for marker in FALLBACK_ROOT_MARKERS):
            return directory
    return None


def _discovery_context(start: str | Path) -> tuple[Path, Path]:
    lexical_current = _lexical_directory(start)
    current = _resolve_directory(lexical_current, label="Discovery start")

    configured = os.environ.get("VOICE_MD_ROOT")
    if configured:
        root = _resolve_directory(
            Path(configured).expanduser(), label="VOICE_MD_ROOT"
        )
        if not _is_within(current, root):
            raise ValueError("VOICE_MD_ROOT must contain the discovery start directory")
        return current, root

    lexical_chain = (lexical_current, *lexical_current.parents)
    symlinks = _symlink_components(lexical_current)
    protective_chain: list[Path] = []
    if symlinks:
        # A marker reached below the deepest symlink cannot redefine a broader
        # lexical project boundary. An ambient prefix symlink such as
        # /tmp -> /private/tmp remains valid when no broader marker exists.
        symlink_parent = symlinks[-1].parent
        protective_chain = [
            directory
            for directory in lexical_chain
            if directory == symlink_parent or directory in symlink_parent.parents
        ]
    lexical_root = _marker_root(protective_chain) or _marker_root(lexical_chain)
    if lexical_root is not None:
        root = _resolve_directory(lexical_root, label="Project root")
        if not _is_within(current, root):
            raise ValueError(
                f"Discovery start is outside canonical project root {root}: {current}"
            )
        return current, root

    canonical_chain = (current, *current.parents)
    canonical_root = _marker_root(canonical_chain) or current
    root = _resolve_directory(canonical_root, label="Project root")
    return current, root


def project_root(start: str | Path) -> Path:
    return _discovery_context(start)[1]


def _resolve_candidate(candidate: Path, *, root: Path) -> Path | None:
    if _contains_secret_env_component(candidate):
        raise ValueError(f"Secret environment files cannot be VOICE.md sources: {candidate}")
    parent = candidate.parent
    if parent != candidate and parent != root and not parent.exists():
        if parent.is_symlink():
            raise ValueError(f"VOICE.md candidate parent cannot be resolved: {parent}")
        return None
    if parent != candidate:
        resolved_parent = _resolve_directory(parent, label="VOICE.md candidate parent")
        if not _is_within(resolved_parent, root):
            raise ValueError(
                f"VOICE.md candidate parent is outside canonical project root {root}: "
                f"{resolved_parent}"
            )

    exists_lexically = candidate.exists() or candidate.is_symlink()
    if not exists_lexically:
        return None
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError(f"VOICE.md candidate cannot be resolved safely: {candidate}") from exc
    if _contains_secret_env_component(resolved):
        raise ValueError(f"Secret environment files cannot be VOICE.md sources: {resolved}")
    if not _is_within(resolved, root):
        raise ValueError(
            f"VOICE.md candidate is outside canonical project root {root}: {resolved}"
        )
    if not resolved.is_file():
        if candidate.is_symlink():
            raise ValueError(f"VOICE.md symlink does not resolve to a regular file: {candidate}")
        return None
    return resolved


def discover(start: str | Path = ".") -> list[Path]:
    cwd, root = _discovery_context(start)
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
            candidate = _resolve_candidate(directory / name, root=root)
            if candidate is not None:
                result.append(candidate)
                break
    return result


def load_voice(start: str | Path = ".") -> str:
    paths = discover(start)
    if not paths:
        raise FileNotFoundError("No VOICE.md found")
    return "\n\n".join(
        path.read_text(encoding="utf-8").strip(VOICE_TRIM_CHARS) for path in paths
    )


def should_apply(output_kind: str, *, exact_output: bool = False, enabled: bool = True) -> bool:
    kind = output_kind.strip().casefold()
    return enabled and not exact_output and kind in HUMAN_OUTPUTS and kind not in MACHINE_OUTPUTS


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) > 1:
        print("usage: python voice_loader.py [START]", file=sys.stderr)
        return 2
    try:
        print(load_voice(args[0] if args else "."))
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
