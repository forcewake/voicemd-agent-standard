"""Provider-neutral activation and prompt-composition example."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from voicemd import compile_voice, decide_activation, load_voice
from voicemd.model import ResolvedVoiceContract


@dataclass(frozen=True)
class OutputContext:
    output_kind: str = "chat"
    surface: str | None = None
    audience: str | None = None
    tone: str | None = None
    profile: str | None = None
    voice_enabled: bool = True
    voice_explicit: bool = False
    marker_text: str | None = None
    exact_output: bool = False


def compose_system_messages(
    base_system_prompt: str,
    context: OutputContext,
    *,
    contract: ResolvedVoiceContract | None = None,
    start: str | Path | None = None,
    path: str | Path | Iterable[str | Path] | None = None,
    include_global: bool = True,
) -> list[dict[str, str]]:
    messages = [{"role": "system", "content": base_system_prompt}]
    if not context.voice_enabled or context.exact_output:
        return messages

    active = contract or load_voice(
        start=start,
        path=list(path) if path is not None and not isinstance(path, (str, Path)) else path,
        include_global=include_global,
    )
    decision = decide_activation(
        active,
        context.output_kind,
        exact_output=context.exact_output,
        enabled=context.voice_enabled,
        explicit=context.voice_explicit,
        marker_text=context.marker_text,
        profile=context.profile,
        audience=context.audience,
        surface=context.surface,
        tone=context.tone,
    )
    if not decision.apply:
        return messages

    voice_prompt = compile_voice(
        active,
        profile=context.profile,
        audience=context.audience,
        surface=context.surface,
        tone=context.tone,
        compact=False,
    )
    messages.append({"role": "system", "content": voice_prompt})
    return messages
