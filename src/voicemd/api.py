from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .compiler import compile_contract
from .contract import load_contract
from .discovery import discover_paths
from .linter import LintIssue, lint_text
from .model import ResolvedVoiceContract


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
) -> ResolvedVoiceContract:
    return load_contract(start=start, explicit=path, include_global=include_global)


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
    return lint_text(
        active,
        text,
        profile=profile,
        audience=audience,
        surface=surface,
        tone=tone,
    )
