from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .constants import (
    DEFAULT_FILENAMES,
    EXPLICIT_PATH_ENV,
    GLOBAL_HOME_ENV,
    PROJECT_ROOT_ENV,
)
from .discovery import FALLBACK_ROOT_MARKERS, ROOT_MARKERS, discover_paths, find_project_root
from .frontmatter import FrontmatterError, parse_bytes
from .merge import deep_merge
from .model import ResolvedVoiceContract, SourceDocument
from .normalization import (
    NormalizationError,
    deprecated_language_alias_paths,
    normalize_contract_data,
)


class ContractError(ValueError):
    pass


DEFAULT_MAX_SOURCE_FILE_BYTES = 1_048_576
DEFAULT_MAX_TOTAL_SOURCE_BYTES = 4_194_304
DEFAULT_MAX_SOURCE_COUNT = 64
DEFAULT_MAX_YAML_NODES = 20_000
DEFAULT_MAX_YAML_ALIASES = 100


@dataclass
class _LoadBudget:
    max_file_bytes: int
    max_total_bytes: int
    max_sources: int
    total_bytes: int = 0
    source_count: int = 0

    def read(self, path: Path) -> bytes:
        if self.source_count >= self.max_sources:
            raise ContractError(f"Maximum source count ({self.max_sources}) exceeded at {path}")
        try:
            with path.open("rb") as source_file:
                raw = source_file.read(self.max_file_bytes + 1)
        except OSError as exc:
            raise ContractError(f"Unable to read VOICE.md source: {path}") from exc
        if len(raw) > self.max_file_bytes:
            raise ContractError(
                f"VOICE.md source exceeds file byte limit ({self.max_file_bytes}): {path}"
            )
        next_total = self.total_bytes + len(raw)
        if next_total > self.max_total_bytes:
            raise ContractError(
                f"VOICE.md sources exceed aggregate byte limit ({self.max_total_bytes}) at {path}"
            )
        self.source_count += 1
        self.total_bytes = next_total
        return raw


