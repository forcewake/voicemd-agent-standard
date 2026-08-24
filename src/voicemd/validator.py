from __future__ import annotations

import json
from dataclasses import dataclass, field
from importlib.resources import files
from typing import Any

from jsonschema import Draft202012Validator

from .constants import KIND, SPEC_VERSION
from .model import ResolvedVoiceContract


@dataclass
class ValidationResult:
    level: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _schema() -> dict[str, Any]:
    path = files("voicemd").joinpath("resources/voice.schema.json")
    return json.loads(path.read_text(encoding="utf-8"))


def validate_contract(contract: ResolvedVoiceContract, *, strict: bool = False) -> ValidationResult:
    data = contract.data
    if not data:
        level = "L0-plain"
        result = ValidationResult(level=level, warnings=list(contract.warnings))
        if not contract.body:
            result.errors.append("VOICE.md is empty")
        if strict:
            result.errors.append("Strict validation requires YAML frontmatter (L1 or higher)")
        return result

    validator = Draft202012Validator(_schema())
    errors = []
    for error in sorted(validator.iter_errors(data), key=lambda item: list(item.absolute_path)):
        location = ".".join(str(part) for part in error.absolute_path) or "frontmatter"
        errors.append(f"{location}: {error.message}")

    warnings = list(contract.warnings)
    if data.get("voice_spec") != SPEC_VERSION:
        warnings.append(
            f"This implementation targets voice_spec {SPEC_VERSION}; found {data.get('voice_spec')!r}."
        )
    if data.get("kind") != KIND:
        warnings.append(f"Expected kind {KIND!r}; found {data.get('kind')!r}.")

    lexicon = data.get("lexicon", {})
    if isinstance(lexicon, dict):
        preferred = {str(value).casefold() for value in lexicon.get("preferred", [])}
        forbidden = {str(value).casefold() for value in lexicon.get("forbidden", [])}
        overlap = sorted(preferred & forbidden)
        if overlap:
            errors.append("lexicon terms cannot be both preferred and forbidden: " + ", ".join(overlap))

    activation = data.get("activation", {})
    has_behavior = any(
        key in data
        for key in ("epistemics", "interaction", "audiences", "surfaces", "speech", "rules")
    )
    has_tests = bool(data.get("tests"))
    if has_tests:
        level = "L3-testable"
    elif has_behavior:
        level = "L2-contextual"
    else:
        level = "L1-core"

    if strict and isinstance(activation, dict) and not activation.get("mode"):
        errors.append("strict: activation.mode is required")
    if strict and not data.get("authority"):
        errors.append("strict: authority boundary is required")
    if not contract.body and not any(
        data.get(key) for key in ("identity", "response", "epistemics", "interaction", "rules")
    ):
        warnings.append("The contract has metadata but no concrete communication guidance.")
    return ValidationResult(level=level, errors=errors, warnings=warnings)
