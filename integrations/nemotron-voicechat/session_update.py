#!/usr/bin/env python3
"""Configure an NVIDIA NemotronLabs VoiceChat realtime session with VoiceMD.

Requires: pip install 'voicemd[nemotron]'
This example configures and verifies the session. It does not stream microphone audio.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import uuid

from voicemd import compile_voice


async def configure(url: str, voice_path: str, profile: str) -> None:
    import websockets

    instructions = compile_voice(
        path=voice_path,
        profile=profile,
        output_format="nemotron-ascii",
        compact=True,
        max_chars=5000,
    )
    if not instructions.isascii():
        raise ValueError("Nemotron VoiceChat instructions must be ASCII-only")

    async with websockets.connect(url, max_size=4 * 1024 * 1024) as websocket:
        created = json.loads(await websocket.recv())
        if created.get("type") != "session.created":
            raise RuntimeError(f"Expected session.created, got: {created}")

        event = {
            "type": "session.update",
            "event_id": str(uuid.uuid4()),
            "session": {
                "audio": {
                    "input": {"format": {"type": "audio/pcm", "rate": 24000}},
                    "output": {"format": {"type": "audio/pcm", "rate": 24000}},
                },
                "instructions": instructions,
                "tools": [],
            },
        }
        await websocket.send(json.dumps(event))
        updated = json.loads(await websocket.recv())
        if updated.get("type") != "session.updated":
            raise RuntimeError(f"Expected session.updated, got: {updated}")
        print(json.dumps({"status": "configured", "event": updated.get("type")}, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="ws://localhost:9000/v1/realtime")
    parser.add_argument("--voice", default="VOICE.md")
    parser.add_argument("--profile", default="nemotron_voicechat")
    args = parser.parse_args()
    asyncio.run(configure(args.url, args.voice, args.profile))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