def _positive_limit(value: int, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ContractError(f"{name} must be a positive integer")
    return value


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


def _resolve_root(root: Path | str) -> Path:
    candidate = Path(root).expanduser()
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ContractError(f"Allowed source root cannot be resolved: {candidate}") from exc
    if not resolved.is_dir():
        raise ContractError(f"Allowed source root is not a directory: {resolved}")
    return resolved


def _default_explicit_root(path: Path) -> Path:
    configured = os.environ.get(PROJECT_ROOT_ENV)
    if configured:
        return _resolve_root(configured)

    candidate = path.expanduser()
    lexical = Path(os.path.abspath(candidate))
    parent = lexical.parent
    chain = (parent, *parent.parents)
    for directory in chain:
        if any((directory / marker).exists() for marker in ROOT_MARKERS):
            return _resolve_root(directory)
    for directory in chain:
        if any((directory / marker).is_file() for marker in FALLBACK_ROOT_MARKERS):
            return _resolve_root(directory)
    return _resolve_root(parent)


def _resolve_source(path: Path, *, allowed_root: Path) -> Path:
    candidate = path.expanduser()
    if _contains_secret_env_component(candidate):
        raise ContractError(f"Secret environment files cannot be VOICE.md sources: {candidate}")
    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ContractError(f"VOICE.md source does not exist: {candidate}") from exc
    except (OSError, RuntimeError, ValueError) as exc:
        raise ContractError(f"VOICE.md source cannot be resolved safely: {candidate}") from exc
    if _contains_secret_env_component(resolved):
        raise ContractError(f"Secret environment files cannot be VOICE.md sources: {resolved}")
    if not _is_within(resolved, allowed_root):
        raise ContractError(
            f"VOICE.md source is outside allowed source root {allowed_root}: {resolved}"
        )
    if not resolved.is_file():
        raise ContractError(f"VOICE.md source is not a regular file: {resolved}")
    return resolved


def _absolute_lexical_path(path: Path) -> Path:
    return Path(os.path.abspath(path.expanduser()))


def _normalize_extends(value: Any, *, path: Path) -> list[Path]:
    if value is None:
        return []
    values = [value] if isinstance(value, str) else value
    if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
        raise ContractError(f"{path}: 'extends' must be a string or a list of strings")
    result: list[Path] = []
    for item in values:
        if item.lower().startswith(("http://", "https://")):
            raise ContractError(
                f"{path}: remote extends are disabled by the core specification; vendor or pin the file locally"
            )
        result.append((path.parent / item).expanduser())
    return result


def _load_recursive(
    path: Path,
    *,
    level: int,
    via: str,
    stack: tuple[Path, ...],
    seen: set[Path],
    max_depth: int,
    allowed_root: Path,
    budget: _LoadBudget,
    max_yaml_nodes: int,
    max_yaml_aliases: int,
    dependency_edges: set[Path],
) -> list[SourceDocument]:
    dependency_edges.add(_absolute_lexical_path(path))
    path = _resolve_source(path, allowed_root=allowed_root)
    if path in stack:
        cycle = " -> ".join(map(str, (*stack, path)))
        raise ContractError(f"VOICE.md extends cycle detected: {cycle}")
    if path in seen:
        return []
    if len(stack) > max_depth:
        raise ContractError(f"Maximum extends depth ({max_depth} hops) exceeded at {path}")
    try:
        metadata, body = parse_bytes(
            budget.read(path),
            source=str(path),
            max_yaml_nodes=max_yaml_nodes,
            max_yaml_aliases=max_yaml_aliases,
        )
    except FrontmatterError as exc:
        raise ContractError(str(exc)) from exc

    documents: list[SourceDocument] = []
    for extended in _normalize_extends(metadata.get("extends"), path=path):
        documents.extend(
            _load_recursive(
                extended,
                level=level - 1,
                via=f"extends:{path.name}",
                stack=(*stack, path),
                seen=seen,
                max_depth=max_depth,
                allowed_root=allowed_root,
                budget=budget,
                max_yaml_nodes=max_yaml_nodes,
                max_yaml_aliases=max_yaml_aliases,
                dependency_edges=dependency_edges,
            )
        )

    if path not in seen:
        documents.append(
            SourceDocument(path=path, metadata=metadata, body=body, level=level, via=via)
        )
        seen.add(path)
    return documents


def load_contract(
    paths: list[Path] | None = None,
    *,
    start: Path | str | None = None,
    explicit: Path | str | list[Path | str] | None = None,
    include_global: bool = True,
    max_extends_depth: int = 8,
    allowed_source_root: Path | str | None = None,
    max_source_file_bytes: int = DEFAULT_MAX_SOURCE_FILE_BYTES,
    max_total_source_bytes: int = DEFAULT_MAX_TOTAL_SOURCE_BYTES,
    max_source_count: int = DEFAULT_MAX_SOURCE_COUNT,
    max_yaml_nodes: int = DEFAULT_MAX_YAML_NODES,
    max_yaml_aliases: int = DEFAULT_MAX_YAML_ALIASES,
) -> ResolvedVoiceContract:
    if (
        isinstance(max_extends_depth, bool)
        or not isinstance(max_extends_depth, int)
        or max_extends_depth < 0
    ):
        raise ContractError("max_extends_depth must be a non-negative integer")
    max_source_file_bytes = _positive_limit(
        max_source_file_bytes, name="max_source_file_bytes"
    )
    max_total_source_bytes = _positive_limit(
        max_total_source_bytes, name="max_total_source_bytes"
    )
    max_source_count = _positive_limit(max_source_count, name="max_source_count")
    max_yaml_nodes = _positive_limit(max_yaml_nodes, name="max_yaml_nodes")
    max_yaml_aliases = _positive_limit(max_yaml_aliases, name="max_yaml_aliases")
    env_paths = os.environ.get(EXPLICIT_PATH_ENV)
    if paths:
        active_paths = list(paths)
    elif explicit is not None:
        active_paths = [explicit] if isinstance(explicit, (str, Path)) else list(explicit)
    elif env_paths:
        active_paths = [
            Path(value.strip()) for value in env_paths.split(os.pathsep) if value.strip()
        ]
    else:
        active_paths = discover_paths(start=start, include_global=include_global)
    if not active_paths:
        raise ContractError(
            "No VOICE.md found. Run 'voicemd init' or pass --path /path/to/VOICE.md."
        )

    documents: list[SourceDocument] = []
    seen: set[Path] = set()
    dependency_edges: set[Path] = set()
    budget = _LoadBudget(
        max_file_bytes=max_source_file_bytes,
        max_total_bytes=max_total_source_bytes,
        max_sources=max_source_count,
    )
    fixed_root = _resolve_root(allowed_source_root) if allowed_source_root is not None else None

    automatic_discovery = not paths and explicit is None and not env_paths
    project_root: Path | None = None
    global_root: Path | None = None
    global_source: Path | None = None
    if fixed_root is None and automatic_discovery:
        project_root = _resolve_root(find_project_root(Path(start or Path.cwd())))
        if include_global:
            global_home = Path(
                os.environ.get(GLOBAL_HOME_ENV, "~/.config/voicemd")
            ).expanduser()
            if global_home.is_dir():
                global_root = _resolve_root(global_home)
                for filename in DEFAULT_FILENAMES:
                    candidate = global_home / filename
                    if candidate.is_file():
                        try:
                            global_source = candidate.resolve(strict=True)
                        except (OSError, RuntimeError, ValueError):
                            global_source = None
                        break

    for index, path in enumerate(active_paths):
        source_path = Path(path).expanduser()
        if fixed_root is not None:
            source_root = fixed_root
        elif automatic_discovery:
            try:
                resolved_hint = source_path.resolve(strict=True)
            except (OSError, RuntimeError, ValueError):
                resolved_hint = source_path
            source_root = (
                global_root
                if global_root is not None and resolved_hint == global_source
                else project_root
            )
            if source_root is None:  # pragma: no cover - project roots always resolve above
                raise ContractError("Unable to determine the allowed source root")
        else:
            source_root = _default_explicit_root(source_path)
        documents.extend(
            _load_recursive(
                source_path,
                level=index * 100,
                via="discovery",
                stack=(),
                seen=seen,
                max_depth=max_extends_depth,
                allowed_root=source_root,
                budget=budget,
                max_yaml_nodes=max_yaml_nodes,
                max_yaml_aliases=max_yaml_aliases,
                dependency_edges=dependency_edges,
            )
        )

    data: dict[str, Any] = {}
    bodies: list[tuple[Path, str]] = []
    warnings: list[str] = []
    for document in documents:
        metadata = {key: value for key, value in document.metadata.items() if key != "extends"}
        data = deep_merge(data, metadata)
        body = document.body.strip(" \t\n\r")
        if body:
            bodies.append((document.path, body))

    deprecated_aliases = deprecated_language_alias_paths(data)
    if deprecated_aliases:
        warnings.append("default_language is deprecated; use language.default")
    try:
        data = normalize_contract_data(data, normalize_dormant_aliases=False)
    except NormalizationError as exc:
        raise ContractError(str(exc)) from exc

    if not data:
        warnings.append("Plain Markdown mode: no structured YAML frontmatter is active.")
    return ResolvedVoiceContract(
        data=data,
        bodies=bodies,
        sources=documents,
        dependency_edges=sorted(dependency_edges, key=lambda item: str(item).encode("utf-8")),
        warnings=warnings,
    )
