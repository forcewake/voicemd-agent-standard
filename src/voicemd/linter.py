from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .compiler import _apply_profile
from .model import ResolvedVoiceContract

EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002700-\U000027BF"
    "\U00002600-\U000026FF"
    "]",
    flags=re.UNICODE,
)
SENTENCE_RE = re.compile(r"(?<=[.!?])(?:\s+|$)")


@dataclass(frozen=True)
class LintIssue:
    rule_id: str
    severity: str
    message: str
    evidence: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "message": self.message,
            "evidence": self.evidence,
        }


def _search_literal(text: str, phrase: str) -> re.Match[str] | None:
    return re.search(re.escape(phrase), text, flags=re.IGNORECASE)


def lint_text(
    contract: ResolvedVoiceContract,
    text: str,
    *,
    profile: str | None = None,
    audience: str | None = None,
    surface: str | None = None,
    tone: str | None = None,
) -> list[LintIssue]:
    data, _, _, _ = _apply_profile(
        contract.data,
        profile=profile,
        audience=audience,
        surface=surface,
        tone=tone,
    )
    issues: list[LintIssue] = []

    lexicon = data.get("lexicon", {})
    if isinstance(lexicon, dict):
        for phrase in lexicon.get("forbidden", []):
            if not isinstance(phrase, str):
                continue
            match = _search_literal(text, phrase)
            if match:
                issues.append(
                    LintIssue(
                        "lexicon.forbidden",
                        "error",
                        f"Forbidden phrase found: {phrase}",
                        match.group(0),
                    )
                )

    formatting = data.get("formatting", {})
    if isinstance(formatting, dict):
        emoji_policy = formatting.get("emoji")
        if emoji_policy in {False, "never", "none"}:
            match = EMOJI_RE.search(text)
            if match:
                issues.append(
                    LintIssue("formatting.emoji", "error", "Emoji are disabled", match.group(0))
                )
        if formatting.get("tables") in {False, "never", "none"}:
            if re.search(r"^\s*\|.*\|\s*$", text, flags=re.MULTILINE):
                issues.append(
                    LintIssue("formatting.tables", "warning", "Markdown tables are disabled")
                )

    response = data.get("response", {})
    if isinstance(response, dict):
        max_words = response.get("max_words")
        if isinstance(max_words, int) and max_words >= 0:
            count = len(re.findall(r"\b\w+\b", text, flags=re.UNICODE))
            if count > max_words:
                issues.append(
                    LintIssue(
                        "response.max_words",
                        "error",
                        f"Response has {count} words; maximum is {max_words}",
                    )
                )
        max_sentences = response.get("max_sentences")
        if isinstance(max_sentences, int) and max_sentences >= 0:
            parts = [part for part in SENTENCE_RE.split(text.strip()) if part.strip()]
            if len(parts) > max_sentences:
                issues.append(
                    LintIssue(
                        "response.max_sentences",
                        "error",
                        f"Response has {len(parts)} sentences; maximum is {max_sentences}",
                    )
                )

    speech = data.get("speech", {})
    if isinstance(speech, dict) and speech.get("ascii_only") is True and not text.isascii():
        bad = next((char for char in text if not char.isascii()), None)
        issues.append(
            LintIssue("speech.ascii_only", "error", "Output contains non-ASCII text", bad)
        )

    rules = data.get("rules", [])
    if isinstance(rules, list):
        for rule in rules:
            if not isinstance(rule, dict) or rule.get("disabled") is True:
                continue
            pattern = rule.get("pattern")
            if not isinstance(pattern, str):
                continue
            try:
                match = re.search(pattern, text)
            except re.error as exc:
                issues.append(
                    LintIssue(
                        str(rule.get("id", "rule.pattern")),
                        "error",
                        f"Invalid rule regex: {exc}",
                    )
                )
                continue
            mode = rule.get("assert", "must_not_match")
            violated = (mode == "must_not_match" and match is not None) or (
                mode == "must_match" and match is None
            )
            if violated:
                issues.append(
                    LintIssue(
                        str(rule.get("id", "rule.pattern")),
                        str(rule.get("severity", "error")),
                        str(rule.get("message") or rule.get("instruction") or "Rule violated"),
                        match.group(0) if match else None,
                    )
                )
    return issues
