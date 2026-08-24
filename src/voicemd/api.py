from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from .compiler import compile_contract
from .contract import (
    DEFAULT_MAX_SOURCE_COUNT,
    DEFAULT_MAX_SOURCE_FILE_BYTES,
    DEFAULT_MAX_TOTAL_SOURCE_BYTES,
    DEFAULT_MAX_YAML_ALIASES,
    DEFAULT_MAX_YAML_NODES,
    ContractError,
    load_contract,
)
from .discovery import discover_paths
from .linter import LintIssue, lint_text
from .model import ResolvedVoiceContract
from .validator import validate_selected_contract


def discover_voice(
    start: str | Path | None = None,
    *,
    path: str | Path | Iterable[str | Path] | None = None,
    include_global: bool = True,
) -> list[Path]:
    return discover_paths(start=start, explicit=path, include_global=include_global)


def load_voice(
    start: str | Path | None = None,
    *,
    path: str | Path | list[str | Path] | None = None,
    include_global: bool = True,
    allowed_source_root: str | Path | None = None,
    max_source_file_bytes: int = DEFAULT_MAX_SOURCE_FILE_BYTES,
    max_total_source_bytes: int = DEFAULT_MAX_TOTAL_SOURCE_BYTES,
    max_source_count: int = DEFAULT_MAX_SOURCE_COUNT,
    max_yaml_nodes: int = DEFAULT_MAX_YAML_NODES,
    max_yaml_aliases: int = DEFAULT_MAX_YAML_ALIASES,
) -> ResolvedVoiceContract:
    return load_contract(
        start=start,
        explicit=path,
        include_global=include_global,
        allowed_source_root=allowed_source_root,
        max_source_file_bytes=max_source_file_bytes,
        max_total_source_bytes=max_total_source_bytes,
        max_source_count=max_source_count,
        max_yaml_nodes=max_yaml_nodes,
        max_yaml_aliases=max_yaml_aliases,
    )


def require_valid_voice(
    contract: ResolvedVoiceContract,
    *,
    profile: str | None = None,
    audience: str | None = None,
    surface: str | None = None,
    tone: str | None = None,
) -> ResolvedVoiceContract:
    """Fail closed unless the exact runtime-selected contract is conforming."""

    result = validate_selected_contract(
        contract,
        profile=profile,
        audience=audience,
        surface=surface,
        tone=tone,
        strict=False,
    )
    if not result.ok:
        raise ContractError("selected VOICE.md failed validation")
    return contract


def compile_voice(
    contract: ResolvedVoiceContract | None = None,
    *,
    start: str | Path | None = None,
    path: str | Path | list[str | Path] | None = None,
    profile: str | None = None,
    audience: str | None = None,
    surface: str | None = None,
    tone: str | None = None,
    output_format: str = "prompt",
    compact: bool = False,
    max_chars: int | None = None,
    include_global: bool = True,
) -> str:
    active = contract or load_voice(start=start, path=path, include_global=include_global)
    require_valid_voice(
        active,
        profile=profile,
        audience=audience,
        surface=surface,
        tone=tone,
    )
    return compile_contract(
        active,
        profile=profile,
        audience=audience,
        surface=surface,
        tone=tone,
        output_format=output_format,
        compact=compact,
        max_chars=max_chars,
    )


def lint_voice_text(
    text: str,
    contract: ResolvedVoiceContract | None = None,
    *,
    start: str | Path | None = None,
    path: str | Path | list[str | Path] | None = None,
    profile: str | None = None,
    audience: str | None = None,
    surface: str | None = None,
    tone: str | None = None,
    include_global: bool = True,
) -> list[LintIssue]:
    active = contract or load_voice(start=start, path=path, include_global=include_global)
    require_valid_voice(
        active,
        profile=profile,
        audience=audience,
        surface=surface,
        tone=tone,
    )
    return lint_text(
        active,
        text,
        profile=profile,
        audience=audience,
        surface=surface,
        tone=tone,
    )
