"""Provider-neutral activation and prompt-composition example."""

from __future__ import annotations

from dataclasses import dataclass

from voicemd import compile_voice

MACHINE_OUTPUTS = {
    "code",
    "patch",
    "diff",
    "json",
    "xml",
    "yaml",
    "sql",
    "tool_call",
    "tool_result",
    "structured_data",
    "exact_quote",
    "raw_data",
}


@dataclass(frozen=True)
class OutputContext:
    output_kind: str = "chat"
    surface: str | None = "chat"
    audience: str | None = None
    tone: str | None = None
    profile: str | None = None
    voice_enabled: bool = True
    exact_output: bool = False


def compose_system_messages(base_system_prompt: str, context: OutputContext) -> list[dict[str, str]]:
    messages = [{"role": "system", "content": base_system_prompt}]
    if (
        not context.voice_enabled
        or context.exact_output
        or context.output_kind in MACHINE_OUTPUTS
    ):
        return messages

    voice_prompt = compile_voice(
        path="VOICE.md",
        profile=context.profile,
        audience=context.audience,
        surface=context.surface,
        tone=context.tone,
        compact=False,
    )
    messages.append({"role": "system", "content": voice_prompt})
    return messages
