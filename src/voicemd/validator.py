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
from .normalization import (
    NormalizationError,
    deprecated_language_alias_paths,
    is_nonblank_selector,
    normalize_contract_data,
    portable_nonnegative_integer,
    prepare_selector_overlay,
)

CORE_GUIDANCE_KEYS = {"identity", "response", "language", "lexicon", "formatting"}
MAX_SELECTABLE_CONTEXTS = 256
MAX_REGEX_RULES = 128
MAX_REGEX_PATTERN_CHARS = 16_384
MAX_REGEX_WORK_UNITS = 16_777_216
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
TOP_LEVEL_KEYS = {
    "activation",
    "audiences",
    "authority",
    "default_language",
    "epistemics",
    "examples",
    "extends",
    "formatting",
    "identity",
    "interaction",
    "kind",
    "language",
    "lexicon",
    "metadata",
    "name",
    "profiles",
    "response",
    "rules",
    "runtime",
    "speech",
    "surfaces",
    "tests",
    "tones",
    "version",
    "voice_spec",
}
SECTION_KEYS = {
    "activation": {"exclude", "include", "mode", "off_markers", "on_markers"},
    "authority": {"may_control", "must_not_control", "precedence"},
    "epistemics": {
        "assumptions",
        "certainty",
        "confidence_pressure",
        "correction",
        "escalation",
        "evidence",
        "inference",
        "precision",
        "sources",
        "uncertainty",
    },
    "formatting": {
        "avoid",
        "bullets",
        "emoji",
        "headings",
        "lists",
        "markdown",
        "tables",
    },
    "identity": {"not_like", "sounds_like", "traits"},
    "interaction": {
        "challenge",
        "clarification",
        "defensiveness",
        "disagreement",
        "emotional_calibration",
        "escalation",
        "repeated_question",
        "technical_depth",
        "user_expertise",
    },
    "language": {"allowed", "default", "match_user", "mixing", "translation"},
    "lexicon": {"forbidden", "preferred", "pronunciations", "replacements"},
    "response": {
        "conclusion_first",
        "examples",
        "max_sentences",
        "max_words",
        "opening",
        "repetition",
        "softening",
        "structure",
        "verbosity",
    },
    "runtime": {"cache_key", "compact_for_small_models", "max_prompt_chars"},
    "speech": {
        "ascii_only",
        "avoid",
        "interruptions",
        "pronunciation",
        "sentence_length",
        "tts_friendly",
        "turn_length",
    },
}
PROFILE_KEYS = {"audience", "surface", "tone", "overrides"}
RULE_KEYS = {
    "id",
    "instruction",
    "description",
    "pattern",
    "flags",
    "assert",
    "severity",
    "message",
    "disabled",
}
TEST_KEYS = {
    "id",
    "prompt",
    "response",
    "profile",
    "audience",
    "surface",
    "tone",
    "disabled",
    "assertions",
}
ASSERTION_KEYS = {
    "must_contain",
    "must_not_contain",
    "max_words",
    "ascii_only",
    "lint_clean",
}
EXAMPLE_KEYS = {"id", "description", "input", "output", "disabled"}
PRONUNCIATION_KEYS = {"term", "pronunciation", "alphabet"}
OVERLAY_KEYS = {
    "activation",
    "authority",
    "default_language",
    "identity",
    "response",
    "language",
    "lexicon",
    "epistemics",
    "interaction",
    "formatting",
    "speech",
    "runtime",
    "rules",
    "tests",
    "examples",
    "metadata",
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


def _schema_errors(data: dict[str, Any]) -> list[str]:
    validator = Draft202012Validator(_schema())
    result = []
    for error in sorted(
        validator.iter_errors(data), key=lambda item: tuple(map(str, item.absolute_path))
    ):
        location = ".".join(str(part) for part in error.absolute_path) or "frontmatter"
        result.append(f"{location}: {error.message}")
    return result


def _unknown_field_messages(
    data: dict[str, Any], *, strict: bool
) -> tuple[list[str], list[str]]:
    messages: list[str] = []

    def inspect(mapping: Any, known: set[str], location: str) -> None:
        if not isinstance(mapping, dict):
            return
        for key in mapping:
            if not isinstance(key, str) or key in known or key.startswith("x-"):
                continue
            path = f"{location}.{key}" if location else key
            messages.append(f"unknown field {path!r}; extension fields must use the x-* prefix")

    def inspect_contract(mapping: Any, known: set[str], location: str) -> None:
        if not isinstance(mapping, dict):
            return
        inspect(mapping, known, location)
        for section, keys in SECTION_KEYS.items():
            inspect(mapping.get(section), keys, f"{location}.{section}".lstrip("."))
        lexicon = mapping.get("lexicon")
        if isinstance(lexicon, dict):
            pronunciations = lexicon.get("pronunciations")
            if isinstance(pronunciations, list):
                for index, item in enumerate(pronunciations):
                    inspect(
                        item,
                        PRONUNCIATION_KEYS,
                        f"{location}.lexicon.pronunciations[{index}]".lstrip("."),
                    )
        rules = mapping.get("rules")
        if isinstance(rules, list):
            for index, item in enumerate(rules):
                inspect(item, RULE_KEYS, f"{location}.rules[{index}]".lstrip("."))
        tests = mapping.get("tests")
        if isinstance(tests, list):
            for index, item in enumerate(tests):
                item_location = f"{location}.tests[{index}]".lstrip(".")
                inspect(item, TEST_KEYS, item_location)
                if isinstance(item, dict):
                    inspect(item.get("assertions"), ASSERTION_KEYS, f"{item_location}.assertions")
        examples = mapping.get("examples")
        if isinstance(examples, list):
            for index, item in enumerate(examples):
                inspect(item, EXAMPLE_KEYS, f"{location}.examples[{index}]".lstrip("."))

    inspect_contract(data, TOP_LEVEL_KEYS, "")
    for category in ("audiences", "surfaces", "tones"):
        variants = data.get(category)
        if isinstance(variants, dict):
            for name, override in variants.items():
                inspect_contract(override, OVERLAY_KEYS, f"{category}.{name}")
    profiles = data.get("profiles")
    if isinstance(profiles, dict):
        for name, profile in profiles.items():
            inspect(profile, PROFILE_KEYS, f"profiles.{name}")
            if isinstance(profile, dict):
                inspect_contract(
                    profile.get("overrides"),
                    OVERLAY_KEYS,
                    f"profiles.{name}.overrides",
                )

    if strict:
        return [f"strict: {message}" for message in messages], []
    return [], messages


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


def _nested_collection_duplicates(
    mapping: Any,
    *,
    location: str,
) -> set[tuple[str, str, str]]:
    """Return duplicate IDs from every core collection in one contract shape."""

    if not isinstance(mapping, dict):
        return set()
    found: set[tuple[str, str, str]] = set()
    for collection in ("rules", "tests", "examples"):
        for item_id in _id_duplicates(mapping.get(collection)):
            found.add((collection, location, item_id))
    for category in ("audiences", "surfaces", "tones"):
        variants = mapping.get(category)
        if not isinstance(variants, dict):
            continue
        for name, override in variants.items():
            found.update(
                _nested_collection_duplicates(
                    override,
                    location=f"{location} {category}.{name}",
                )
            )
    profiles = mapping.get("profiles")
    if isinstance(profiles, dict):
        for name, profile in profiles.items():
            if isinstance(profile, dict):
                found.update(
                    _nested_collection_duplicates(
                        profile.get("overrides"),
                        location=f"{location} profiles.{name}.overrides",
                    )
                )
    return found


def _casefold_string(value: Any) -> str:
    return str(value).strip().casefold()


def regex_safety_error(pattern: str) -> str | None:
    """Validate the portable-safe-v1 fixed-width regex subset.

    The subset deliberately excludes repetition, alternation, backreferences,
    lookarounds, named groups, and inline modifiers. That gives Python and ECMAScript
    implementations a bounded O(input_length * pattern_length) search without
    depending on a provider-specific regex timeout.
    """
    if len(pattern) > 512:
        return "pattern exceeds the 512-character safety limit"
    if not pattern:
        return "pattern must not be empty"
    if not pattern.isascii():
        return "patterns must be ASCII in portable-safe-v1"
    try:
        re.compile(pattern)
    except re.error as exc:
        return f"invalid regex: {exc}"

    allowed_escapes = frozenset(r"\.^$*+?{}[]()|/-nrtfv")
    depth = 0
    in_class = False
    class_has_content = False
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if char == "\\":
            if index + 1 >= len(pattern):
                return "pattern ends with an incomplete escape"
            escaped = pattern[index + 1]
            if escaped.isdigit():
                return "backreferences and octal escapes are not supported by portable-safe-v1"
            if escaped == "x":
                width = 2
                digits = pattern[index + 2 : index + 2 + width]
                if len(digits) != width or re.fullmatch(r"[0-9A-Fa-f]+", digits) is None:
                    return f"invalid \\{escaped} escape in portable-safe-v1 pattern"
                index += width + 2
            elif escaped in allowed_escapes:
                index += 2
            else:
                return f"escape \\{escaped} is not portable-safe-v1"
            class_has_content = class_has_content or in_class
            continue
        if in_class:
            if char == "]":
                if not class_has_content:
                    return "empty character classes are not supported"
                in_class = False
            elif char == "[":
                return "nested character-class syntax is not portable-safe-v1"
            elif not (char == "^" and not class_has_content):
                class_has_content = True
            index += 1
            continue
        if char == "[":
            in_class = True
            class_has_content = False
            index += 1
            continue
        if char in "*+?{}":
            return "repetition operators are not supported by portable-safe-v1"
        if char == "(":
            if pattern[index + 1 : index + 2] == "?":
                return "group extensions and inline modifiers are not portable-safe-v1"
            depth += 1
            if depth > 32:
                return "group nesting exceeds the portable-safe-v1 limit of 32"
            index += 1
            continue
        if char == ")":
            depth -= 1
            if depth < 0:
                return "unmatched closing parenthesis"
            index += 1
            continue
        if char == "|":
            return "alternation is not supported by portable-safe-v1"
        index += 1
    if in_class:
        return "unterminated character class"
    if depth:
        return "unterminated group"
    return None


def regex_flags_error(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return "flags must be an array containing only i, m, or s"
    if len(value) != len(set(value)):
        return "flags must not contain duplicates"
    unsupported = sorted(set(value) - {"i", "m", "s"})
    if unsupported:
        return "unsupported portable-safe-v1 flags: " + ", ".join(unsupported)
    return None


def regex_flags_value(value: Any) -> int:
    problem = regex_flags_error(value)
    if problem:
        raise ValueError(problem)
    flags = re.ASCII
    for item in value or []:
        flags |= {"i": re.IGNORECASE, "m": re.MULTILINE, "s": re.DOTALL}[item]
    return flags


def _effective_assertions(assertions: Any) -> bool:
    if not isinstance(assertions, dict):
        return False
    if any(
        isinstance(assertions.get(key), list) and bool(assertions[key])
        for key in ("must_contain", "must_not_contain")
    ):
        return True
    max_words = portable_nonnegative_integer(assertions.get("max_words"))
    if max_words is not None:
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
            and regex_flags_error(rule.get("flags")) is None
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

    unknown_errors, unknown_warnings = _unknown_field_messages(data, strict=strict)
    errors.extend(unknown_errors)
    warnings.extend(unknown_warnings)

    duplicate_ids = _nested_collection_duplicates(data, location="resolved contract")
    for source in contract.sources:
        duplicate_ids.update(
            _nested_collection_duplicates(source.metadata, location=str(source.path))
        )
    for collection, location, item_id in sorted(duplicate_ids):
        errors.append(f"{collection}: duplicate id {item_id!r} in {location}")

    rules = data.get("rules", [])
    if isinstance(rules, list):
        regex_rule_count = 0
        regex_pattern_chars = 0
        for index, rule in enumerate(rules):
            if not isinstance(rule, dict) or rule.get("disabled") is True:
                continue
            pattern = rule.get("pattern")
            if isinstance(pattern, str):
                regex_rule_count += 1
                regex_pattern_chars += len(pattern)
                problem = regex_safety_error(pattern)
                if problem:
                    errors.append(f"rules[{index}].pattern: {problem}")
            flags_problem = regex_flags_error(rule.get("flags"))
            if flags_problem:
                errors.append(f"rules[{index}].flags: {flags_problem}")
        if regex_rule_count > MAX_REGEX_RULES:
            errors.append(
                "active regex rule count exceeds reference limit "
                f"({regex_rule_count} > {MAX_REGEX_RULES})"
            )
        if regex_pattern_chars > MAX_REGEX_PATTERN_CHARS:
            errors.append(
                "aggregate regex pattern characters exceed reference limit "
                f"({regex_pattern_chars} > {MAX_REGEX_PATTERN_CHARS})"
            )

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
    for selector, mapping in variants.items():
        if isinstance(mapping, dict):
            for name in mapping:
                if not is_nonblank_selector(name):
                    errors.append(f"{selector} variant names must be non-empty strings")
    profiles = data.get("profiles", {})
    if isinstance(profiles, dict):
        for profile_name, profile in profiles.items():
            if not is_nonblank_selector(profile_name):
                errors.append("profile names must be non-empty strings")
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

    selected_test_count = 0
    if isinstance(tests, list):
        selected_test_count = sum(
            1
            for case in tests
            if isinstance(case, dict)
            and case.get("disabled") is not True
            and any(case.get(key) is not None for key in ("profile", "audience", "surface", "tone"))
        )
    selectable_context_count = (
        sum(len(mapping) for mapping in variants.values() if isinstance(mapping, dict))
        + (len(profiles) if isinstance(profiles, dict) else 0)
        + selected_test_count
    )
    within_context_budget = selectable_context_count <= MAX_SELECTABLE_CONTEXTS
    if not within_context_budget:
        errors.append(
            "selectable context count exceeds reference limit "
            f"({selectable_context_count} > {MAX_SELECTABLE_CONTEXTS})"
        )

    if check_selected_contexts and within_context_budget:
        from .compiler import CompileError, _apply_profile
        from .merge import deep_merge

        selected_contexts: list[tuple[str, dict[str, Any]]] = []
        for category in ("audiences", "surfaces", "tones"):
            variants = data.get(category, {})
            if not isinstance(variants, dict):
                continue
            for name, override in variants.items():
                if isinstance(override, dict):
                    try:
                        prepared = prepare_selector_overlay(override)
                        merged = deep_merge(data, prepared, append_unique_arrays=False)
                        merged = normalize_contract_data(merged)
                    except NormalizationError as exc:
                        errors.append(f"{category}.{name}: {exc}")
                        continue
                    selected_contexts.append(
                        (
                            f"{category}.{name}",
                            merged,
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
                except CompileError as exc:
                    errors.append(f"profiles.{name}: {exc}")
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
                except CompileError as exc:
                    errors.append(f"tests[{index}] selectors: {exc}")
                    continue
                selected_contexts.append((f"tests[{index}] selectors", selected))

        for label, selected in selected_contexts:
            errors.extend(f"{label}: {error}" for error in _schema_errors(selected))
            context_errors, context_warnings = _semantic_errors_and_warnings(
                ResolvedVoiceContract(data=selected),
                strict=strict,
                check_selected_contexts=False,
            )
            errors.extend(f"{label}: {error}" for error in context_errors)
            warnings.extend(f"{label}: {warning}" for warning in context_warnings)

    return errors, warnings


def _validate_contract(
    contract: ResolvedVoiceContract,
    *,
    strict: bool,
    check_selected_contexts: bool,
) -> ValidationResult:
    data = contract.data
    if not data:
        result = ValidationResult(level="L0-plain", warnings=list(contract.warnings))
        if not contract.body:
            result.errors.append("VOICE.md is empty")
        if strict:
            result.errors.append("Strict validation requires YAML frontmatter (L1 or higher)")
        if result.errors:
            result.level = "nonconforming"
        return result

    normalization_warnings = list(contract.warnings)
    if deprecated_language_alias_paths(data):
        normalization_warnings.append("default_language is deprecated; use language.default")
    try:
        data = normalize_contract_data(data, normalize_dormant_aliases=False)
    except NormalizationError as exc:
        return ValidationResult(
            level="nonconforming",
            errors=[str(exc)],
            warnings=list(dict.fromkeys(normalization_warnings)),
        )
    contract = ResolvedVoiceContract(
        data=data,
        bodies=contract.bodies,
        sources=contract.sources,
        dependency_edges=contract.dependency_edges,
        warnings=normalization_warnings,
    )

    errors = _schema_errors(data)

    warnings = list(contract.warnings)
    voice_spec = data.get("voice_spec")
    if not isinstance(voice_spec, str) or SPEC_VERSION_PATTERN.fullmatch(voice_spec) is None:
        warnings.append(
            f"This implementation targets voice_spec {SPEC_VERSION}; found {voice_spec!r}."
        )
    if data.get("kind") != KIND:
        warnings.append(f"Expected kind {KIND!r}; found {data.get('kind')!r}.")

    semantic_errors, semantic_warnings = _semantic_errors_and_warnings(
        contract,
        strict=strict,
        check_selected_contexts=check_selected_contexts,
    )
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
        level="nonconforming" if errors else level,
        errors=list(dict.fromkeys(errors)),
        warnings=list(dict.fromkeys(warnings)),
    )


def validate_contract(contract: ResolvedVoiceContract, *, strict: bool = False) -> ValidationResult:
    return _validate_contract(contract, strict=strict, check_selected_contexts=True)


def validate_selected_contract(
    contract: ResolvedVoiceContract,
    *,
    profile: str | None = None,
    audience: str | None = None,
    surface: str | None = None,
    tone: str | None = None,
    strict: bool = False,
) -> ValidationResult:
    """Validate the exact contextual contract a runtime is about to consume."""

    from .compiler import CompileError, _apply_profile

    try:
        selected, _, _, _ = _apply_profile(
            contract.data,
            profile=profile,
            audience=audience,
            surface=surface,
            tone=tone,
        )
    except CompileError as exc:
        return ValidationResult(
            level="nonconforming",
            errors=[str(exc)],
            warnings=list(contract.warnings),
        )
    selected_contract = ResolvedVoiceContract(
        data=selected,
        sources=contract.sources,
        bodies=contract.bodies,
        dependency_edges=contract.dependency_edges,
        warnings=contract.warnings,
    )
    return _validate_contract(
        selected_contract,
        strict=strict,
        check_selected_contexts=False,
    )
