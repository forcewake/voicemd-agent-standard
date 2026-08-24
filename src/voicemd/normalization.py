from __future__ import annotations

import math
from copy import deepcopy
from typing import Any

MAX_SAFE_INTEGER = (1 << 53) - 1

# Unicode White_Space, pinned explicitly so Python, ECMAScript, JSON Schema,
# CLI, and HTTP implementations do not inherit different runtime definitions.
PORTABLE_SELECTOR_WHITESPACE = frozenset(
    "\u0009\u000a\u000b\u000c\u000d\u0020\u0085\u00a0\u1680"
    "\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a"
    "\u2028\u2029\u202f\u205f\u3000"
)


class NormalizationError(ValueError):
    pass


def is_nonblank_selector(value: object) -> bool:
    return isinstance(value, str) and any(
        character not in PORTABLE_SELECTOR_WHITESPACE for character in value
    )


def portable_nonnegative_integer(value: object) -> int | None:
    """Return the normalized VoiceMD integer, or ``None`` when out of domain."""

    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if 0 <= value <= MAX_SAFE_INTEGER else None
    if (
        isinstance(value, float)
        and math.isfinite(value)
        and value.is_integer()
        and 0 <= value <= MAX_SAFE_INTEGER
    ):
        return int(value)
    return None


def prepare_selector_overlay(data: dict[str, Any]) -> dict[str, Any]:
    """Canonicalize a legacy alias tombstone immediately before selection.

    String aliases deliberately remain untouched until all selector operands
    have merged, where conflict checking has the complete effective context.
    """

    prepared = deepcopy(data)
    if "default_language" not in prepared or prepared["default_language"] is not None:
        return prepared

    language = prepared.get("language")
    if language is None:
        if "language" not in prepared:
            prepared["language"] = {"default": None}
    elif isinstance(language, dict):
        if "default" in language and language["default"] is not None:
            raise NormalizationError(
                "selector default_language conflicts with language.default"
            )
        language["default"] = None
    else:
        raise NormalizationError(
            "selector default_language requires language to be a mapping"
        )
    del prepared["default_language"]
    return prepared


def _location(path: tuple[str, ...]) -> str:
    return ".".join(path) or "frontmatter"


def _is_selector_overlay(path: tuple[str, ...]) -> bool:
    if len(path) >= 2 and path[0] in {"audiences", "surfaces", "tones"}:
        return True
    return len(path) >= 3 and path[0] == "profiles" and path[2] == "overrides"


def _normalize_integer_field(mapping: dict[str, Any], key: str) -> None:
    value = mapping.get(key)
    normalized = portable_nonnegative_integer(value)
    if normalized is not None:
        mapping[key] = normalized


def _normalize_language_alias(mapping: dict[str, Any], path: tuple[str, ...]) -> None:
    if "default_language" not in mapping:
        return
    legacy = mapping["default_language"]
    if legacy is None and _is_selector_overlay(path):
        language = mapping.get("language")
        if language is None:
            mapping["language"] = {"default": None}
        elif isinstance(language, dict):
            existing = language.get("default")
            if "default" in language and existing is not None:
                raise NormalizationError(
                    f"{_location(path)}.default_language conflicts with language.default"
                )
            language["default"] = None
        else:
            raise NormalizationError(
                f"{_location(path)}.default_language requires language to be a mapping"
            )
        del mapping["default_language"]
        return
    if not isinstance(legacy, str):
        return

    language = mapping.get("language")
    if language is None:
        mapping["language"] = {"default": legacy}
    elif not isinstance(language, dict):
        raise NormalizationError(
            f"{_location(path)}.default_language requires language to be a mapping"
        )
    elif "default" not in language:
        language["default"] = legacy
    elif language["default"] != legacy:
        raise NormalizationError(
            f"{_location(path)}.default_language conflicts with language.default"
        )
    del mapping["default_language"]


def _normalize_contract_mapping(
    mapping: Any,
    path: tuple[str, ...],
    *,
    normalize_dormant_aliases: bool,
) -> None:
    if not isinstance(mapping, dict):
        return

    if not path or normalize_dormant_aliases:
        _normalize_language_alias(mapping, path)

    response = mapping.get("response")
    if isinstance(response, dict):
        _normalize_integer_field(response, "max_words")
        _normalize_integer_field(response, "max_sentences")

    runtime = mapping.get("runtime")
    if isinstance(runtime, dict):
        _normalize_integer_field(runtime, "max_prompt_chars")

    tests = mapping.get("tests")
    if isinstance(tests, list):
        for case in tests:
            if not isinstance(case, dict):
                continue
            assertions = case.get("assertions")
            if isinstance(assertions, dict):
                _normalize_integer_field(assertions, "max_words")

    for category in ("audiences", "surfaces", "tones"):
        variants = mapping.get(category)
        if isinstance(variants, dict):
            for name, override in variants.items():
                _normalize_contract_mapping(
                    override,
                    (*path, category, str(name)),
                    normalize_dormant_aliases=normalize_dormant_aliases,
                )

    profiles = mapping.get("profiles")
    if isinstance(profiles, dict):
        for name, profile in profiles.items():
            if isinstance(profile, dict):
                _normalize_contract_mapping(
                    profile.get("overrides"),
                    (*path, "profiles", str(name), "overrides"),
                    normalize_dormant_aliases=normalize_dormant_aliases,
                )


def deprecated_language_alias_paths(data: dict[str, Any]) -> list[str]:
    paths: list[str] = []

    def visit(mapping: Any, path: tuple[str, ...]) -> None:
        if not isinstance(mapping, dict):
            return
        if "default_language" in mapping:
            paths.append(f"{_location(path)}.default_language")
        for category in ("audiences", "surfaces", "tones"):
            variants = mapping.get(category)
            if isinstance(variants, dict):
                for name, override in variants.items():
                    visit(override, (*path, category, str(name)))
        profiles = mapping.get("profiles")
        if isinstance(profiles, dict):
            for name, profile in profiles.items():
                if isinstance(profile, dict):
                    visit(
                        profile.get("overrides"),
                        (*path, "profiles", str(name), "overrides"),
                    )

    visit(data, ())
    return paths


def normalize_contract_data(
    data: dict[str, Any],
    *,
    normalize_dormant_aliases: bool = True,
) -> dict[str, Any]:
    """Return a copy with portable integer and deprecated-field normalization.

    Source resolution uses ``normalize_dormant_aliases=False`` so selector-local
    aliases remain merge operands until the exact context has been applied.
    """

    normalized = deepcopy(data)
    _normalize_contract_mapping(
        normalized,
        (),
        normalize_dormant_aliases=normalize_dormant_aliases,
    )
    return normalized
