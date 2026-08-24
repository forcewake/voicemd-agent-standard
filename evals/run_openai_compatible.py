#!/usr/bin/env python3
"""Generate VoiceMD regression outputs from an OpenAI-compatible endpoint."""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from voicemd import compile_voice


def read_jsonl(path: Path):
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        item = json.loads(line)
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not isinstance(item.get("prompt"), str):
            raise ValueError(f"{path}:{line_number}: expected object with string id and prompt")
        yield item


def call(base_url: str, api_key: str, model: str, messages: list[dict], temperature: float) -> tuple[str, int]:
    payload = {"model": model, "messages": messages, "temperature": temperature}
    request = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(exc.read().decode("utf-8")) from exc
    latency_ms = round((time.perf_counter() - started) * 1000)
    return result["choices"][0]["message"]["content"], latency_ms


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--voice", default="VOICE.md")
    parser.add_argument("--cases", default="evals/prompts.jsonl")
    parser.add_argument("--output", default="evals/results.jsonl")
    parser.add_argument("--base-url", default=os.getenv("VOICEMD_BASE_URL", "http://127.0.0.1:8000/v1"))
    parser.add_argument("--api-key", default=os.getenv("VOICEMD_API_KEY", "local"))
    parser.add_argument("--model", default=os.getenv("VOICEMD_MODEL", "local-model"))
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as output:
        for case in read_jsonl(Path(args.cases)):
            voice = compile_voice(
                path=args.voice,
                profile=case.get("profile"),
                audience=case.get("audience"),
                surface=case.get("surface"),
                tone=case.get("tone"),
                compact=args.compact,
            )
            response, latency_ms = call(
                args.base_url,
                args.api_key,
                args.model,
                [
                    {"role": "system", "content": "Answer accurately and follow the active communication contract."},
                    {"role": "system", "content": voice},
                    {"role": "user", "content": case["prompt"]},
                ],
                args.temperature,
            )
            result = {
                **case,
                "response": response,
                "model": args.model,
                "latency_ms": latency_ms,
            }
            output.write(json.dumps(result, ensure_ascii=False) + "\n")
            output.flush()
            print(f"completed: {case['id']}")
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
