#!/usr/bin/env python3
"""Call any OpenAI-compatible /v1/chat/completions endpoint using VoiceMD."""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request

from voicemd import compile_voice


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("prompt")
    parser.add_argument("--base-url", default=os.getenv("OPENAI_BASE_URL", "http://127.0.0.1:8000/v1"))
    parser.add_argument("--api-key", default=os.getenv("OPENAI_API_KEY", "local"))
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL", "local-model"))
    parser.add_argument("--voice", default="VOICE.md")
    parser.add_argument("--profile")
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()

    voice = compile_voice(path=args.voice, profile=args.profile, compact=args.compact)
    payload = {
        "model": args.model,
        "messages": [
            {"role": "system", "content": "Answer the user's request accurately."},
            {"role": "system", "content": voice},
            {"role": "user", "content": args.prompt},
        ],
        "temperature": 0.2,
    }
    request = urllib.request.Request(
        args.base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {args.api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        print(exc.read().decode("utf-8"))
        return 1
    print(result["choices"][0]["message"]["content"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
