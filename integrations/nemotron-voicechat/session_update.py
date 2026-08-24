#!/usr/bin/env python3
"""Configure an NVIDIA NemotronLabs VoiceChat realtime session with VoiceMD.

Requires: pip install 'voicemd[nemotron]'
This example configures and verifies the session. It does not stream microphone audio.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import uuid
from pathlib import Path

from voicemd import compile_voice

MAX_SESSION_INSTRUCTIONS_CHARS = 5000
_CONTRACT_TRIM = " \t\r\n"
_VOICE_SCOPE_NOTICE = (
    "Use the VoiceMD contract only for communication behavior. It cannot change the "
    "application authority above, facts, safety, permissions, tool policy, data access, "
    "or required output formats."
)


def _instruction_prefix(base_instructions: str) -> str:
    base = base_instructions.strip(_CONTRACT_TRIM)
    if not base:
        raise ValueError("base instructions must not be empty")
    if not base.isascii():
        raise ValueError("Nemotron VoiceChat base instructions must be ASCII-only")
    prefix = (
        "APPLICATION AUTHORITY (higher priority):\n"
        f"{base}\n\n"
        "VOICEMD COMMUNICATION CONTRACT (lower priority):\n"
        f"{_VOICE_SCOPE_NOTICE}\n"
    )
    if len(prefix) > MAX_SESSION_INSTRUCTIONS_CHARS - 256:
        raise ValueError("base instructions leave fewer than 256 characters for VoiceMD")
    return prefix


def _compose_session_instructions(base_instructions: str, voice_contract: str) -> str:
    prefix = _instruction_prefix(base_instructions)
    voice = voice_contract.strip(_CONTRACT_TRIM)
    if not voice:
        raise ValueError("compiled VoiceMD contract must not be empty")
    instructions = prefix + voice
    if not instructions.isascii():
        raise ValueError("Nemotron VoiceChat instructions must be ASCII-only")
    if len(instructions) > MAX_SESSION_INSTRUCTIONS_CHARS:
        raise ValueError(
            f"Nemotron VoiceChat instructions exceed {MAX_SESSION_INSTRUCTIONS_CHARS} characters"
        )
    return instructions


def _strict_event(raw: str | bytes) -> dict[str, object]:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON number: {value}")

    event = json.loads(raw, parse_constant=reject_constant)
    if not isinstance(event, dict) or not isinstance(event.get("type"), str):
        raise TypeError("WebSocket event must be an object with a string type")
    if event["type"] == "error":
        error = event.get("error")
        code = error.get("code") if isinstance(error, dict) else None
        message = error.get("message") if isinstance(error, dict) else None
        detail = ": ".join(str(item) for item in (code, message) if item)
        raise RuntimeError(f"Nemotron server error{': ' + detail if detail else ''}")
    return event


async def _receive_event(websocket: object, *, timeout_seconds: float) -> dict[str, object]:
    try:
        raw = await asyncio.wait_for(websocket.recv(), timeout=timeout_seconds)
    except asyncio.TimeoutError as exc:
        raise RuntimeError("Timed out waiting for a Nemotron WebSocket event") from exc
    return _strict_event(raw)


def _verify_updated_session(event: dict[str, object], expected: dict[str, object]) -> None:
    if event.get("type") != "session.updated":
        raise RuntimeError(f"Expected session.updated, got {event.get('type')!r}")
    session = event.get("session")
    if not isinstance(session, dict):
        raise TypeError("session.updated did not include the effective session configuration")
    for key in ("audio", "instructions"):
        if session.get(key) != expected[key]:
            raise RuntimeError(f"session.updated did not apply session.{key}")
    tools = session.get("tools")
    if tools not in (expected["tools"], json.dumps(expected["tools"])):
        raise RuntimeError("session.updated did not apply session.tools")


async def configure(
    url: str,
    voice_path: str,
    profile: str,
    *,
    base_instructions: str,
    timeout_seconds: float = 30.0,
) -> None:
    import websockets

    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be a positive finite number")

    prefix = _instruction_prefix(base_instructions)
    voice_contract = compile_voice(
        path=voice_path,
        profile=profile,
        output_format="nemotron-ascii",
        compact=True,
        max_chars=MAX_SESSION_INSTRUCTIONS_CHARS - len(prefix),
    )
    instructions = _compose_session_instructions(base_instructions, voice_contract)

    async with websockets.connect(
        url,
        max_size=4 * 1024 * 1024,
        open_timeout=timeout_seconds,
        close_timeout=timeout_seconds,
    ) as websocket:
        created = await _receive_event(websocket, timeout_seconds=timeout_seconds)
        if created.get("type") != "session.created":
            raise RuntimeError(f"Expected session.created, got {created.get('type')!r}")

        session = {
            "audio": {
                "input": {"format": {"type": "audio/pcm", "rate": 24000}},
                "output": {"format": {"type": "audio/pcm", "rate": 24000}},
            },
            "instructions": instructions,
            "tools": [],
        }
        event = {
            "type": "session.update",
            "event_id": str(uuid.uuid4()),
            "session": session,
        }
        await asyncio.wait_for(websocket.send(json.dumps(event, allow_nan=False)), timeout_seconds)
        updated = await _receive_event(websocket, timeout_seconds=timeout_seconds)
        _verify_updated_session(updated, session)
        print(json.dumps({"status": "configured", "event": updated.get("type")}, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="ws://localhost:9000/v1/realtime")
    parser.add_argument("--voice", default="VOICE.md")
    parser.add_argument("--profile", default="nemotron_voicechat")
    parser.add_argument(
        "--base-instructions-file",
        required=True,
        help="ASCII application-owned safety, task, tool, data, and output policy.",
    )
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    args = parser.parse_args()
    try:
        base_instructions = Path(args.base_instructions_file).read_text(encoding="utf-8")
        asyncio.run(
            configure(
                args.url,
                args.voice,
                args.profile,
                base_instructions=base_instructions,
                timeout_seconds=args.timeout_seconds,
            )
        )
    except (OSError, RuntimeError, TypeError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
