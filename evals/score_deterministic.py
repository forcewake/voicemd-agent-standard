#!/usr/bin/env python3
"""Score generated JSONL results with deterministic VoiceMD checks."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from voicemd import load_voice
from voicemd.linter import lint_text

try:
    from .run_openai_compatible import (
        corpus_sha256,
        read_jsonl,
        strict_json_loads,
        validate_candidate_result,
    )
except ImportError:  # Direct script execution sets no package context.
    from run_openai_compatible import (
        corpus_sha256,
        read_jsonl,
        strict_json_loads,
        validate_candidate_result,
    )


SUPPORTED_ASSERTIONS = {
    "exact_text",
    "json_equals",
    "must_contain",
    "must_not_contain",
    "must_contain_any",
    "max_words",
    "ascii_only",
}


def _phrase_list(assertions: dict[str, object], key: str) -> list[str]:
    value = assertions.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TypeError(f"{key} must be an array of strings")
    return value


def assertion_failures(item: dict[str, object], response: str) -> list[str]:
    assertions = item.get("assertions", {})
    if not isinstance(assertions, dict):
        raise TypeError("assertions must be an object")
    unknown = sorted(
        str(key)
        for key in assertions
        if key not in SUPPORTED_ASSERTIONS and not str(key).startswith("x-")
    )
    if unknown:
        raise ValueError("unsupported assertions: " + ", ".join(unknown))

    failures: list[str] = []
    exact_text = assertions.get("exact_text")
    if exact_text is not None and not isinstance(exact_text, str):
        raise TypeError("exact_text must be a string")
    if isinstance(exact_text, str) and response != exact_text:
        failures.append("response does not exactly match expected text")
    if "json_equals" in assertions:
        try:
            parsed = strict_json_loads(response)
        except (json.JSONDecodeError, ValueError):
            failures.append("response is not exactly one valid JSON value")
        else:
            if parsed != assertions["json_equals"]:
                failures.append("JSON response does not match expected value")

    required = _phrase_list(assertions, "must_contain")
    forbidden = _phrase_list(assertions, "must_not_contain")
    for phrase in required:
        if phrase.casefold() not in response.casefold():
            failures.append(f"missing required phrase: {phrase}")
    for phrase in forbidden:
        if phrase.casefold() in response.casefold():
            failures.append(f"contains forbidden phrase: {phrase}")

    alternatives_value = assertions.get("must_contain_any", [])
    if not isinstance(alternatives_value, list):
        raise TypeError("must_contain_any must be an array of string arrays")
    for alternatives in alternatives_value:
        if (
            not isinstance(alternatives, list)
            or not alternatives
            or not all(isinstance(phrase, str) for phrase in alternatives)
        ):
            raise TypeError("must_contain_any entries must be non-empty string arrays")
        if not any(phrase.casefold() in response.casefold() for phrase in alternatives):
            failures.append("missing every accepted alternative: " + " | ".join(alternatives))

    max_words = assertions.get("max_words")
    if max_words is not None and (
        not isinstance(max_words, int) or isinstance(max_words, bool) or max_words < 0
    ):
        raise TypeError("max_words must be a non-negative integer")
    if isinstance(max_words, int):
        word_count = len(re.findall(r"\b\w+\b", response, flags=re.UNICODE))
        if word_count > max_words:
            failures.append(f"{word_count} words exceeds {max_words}")
    ascii_only = assertions.get("ascii_only")
    if ascii_only is not None and not isinstance(ascii_only, bool):
        raise TypeError("ascii_only must be a boolean")
    if ascii_only is True and not response.isascii():
        failures.append("response is not ASCII-only")

    effective = bool(required or forbidden or alternatives_value)
    effective = effective or isinstance(exact_text, str) or "json_equals" in assertions
    effective = effective or isinstance(max_words, int) or ascii_only is True
    if not effective:
        raise ValueError("case has no supported effective deterministic assertion")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--voice", default="VOICE.md")
    parser.add_argument("--cases", default="evals/prompts.jsonl")
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Allow a non-empty subset of the selected corpus while still rejecting unknown IDs.",
    )
    parser.add_argument("--results", required=True)
    args = parser.parse_args()

    canonical_cases = list(read_jsonl(Path(args.cases)))
    if not canonical_cases:
        raise ValueError("cases file contains no evaluation cases")
    corpus = {item["id"]: item for item in canonical_cases}
    selected = set(args.case) or set(corpus)
    unknown_selection = sorted(selected - set(corpus))
    if unknown_selection:
        raise ValueError("unknown --case IDs: " + ", ".join(unknown_selection))

    results = list(read_jsonl(Path(args.results)))
    if not results:
        raise ValueError("results file contains no evaluation cases")
    result_ids = {item["id"] for item in results}
    unexpected = sorted(result_ids - selected)
    if unexpected:
        raise ValueError("unexpected result IDs: " + ", ".join(unexpected))
    missing = sorted(selected - result_ids)
    if missing and not args.allow_partial:
        raise ValueError("missing result IDs: " + ", ".join(missing))

    contract = load_voice(path=args.voice, include_global=False)
    expected_corpus_sha256 = corpus_sha256(canonical_cases)
    failed = 0
    for item in results:
        case_id = item["id"]
        expected = corpus[case_id]
        candidate = validate_candidate_result(
            item,
            expected_case=expected,
            expected_corpus_sha256=expected_corpus_sha256,
            contract=contract,
        )
        response = candidate["response"]
        if not isinstance(response, str):  # The shared validator narrows this at runtime.
            raise TypeError(f"case {case_id}: missing response string")
        failures = assertion_failures(expected, response)

        activation = candidate["activation"]
        voice_applied = isinstance(activation, dict) and activation.get("apply") is True
        issues = []
        if voice_applied:
            selectors = candidate["selectors"]
            if not isinstance(selectors, dict):  # Shared validation guarantees this shape.
                raise TypeError(f"case {case_id}: missing selector provenance")
            issues = lint_text(
                contract,
                response,
                profile=selectors.get("profile"),
                audience=selectors.get("audience"),
                surface=selectors.get("surface"),
                tone=selectors.get("tone"),
            )
        errors = [issue for issue in issues if issue.severity == "error"]
        if errors or failures:
            failed += 1
            print(f"FAIL {case_id}")
            for failure in failures:
                print(f"  assertion: {failure}")
            for issue in issues:
                print(f"  {issue.severity}: {issue.rule_id}: {issue.message}")
        else:
            print(f"PASS {case_id} ({len(issues)} non-error findings)")
    print(f"summary: {len(results) - failed}/{len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
