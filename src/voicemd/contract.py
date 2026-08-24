from __future__ import annotations

from pathlib import Path
from typing import Any

from .discovery import discover_paths
from .frontmatter import FrontmatterError, parse_file
from .merge import deep_merge
from .model import ResolvedVoiceContract, SourceDocument


class ContractError(ValueError):
    pass


def _normalize_extends(value: Any, *, path: Path) -> list[Path]:
    if value is None:
        return []
    values = [value] if isinstance(value, str) else value
    if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
        raise ContractError(f"{path}: 'extends' must be a string or a list of strings")
    result: list[Path] = []
    for item in values:
        if item.startswith(("http://", "https://")):
            raise ContractError(
                f"{path}: remote extends are disabled by the core specification; vendor or pin the file locally"
            )
        result.append((path.parent / item).expanduser().resolve())
    return result


def _load_recursive(
    path: Path,
    *,
    level: int,
    via: str,
    stack: tuple[Path, ...],
    seen: set[Path],
    max_depth: int,
) -> list[SourceDocument]:
    path = path.resolve()
    if len(stack) >= max_depth:
        raise ContractError(f"Maximum extends depth ({max_depth}) exceeded at {path}")
    if path in stack:
        cycle = " -> ".join(map(str, (*stack, path)))
        raise ContractError(f"VOICE.md extends cycle detected: {cycle}")
    if not path.is_file():
        raise ContractError(f"VOICE.md source does not exist: {path}")

    try:
        metadata, body = parse_file(path)
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
) -> ResolvedVoiceContract:
    active_paths = paths or discover_paths(
        start=start, explicit=explicit, include_global=include_global
    )
    if not active_paths:
        raise ContractError(
            "No VOICE.md found. Run 'voicemd init' or pass --path /path/to/VOICE.md."
        )

    documents: list[SourceDocument] = []
    seen: set[Path] = set()
    for index, path in enumerate(active_paths):
        documents.extend(
            _load_recursive(
                Path(path),
                level=index * 100,
                via="discovery",
                stack=(),
                seen=seen,
                max_depth=max_extends_depth,
            )
        )

    data: dict[str, Any] = {}
    bodies: list[tuple[Path, str]] = []
    warnings: list[str] = []
    for document in documents:
        metadata = {key: value for key, value in document.metadata.items() if key != "extends"}
        data = deep_merge(data, metadata)
        if document.body.strip():
            bodies.append((document.path, document.body.strip()))

    if not data:
        warnings.append("Plain Markdown mode: no structured YAML frontmatter is active.")
    return ResolvedVoiceContract(data=data, bodies=bodies, sources=documents, warnings=warnings)
