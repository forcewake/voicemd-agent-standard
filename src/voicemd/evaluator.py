from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .linter import lint_text
from .model import ResolvedVoiceContract


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
        item = json.loads(line)
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise ValueError(f"{path}:{line_number}: expected JSON object with string id")
        response = item.get("response") or item.get("output")
        if not isinstance(response, str):
            raise ValueError(f"{path}:{line_number}: expected response/output string")
        result[item["id"]] = response
    return result


def run_cases(
    contract: ResolvedVoiceContract,
    *,
    responses: dict[str, str] | None = None,
) -> list[CaseResult]:
    responses = responses or {}
    cases = contract.data.get("tests", [])
    if not isinstance(cases, list):
        raise ValueError("tests must be a list")
    results: list[CaseResult] = []
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            results.append(CaseResult(str(index), False, ["case must be a mapping"]))
            continue
        case_id = str(case.get("id") or f"case-{index + 1}")
        response = responses[case_id] if case_id in responses else case.get("response")
        if not isinstance(response, str):
            results.append(CaseResult(case_id, True, [], skipped=True))
            continue
        assertions = case.get("assertions", {})
        if not isinstance(assertions, dict):
            results.append(CaseResult(case_id, False, ["assertions must be a mapping"]))
            continue
        failures: list[str] = []
        for phrase in assertions.get("must_contain", []):
            if str(phrase).casefold() not in response.casefold():
                failures.append(f"missing required phrase: {phrase}")
        for phrase in assertions.get("must_not_contain", []):
            if str(phrase).casefold() in response.casefold():
                failures.append(f"contains forbidden phrase: {phrase}")
        max_words = assertions.get("max_words")
        if isinstance(max_words, int):
            count = len(re.findall(r"\b\w+\b", response, flags=re.UNICODE))
            if count > max_words:
                failures.append(f"{count} words exceeds {max_words}")
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
        results.append(CaseResult(case_id, not failures, failures))
    return results
