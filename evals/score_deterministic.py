#!/usr/bin/env python3
"""Score generated JSONL results with deterministic VoiceMD checks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from voicemd import lint_voice_text


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--voice", default="VOICE.md")
    parser.add_argument("--results", required=True)
    args = parser.parse_args()

    total = 0
    failed = 0
    for line_number, line in enumerate(Path(args.results).read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        item = json.loads(line)
        response = item.get("response")
        if not isinstance(response, str):
            raise ValueError(f"line {line_number}: missing response string")
        issues = lint_voice_text(
            response,
            path=args.voice,
            profile=item.get("profile"),
            audience=item.get("audience"),
            surface=item.get("surface"),
            tone=item.get("tone"),
        )
        errors = [issue for issue in issues if issue.severity == "error"]
        total += 1
        if errors:
            failed += 1
            print(f"FAIL {item.get('id', line_number)}")
            for issue in issues:
                print(f"  {issue.severity}: {issue.rule_id}: {issue.message}")
        else:
            print(f"PASS {item.get('id', line_number)} ({len(issues)} non-error findings)")
    print(f"summary: {total - failed}/{total} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
