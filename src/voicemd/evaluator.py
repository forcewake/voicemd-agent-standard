from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .linter import lint_text
from .model import ResolvedVoiceContract

SUPPORTED_ASSERTIONS = {
    "must_contain",
    "must_not_contain",
    "max_words",
    "ascii_only",
    "lint_clean",
}


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number is not allowed: {value}")


@dataclass
class CaseResult:
    case_id: str
    passed: bool
    failures: list[str]
    skipped: bool = False


def load_responses(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    result: dict[str, str] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        item = json.loads(line, parse_constant=_reject_json_constant)
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise TypeError(f"{path}:{line_number}: expected JSON object with string id")
        case_id = item["id"]
        if case_id in result:
            raise ValueError(f"{path}:{line_number}: duplicate response id: {case_id}")
        if "response" in item:
            response = item["response"]
        elif "output" in item:
            response = item["output"]
        else:
            response = None
        if not isinstance(response, str):
            raise TypeError(f"{path}:{line_number}: expected response/output string")
        result[case_id] = response
    return result


def run_cases(
    contract: ResolvedVoiceContract,
    *,
    responses: dict[str, str] | None = None,
) -> list[CaseResult]:
    responses = responses or {}
    cases = contract.data.get("tests", [])
    if not isinstance(cases, list):
        raise TypeError("tests must be a list")
    results: list[CaseResult] = []
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            results.append(CaseResult(str(index), False, ["case must be a mapping"]))
            continue
        case_id = str(case.get("id") or f"case-{index + 1}")
        response = responses[case_id] if case_id in responses else case.get("response")
        if not isinstance(response, str):
            results.append(
                CaseResult(case_id, False, ["no response supplied"], skipped=True)
            )
            continue
        assertions = case.get("assertions", {})
        if not isinstance(assertions, dict):
            results.append(CaseResult(case_id, False, ["assertions must be a mapping"]))
            continue
        failures: list[str] = []
        unknown = sorted(
            str(key)
            for key in assertions
            if key not in SUPPORTED_ASSERTIONS and not str(key).startswith("x-")
        )
        if unknown:
            failures.append("unsupported assertions: " + ", ".join(unknown))

        required = assertions.get("must_contain", [])
        forbidden = assertions.get("must_not_contain", [])
        if not isinstance(required, list) or not all(isinstance(item, str) for item in required):
            failures.append("must_contain must be an array of strings")
            required = []
        if not isinstance(forbidden, list) or not all(
            isinstance(item, str) for item in forbidden
        ):
            failures.append("must_not_contain must be an array of strings")
            forbidden = []

        for phrase in required:
            if str(phrase).casefold() not in response.casefold():
                failures.append(f"missing required phrase: {phrase}")
        for phrase in forbidden:
            if str(phrase).casefold() in response.casefold():
                failures.append(f"contains forbidden phrase: {phrase}")
        max_words = assertions.get("max_words")
        if max_words is not None and (
            not isinstance(max_words, int) or isinstance(max_words, bool) or max_words < 1
        ):
            failures.append("max_words must be a positive integer")
            max_words = None
        if isinstance(max_words, int):
            count = len(re.findall(r"\b\w+\b", response, flags=re.UNICODE))
            if count > max_words:
                failures.append(f"{count} words exceeds {max_words}")
        for boolean_assertion in ("ascii_only", "lint_clean"):
            value = assertions.get(boolean_assertion)
            if value is not None and not isinstance(value, bool):
                failures.append(f"{boolean_assertion} must be a boolean")
        if assertions.get("ascii_only") is True and not response.isascii():
            failures.append("response is not ASCII-only")
        if assertions.get("lint_clean") is True:
            issues = lint_text(
                contract,
                response,
                profile=case.get("profile"),
                audience=case.get("audience"),
                surface=case.get("surface"),
                tone=case.get("tone"),
            )
            failures.extend(f"lint:{issue.rule_id}: {issue.message}" for issue in issues)
        effective = bool(required or forbidden) or isinstance(max_words, int)
        effective = effective or assertions.get("ascii_only") is True
        effective = effective or assertions.get("lint_clean") is True
        if not effective:
            failures.append("no supported effective assertion")
        results.append(CaseResult(case_id, not failures, failures))
    return results
