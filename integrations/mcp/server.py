#!/usr/bin/env python3
"""Optional MCP adapter. Requires: pip install 'voicemd[mcp]'."""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from voicemd import compile_voice, lint_voice_text, load_voice

mcp = FastMCP("voicemd")


@mcp.resource("voice://active")
def active_contract() -> str:
    contract = load_voice()
    return json.dumps(
        {
            "contract": contract.data,
            "body": contract.body,
            "sources": [str(path) for path in contract.source_paths()],
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
def compile_voice_contract(
    profile: str | None = None,
    audience: str | None = None,
    surface: str | None = None,
    tone: str | None = None,
    compact: bool = False,
    ascii_only: bool = False,
) -> str:
    """Compile the active VOICE.md for a human-facing output context."""
    return compile_voice(
        profile=profile,
        audience=audience,
        surface=surface,
        tone=tone,
        compact=compact,
        output_format="ascii" if ascii_only else "prompt",
    )


@mcp.tool()
def lint_voice_output(
    text: str,
    profile: str | None = None,
    audience: str | None = None,
    surface: str | None = None,
    tone: str | None = None,
) -> str:
    """Run deterministic VoiceMD checks on generated human-facing text."""
    issues = lint_voice_text(
        text,
        profile=profile,
        audience=audience,
        surface=surface,
        tone=tone,
    )
    return json.dumps([issue.as_dict() for issue in issues], ensure_ascii=False, indent=2)


if __name__ == "__main__":
    mcp.run()
