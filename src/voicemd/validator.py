from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from importlib.resources import files
from typing import Any

from jsonschema import Draft202012Validator

from .constants import (
    AUTHORITY_CAPABILITY_ALIASES,
    KIND,
    PROTECTED_AUTHORITY_CAPABILITIES,
    SPEC_VERSION,
    SPEC_VERSION_PATTERN,
)
from .model import ResolvedVoiceContract

CORE_GUIDANCE_KEYS = {"identity", "response", "language", "lexicon", "formatting"}
CONTEXTUAL_KEYS = {
    "activation",
    "authority",
    "epistemics",
    "interaction",
    "audiences",
    "surfaces",
    "tones",
    "profiles",
    "speech",
}


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


def _is_nonempty(value: Any) -> bool:
    return value not in (None, "", [], {})


def _normalized_term(value: Any) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", str(value).casefold())
    return " ".join(text.split())


def _authority_capability(value: Any) -> str:
    normalized = _normalized_term(value)
    return AUTHORITY_CAPABILITY_ALIASES.get(normalized, normalized.replace(" ", "_"))


def _id_duplicates(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    seen: set[str] = set()
    duplicates: set[str] = set()
    for item in value:
        item_id = item.get("id") if isinstance(item, dict) else None
        if not isinstance(item_id, str):
            continue
        if item_id in seen:
            duplicates.add(item_id)
        seen.add(item_id)
    return sorted(duplicates, key=str.casefold)


def _casefold_string(value: Any) -> str:
    return str(value).strip().casefold()


def _regex_quantifier(pattern: str, index: int) -> tuple[int, bool, bool] | None:
    """Return end index, variable-width, and unbounded for a quantifier."""
    char = pattern[index]
    if char in "*+?":
        return index + 1, True, char in "*+"
    if char != "{":
        return None
    match = re.match(r"\{(\d+)(?:,(\d*)?)?\}", pattern[index:])
    if not match:
        return None
    token = match.group(0)
    if "," not in token:
        return index + len(token), False, False
    minimum = int(match.group(1))
    raw_maximum = match.group(2)
    if raw_maximum in (None, ""):
        return index + len(token), True, True
    maximum = int(raw_maximum)
    return index + len(token), minimum != maximum, False


def regex_safety_error(pattern: str) -> str | None:
    """Reject syntax errors and obvious catastrophic-backtracking patterns.

    Python's stdlib regex engine has no execution timeout. The supported subset
    therefore rejects unbounded repetition of a group that itself contains a
    variable-width repeat or alternation, including ``(a+)+`` and ``(a|aa)+``.
    """
    if len(pattern) > 2048:
        return "pattern exceeds the 2048-character safety limit"
    try:
        re.compile(pattern)
    except re.error as exc:
        return f"invalid regex: {exc}"

    groups: list[dict[str, bool]] = []
    last_group: dict[str, bool] | None = None
    previous_was_quantifier = False
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if char == "\\":
            index += 2
            last_group = None
            previous_was_quantifier = False
            continue
        if char == "[":
            index += 1
            while index < len(pattern):
                if pattern[index] == "\\":
                    index += 2
                    continue
                if pattern[index] == "]":
                    index += 1
                    break
                index += 1
            last_group = None
            previous_was_quantifier = False
            continue
        if char == "(":
            groups.append({"variable_repeat": False, "alternation": False})
            index += 1
            last_group = None
            previous_was_quantifier = False
            continue
        if char == ")":
            if groups:
                closed = groups.pop()
                if groups:
                    groups[-1]["variable_repeat"] |= closed["variable_repeat"]
                    groups[-1]["alternation"] |= closed["alternation"]
                last_group = closed
            index += 1
            previous_was_quantifier = False
            continue
        if char == "|":
            if groups:
                groups[-1]["alternation"] = True
            index += 1
            last_group = None
            previous_was_quantifier = False
            continue

        quantifier = _regex_quantifier(pattern, index)
        if quantifier is not None:
            end, variable, unbounded = quantifier
            if char == "?" and index > 0 and pattern[index - 1] == "(":
                index = end
                last_group = None
                previous_was_quantifier = False
                continue
            # '?' and '+' immediately after another quantifier are lazy or
            # possessive modifiers, not another repetition layer.
            if previous_was_quantifier and char in "?+":
                index = end
                previous_was_quantifier = False
                continue
            if unbounded and last_group is not None:
                if last_group["variable_repeat"]:
                    return "unsafe nested quantifier in an unbounded repeated group"
                if last_group["alternation"]:
                    return "unsafe alternation in an unbounded repeated group"
            if variable:
                for group in groups:
                    group["variable_repeat"] = True
            index = end
            last_group = None
            previous_was_quantifier = True
            continue

        index += 1
        last_group = None
        previous_was_quantifier = False
    return None


def _effective_assertions(assertions: Any) -> bool:
    if not isinstance(assertions, dict):
        return False
    if any(
        isinstance(assertions.get(key), list) and bool(assertions[key])
        for key in ("must_contain", "must_not_contain")
    ):
        return True
    max_words = assertions.get("max_words")
    if isinstance(max_words, int) and not isinstance(max_words, bool) and max_words >= 0:
        return True
    return assertions.get("ascii_only") is True or assertions.get("lint_clean") is True


def _deterministic_rules(data: dict[str, Any]) -> list[dict[str, Any]]:
    rules = data.get("rules", [])
    if not isinstance(rules, list):
        return []
    result = []
    for rule in rules:
        if not isinstance(rule, dict) or rule.get("disabled") is True:
            continue
        pattern = rule.get("pattern")
        if (
            isinstance(pattern, str)
            and pattern
            and rule.get("assert") in {"must_match", "must_not_match"}
            and regex_safety_error(pattern) is None
        ):
            result.append(rule)
    return result


def _deterministic_tests(data: dict[str, Any]) -> list[dict[str, Any]]:
    tests = data.get("tests", [])
    if not isinstance(tests, list):
        return []
    return [
        case
        for case in tests
        if isinstance(case, dict)
        and case.get("disabled") is not True
        and isinstance(case.get("response"), str)
        and _effective_assertions(case.get("assertions"))
    ]


def _has_core_guidance(contract: ResolvedVoiceContract) -> bool:
    data = contract.data
    if contract.body or any(_is_nonempty(data.get(key)) for key in CORE_GUIDANCE_KEYS):
        return True
    rules = data.get("rules", [])
    return isinstance(rules, list) and any(
        isinstance(rule, dict)
        and rule.get("disabled") is not True
        and any(_is_nonempty(rule.get(key)) for key in ("instruction", "description", "pattern"))
        for rule in rules
    )


def _has_context(contract: ResolvedVoiceContract) -> bool:
    if any(_is_nonempty(contract.data.get(key)) for key in CONTEXTUAL_KEYS):
        return True
    return len(contract.sources) > 1 or any(
        _is_nonempty(source.metadata.get("extends")) for source in contract.sources
    )


def _semantic_errors_and_warnings(
    contract: ResolvedVoiceContract,
    *,
    strict: bool,
    check_selected_contexts: bool = True,
) -> tuple[list[str], list[str]]:
    data = contract.data
    errors: list[str] = []
    warnings: list[str] = []

    for collection in ("rules", "tests", "examples"):
        found: set[tuple[str, str]] = set()
        for item_id in _id_duplicates(data.get(collection)):
            found.add(("resolved contract", item_id))
        for source in contract.sources:
            for item_id in _id_duplicates(source.metadata.get(collection)):
                found.add((str(source.path), item_id))
        for location, item_id in sorted(found):
            errors.append(f"{collection}: duplicate id {item_id!r} in {location}")

    rules = data.get("rules", [])
    if isinstance(rules, list):
        for index, rule in enumerate(rules):
            if not isinstance(rule, dict) or rule.get("disabled") is True:
                continue
            pattern = rule.get("pattern")
            if isinstance(pattern, str):
                problem = regex_safety_error(pattern)
                if problem:
                    errors.append(f"rules[{index}].pattern: {problem}")

    activation = data.get("activation", {})
    if isinstance(activation, dict):
        include = activation.get("include", [])
        exclude = activation.get("exclude", [])
        if isinstance(include, list) and isinstance(exclude, list):
            overlap = sorted(
                {_casefold_string(item) for item in include}
                & {_casefold_string(item) for item in exclude}
            )
            if overlap:
                errors.append("activation include/exclude overlap: " + ", ".join(overlap))
        on_markers = activation.get("on_markers", [])
        off_markers = activation.get("off_markers", [])
        if isinstance(on_markers, list) and isinstance(off_markers, list):
            overlap = sorted(
                {_casefold_string(item) for item in on_markers}
                & {_casefold_string(item) for item in off_markers}
            )
            if overlap:
                errors.append("activation on/off marker overlap: " + ", ".join(overlap))

    authority = data.get("authority", {})
    if isinstance(authority, dict):
        may_control = authority.get("may_control", [])
        must_not_control = authority.get("must_not_control", [])
        may = (
            {_authority_capability(item) for item in may_control}
            if isinstance(may_control, list)
            else set()
        )
        must_not = (
            {_authority_capability(item) for item in must_not_control}
            if isinstance(must_not_control, list)
            else set()
        )
        protected = sorted(may & PROTECTED_AUTHORITY_CAPABILITIES)
        if protected:
            errors.append(
                "authority.may_control contains protected capabilities: " + ", ".join(protected)
            )
        overlap = sorted(may & must_not)
        if overlap:
            errors.append(
                "authority capabilities cannot be both allowed and forbidden: " + ", ".join(overlap)
            )
        if strict:
            missing = sorted(PROTECTED_AUTHORITY_CAPABILITIES - must_not)
            if missing:
                errors.append(
                    "strict: authority.must_not_control is missing: " + ", ".join(missing)
                )
            if (
                not isinstance(authority.get("precedence"), str)
                or not authority["precedence"].strip()
            ):
                errors.append("strict: authority.precedence is required")

    variants = {
        "audience": data.get("audiences", {}),
        "surface": data.get("surfaces", {}),
        "tone": data.get("tones", {}),
    }
    profiles = data.get("profiles", {})
    if isinstance(profiles, dict):
        for profile_name, profile in profiles.items():
            if not isinstance(profile, dict):
                continue
            for selector, mapping in variants.items():
                reference = profile.get(selector)
                if isinstance(reference, str) and (
                    not isinstance(mapping, dict) or reference not in mapping
                ):
                    errors.append(
                        f"profiles.{profile_name}.{selector}: unknown {selector} {reference!r}"
                    )

    tests = data.get("tests", [])
    if isinstance(tests, list):
        for index, case in enumerate(tests):
            if not isinstance(case, dict) or case.get("disabled") is True:
                continue
            profile = case.get("profile")
            if isinstance(profile, str) and (
                not isinstance(profiles, dict) or profile not in profiles
            ):
                errors.append(f"tests[{index}].profile: unknown profile {profile!r}")
            for selector, mapping in variants.items():
                reference = case.get(selector)
                if isinstance(reference, str) and (
                    not isinstance(mapping, dict) or reference not in mapping
                ):
                    errors.append(f"tests[{index}].{selector}: unknown {selector} {reference!r}")
            if not isinstance(case.get("response"), str):
                warnings.append(
                    f"tests[{index}] is not locally executable without a supplied response"
                )
            if not _effective_assertions(case.get("assertions")):
                warnings.append(f"tests[{index}] has no effective core deterministic assertion")

    default_language = data.get("default_language")
    language = data.get("language", {})
    if default_language is not None:
        warnings.append("default_language is deprecated; use language.default")
        if isinstance(language, dict) and language.get("default") not in (
            None,
            default_language,
        ):
            errors.append("default_language conflicts with language.default")
    if isinstance(language, dict):
        default = language.get("default")
        allowed = language.get("allowed")
        if isinstance(default, str) and isinstance(allowed, list) and default not in allowed:
            errors.append("language.default must be present in language.allowed")

    lexicon = data.get("lexicon", {})
    if isinstance(lexicon, dict):
        raw_preferred = lexicon.get("preferred", [])
        raw_forbidden = lexicon.get("forbidden", [])
        preferred = (
            {str(value).casefold() for value in raw_preferred}
            if isinstance(raw_preferred, list)
            else set()
        )
        forbidden = (
            {str(value).casefold() for value in raw_forbidden}
            if isinstance(raw_forbidden, list)
            else set()
        )
        overlap = sorted(preferred & forbidden)
        if overlap:
            errors.append(
                "lexicon terms cannot be both preferred and forbidden: " + ", ".join(overlap)
            )

    if check_selected_contexts:
        from .compiler import CompileError, _apply_profile
        from .merge import deep_merge

        selected_contexts: list[tuple[str, dict[str, Any]]] = []
        for category in ("audiences", "surfaces", "tones"):
            variants = data.get(category, {})
            if not isinstance(variants, dict):
                continue
            for name, override in variants.items():
                if isinstance(override, dict):
                    selected_contexts.append(
                        (
                            f"{category}.{name}",
                            deep_merge(data, override, append_unique_arrays=False),
                        )
                    )
        if isinstance(profiles, dict):
            for name in profiles:
                try:
                    selected, _, _, _ = _apply_profile(
                        data,
                        profile=name,
                        audience=None,
                        surface=None,
                        tone=None,
                    )
                except CompileError:
                    continue
                selected_contexts.append((f"profiles.{name}", selected))
        if isinstance(tests, list):
            for index, case in enumerate(tests):
                if not isinstance(case, dict) or case.get("disabled") is True:
                    continue
                if not any(case.get(key) for key in ("profile", "audience", "surface", "tone")):
                    continue
                try:
                    selected, _, _, _ = _apply_profile(
                        data,
                        profile=case.get("profile"),
                        audience=case.get("audience"),
                        surface=case.get("surface"),
                        tone=case.get("tone"),
                    )
                except CompileError:
                    continue
                selected_contexts.append((f"tests[{index}] selectors", selected))

        semantic_keys = {"activation", "authority", "language", "lexicon", "rules"}
        for label, selected in selected_contexts:
            projection = {key: selected[key] for key in semantic_keys if key in selected}
            context_errors, context_warnings = _semantic_errors_and_warnings(
                ResolvedVoiceContract(data=projection),
                strict=strict,
                check_selected_contexts=False,
            )
            errors.extend(f"{label}: {error}" for error in context_errors)
            warnings.extend(f"{label}: {warning}" for warning in context_warnings)

    return errors, warnings


def validate_contract(contract: ResolvedVoiceContract, *, strict: bool = False) -> ValidationResult:
    data = contract.data
    if not data:
        result = ValidationResult(level="L0-plain", warnings=list(contract.warnings))
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
    voice_spec = data.get("voice_spec")
    if not isinstance(voice_spec, str) or SPEC_VERSION_PATTERN.fullmatch(voice_spec) is None:
        warnings.append(
            f"This implementation targets voice_spec {SPEC_VERSION}; found {voice_spec!r}."
        )
    if data.get("kind") != KIND:
        warnings.append(f"Expected kind {KIND!r}; found {data.get('kind')!r}.")

    semantic_errors, semantic_warnings = _semantic_errors_and_warnings(contract, strict=strict)
    errors.extend(semantic_errors)
    warnings.extend(semantic_warnings)

    has_core = _has_core_guidance(contract)
    has_deterministic_evidence = bool(_deterministic_rules(data) or _deterministic_tests(data))
    if has_core and has_deterministic_evidence:
        level = "L3-testable"
    elif has_core and _has_context(contract):
        level = "L2-contextual"
    else:
        level = "L1-core"

    activation = data.get("activation", {})
    if strict and (not isinstance(activation, dict) or not activation.get("mode")):
        errors.append("strict: activation.mode is required")
    if strict and not data.get("authority"):
        errors.append("strict: authority boundary is required")
    if not has_core:
        message = "The structured contract has no concrete communication guidance."
        if strict:
            errors.append("strict: " + message)
        else:
            warnings.append(message)

    return ValidationResult(
        level=level,
        errors=list(dict.fromkeys(errors)),
        warnings=list(dict.fromkeys(warnings)),
    )
