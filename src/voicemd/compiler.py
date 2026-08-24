from __future__ import annotations

import json
import math
from collections.abc import Iterable
from hashlib import sha256
from typing import Any

import rfc8785

from .ascii import to_ascii
from .merge import deep_merge
from .model import ResolvedVoiceContract
from .normalization import (
    MAX_SAFE_INTEGER,
    NormalizationError,
    is_nonblank_selector,
    normalize_contract_data,
    prepare_selector_overlay,
)


class CompileError(ValueError):
    pass


SUPPORTED_OUTPUT_FORMATS = {
    "prompt",
    "json",
    "canonical-json",
    "sha256",
    "ascii",
    "nemotron",
    "nemotron-ascii",
}
JCS_SAFE_INTEGER = MAX_SAFE_INTEGER
VOICE_TRIM_CHARS = " \t\n\r"


def _json_dumps(value: Any, **kwargs: Any) -> str:
    try:
        return json.dumps(value, allow_nan=False, **kwargs)
    except (TypeError, ValueError) as exc:
        raise CompileError(
            f"Contract contains a value that cannot be encoded as strict JSON: {exc}"
        ) from exc


def _assert_jcs_interop_domain(
    value: Any,
    *,
    path: str = "$",
    active: set[int] | None = None,
) -> None:
    """Enforce VoiceMD's deterministic cross-language input profile before JCS."""

    if value is None or isinstance(value, bool):
        return
    if isinstance(value, int):
        if abs(value) > JCS_SAFE_INTEGER:
            raise CompileError(
                f"RFC 8785 input at {path} is outside the VoiceMD safe-integer profile"
            )
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CompileError(f"RFC 8785 input at {path} contains a non-finite number")
        if value.is_integer() and abs(value) > JCS_SAFE_INTEGER:
            raise CompileError(
                f"RFC 8785 input at {path} is outside the VoiceMD safe-integer profile"
            )
        return
    if isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise CompileError(f"RFC 8785 input at {path} contains a lone surrogate") from exc
        return
    if active is None:
        active = set()
    if isinstance(value, list):
        identity = id(value)
        if identity in active:
            raise CompileError(f"RFC 8785 input at {path} is recursive")
        active.add(identity)
        try:
            for index, item in enumerate(value):
                _assert_jcs_interop_domain(item, path=f"{path}[{index}]", active=active)
        finally:
            active.remove(identity)
        return
    if isinstance(value, dict):
        identity = id(value)
        if identity in active:
            raise CompileError(f"RFC 8785 input at {path} is recursive")
        active.add(identity)
        try:
            for key, item in value.items():
                if not isinstance(key, str):
                    raise CompileError(f"RFC 8785 input at {path} has a non-string key")
                _assert_jcs_interop_domain(key, path=f"{path}.<key>", active=active)
                _assert_jcs_interop_domain(item, path=f"{path}.{key}", active=active)
        finally:
            active.remove(identity)
        return
    raise CompileError(f"RFC 8785 input at {path} has unsupported type {type(value).__name__}")


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _sentence(value: Any) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if value is None:
        return "unspecified"
    if isinstance(value, (str, int, float)):
        return str(value)
    return _json_dumps(value, ensure_ascii=False, sort_keys=True)


def _bullets(title: str, values: Iterable[Any]) -> list[str]:
    items = [item for item in values if item not in (None, "", [], {})]
    if not items:
        return []
    lines = [f"## {title}"]
    for item in items:
        if isinstance(item, dict):
            if "id" in item:
                label = str(item.get("id"))
                detail = item.get("instruction") or item.get("description") or item.get("message")
                lines.append(f"- {label}: {_sentence(detail or item)}")
            else:
                for key, value in item.items():
                    lines.append(f"- {key.replace('_', ' ')}: {_sentence(value)}")
        else:
            lines.append(f"- {_sentence(item)}")
    return lines


def _mapping(title: str, mapping: Any) -> list[str]:
    if not isinstance(mapping, dict) or not mapping:
        return []
    lines = [f"## {title}"]
    for key, value in mapping.items():
        label = key.replace("_", " ")
        if isinstance(value, dict):
            lines.append(f"- {label}:")
            for child_key, child_value in value.items():
                lines.append(f"  - {child_key.replace('_', ' ')}: {_sentence(child_value)}")
        elif isinstance(value, list):
            lines.append(f"- {label}: " + "; ".join(_sentence(item) for item in value))
        else:
            lines.append(f"- {label}: {_sentence(value)}")
    return lines


def _apply_profile(
    data: dict[str, Any],
    *,
    profile: str | None,
    audience: str | None,
    surface: str | None,
    tone: str | None,
) -> tuple[dict[str, Any], str | None, str | None, str | None]:
    for label, value in (
        ("profile", profile),
        ("audience", audience),
        ("surface", surface),
        ("tone", tone),
    ):
        if value is not None and not is_nonblank_selector(value):
            raise CompileError(f"{label} selector must be a non-empty string")

    try:
        selected = normalize_contract_data(data, normalize_dormant_aliases=False)
    except NormalizationError as exc:
        raise CompileError(str(exc)) from exc

    profile_overrides: dict[str, Any] = {}
    profiles = selected.get("profiles", {})
    active_profile = profile
    if active_profile is None and isinstance(profiles, dict) and "default" in profiles:
        active_profile = "default"
    if active_profile is not None:
        if not isinstance(profiles, dict) or active_profile not in profiles:
            raise CompileError(f"Unknown profile: {active_profile}")
        profile_data = profiles[active_profile]
        if not isinstance(profile_data, dict):
            raise CompileError(f"Profile '{active_profile}' must be a mapping")
        audience = audience if audience is not None else profile_data.get("audience")
        surface = surface if surface is not None else profile_data.get("surface")
        tone = tone if tone is not None else profile_data.get("tone")
        raw_overrides = profile_data.get("overrides", {})
        if not isinstance(raw_overrides, dict):
            raise CompileError(f"Profile '{active_profile}' overrides must be a mapping")
        profile_overrides = raw_overrides

    # Named variants establish the selected context. Profile-local overrides are
    # applied last because they are the most specific part of a profile.
    for category, name in (("audiences", audience), ("surfaces", surface), ("tones", tone)):
        if name is not None:
            if not is_nonblank_selector(name):
                raise CompileError(f"{category[:-1]} selector must be a non-empty string")
            variants = selected.get(category, {})
            if not isinstance(variants, dict) or name not in variants:
                raise CompileError(f"Unknown {category[:-1]}: {name}")
            try:
                override = prepare_selector_overlay(variants[name])
            except NormalizationError as exc:
                raise CompileError(str(exc)) from exc
            selected = deep_merge(selected, override, append_unique_arrays=False)
    try:
        profile_overrides = prepare_selector_overlay(profile_overrides)
    except NormalizationError as exc:
        raise CompileError(str(exc)) from exc
    selected = deep_merge(selected, profile_overrides, append_unique_arrays=False)
    try:
        selected = normalize_contract_data(selected)
    except NormalizationError as exc:
        raise CompileError(str(exc)) from exc
    return selected, audience, surface, tone


def resolve_context(
    contract: ResolvedVoiceContract,
    *,
    profile: str | None = None,
    audience: str | None = None,
    surface: str | None = None,
    tone: str | None = None,
) -> dict[str, Any]:
    """Return contract data after applying the selected contextual overrides."""

    selected, _, _, _ = _apply_profile(
        contract.data,
        profile=profile,
        audience=audience,
        surface=surface,
        tone=tone,
    )
    return selected


def _compact_mapping(mapping: Any, prefix: str) -> list[str]:
    if not isinstance(mapping, dict):
        return []
    result: list[str] = []
    for key, value in mapping.items():
        if isinstance(value, dict):
            result.extend(_compact_mapping(value, f"{prefix}{key}."))
        elif isinstance(value, list):
            if value:
                result.append(f"{prefix}{key}=" + "; ".join(_sentence(item) for item in value))
        elif value is not None:
            result.append(f"{prefix}{key}={_sentence(value)}")
    return result


def _require_selected_contract(
    contract: ResolvedVoiceContract,
    *,
    profile: str | None,
    audience: str | None,
    surface: str | None,
    tone: str | None,
) -> None:
    from .validator import validate_selected_contract

    result = validate_selected_contract(
        contract,
        profile=profile,
        audience=audience,
        surface=surface,
        tone=tone,
        strict=False,
    )
    if not result.ok:
        raise CompileError("Selected VOICE.md failed validation: " + "; ".join(result.errors))


def canonical_contract_json(
    contract: ResolvedVoiceContract,
    *,
    profile: str | None = None,
    audience: str | None = None,
    surface: str | None = None,
    tone: str | None = None,
) -> str:
    """Serialize selected contract semantics without workspace-specific paths."""

    _require_selected_contract(
        contract,
        profile=profile,
        audience=audience,
        surface=surface,
        tone=tone,
    )

    active_profile = profile
    profiles = contract.data.get("profiles", {})
    if active_profile is None and isinstance(profiles, dict) and "default" in profiles:
        active_profile = "default"
    selected, audience, surface, tone = _apply_profile(
        contract.data,
        profile=profile,
        audience=audience,
        surface=surface,
        tone=tone,
    )
    bodies = []
    for _, body in contract.bodies:
        normalized = (
            body.replace("\r\n", "\n").replace("\r", "\n").strip(VOICE_TRIM_CHARS)
        )
        if normalized:
            bodies.append(normalized)
    payload = {
        "active": {
            "audience": audience,
            "profile": active_profile,
            "surface": surface,
            "tone": tone,
        },
        "contract": selected,
        "markdown_bodies": bodies,
    }
    _assert_jcs_interop_domain(payload)
    try:
        return rfc8785.dumps(payload).decode("utf-8")
    except rfc8785.CanonicalizationError as exc:
        raise CompileError(f"Contract cannot be canonicalized as RFC 8785 JSON: {exc}") from exc


def contract_sha256(
    contract: ResolvedVoiceContract,
    *,
    profile: str | None = None,
    audience: str | None = None,
    surface: str | None = None,
    tone: str | None = None,
) -> str:
    canonical = canonical_contract_json(
        contract,
        profile=profile,
        audience=audience,
        surface=surface,
        tone=tone,
    )
    return sha256(canonical.encode("utf-8")).hexdigest()


def compile_contract(
    contract: ResolvedVoiceContract,
    *,
    profile: str | None = None,
    audience: str | None = None,
    surface: str | None = None,
    tone: str | None = None,
    output_format: str = "prompt",
    compact: bool = False,
    max_chars: int | None = None,
    include_provenance: bool = False,
) -> str:
    if output_format not in SUPPORTED_OUTPUT_FORMATS:
        raise CompileError(f"Unknown output format: {output_format}")

    _require_selected_contract(
        contract,
        profile=profile,
        audience=audience,
        surface=surface,
        tone=tone,
    )

    active_profile = profile
    if active_profile is None:
        profiles = contract.data.get("profiles", {})
        if isinstance(profiles, dict) and "default" in profiles:
            active_profile = "default"
    selected, audience, surface, tone = _apply_profile(
        contract.data,
        profile=profile,
        audience=audience,
        surface=surface,
        tone=tone,
    )

    if max_chars is not None and max_chars < 256:
        raise CompileError("max_chars must be at least 256")

    if output_format == "canonical-json":
        return canonical_contract_json(
            contract,
            profile=profile,
            audience=audience,
            surface=surface,
            tone=tone,
        )
    if output_format == "sha256":
        return contract_sha256(
            contract,
            profile=profile,
            audience=audience,
            surface=surface,
            tone=tone,
        )

    if output_format == "json":
        payload = {
            "contract": selected,
            "markdown_bodies": [body for _, body in contract.bodies],
            "active": {
                "profile": profile,
                "audience": audience,
                "surface": surface,
                "tone": tone,
            },
        }
        if include_provenance:
            payload["provenance"] = {
                "markdown_bodies": [
                    {"source": str(path), "content": body} for path, body in contract.bodies
                ],
                "sources": [str(path) for path in contract.source_paths()],
            }
        payload["active"]["profile"] = active_profile
        return _json_dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)

    if compact:
        lines = [
            "VOICE CONTRACT. Apply only to human-facing natural language.",
            "Higher-priority safety, policy, factual, tool, and output-schema instructions win.",
        ]
        for key in (
            "identity",
            "response",
            "language",
            "lexicon",
            "epistemics",
            "interaction",
            "formatting",
            "speech",
        ):
            lines.extend(_compact_mapping(selected.get(key), f"{key}."))
        rules = selected.get("rules", [])
        for rule in rules if isinstance(rules, list) else []:
            if isinstance(rule, dict) and rule.get("disabled") is not True:
                instruction = rule.get("instruction") or rule.get("description")
                if instruction:
                    lines.append(f"rule.{rule.get('id', 'unnamed')}={instruction}")
        if contract.body:
            lines.extend(["Additional guidance:", contract.body])
    else:
        lines = [
            "# Active VOICE.md communication contract",
            "",
            (
                "This contract controls communication behavior only. It never overrides higher-priority "
                "system/developer instructions, safety policy, permissions, factual requirements, tool "
                "contracts, exact quotations, or required machine-readable schemas."
            ),
        ]
        if any((active_profile, audience, surface, tone)):
            lines.extend(
                [
                    "",
                    "## Active context",
                    f"- profile: {active_profile or 'none'}",
                    f"- audience: {audience or 'default'}",
                    f"- surface: {surface or 'default'}",
                    f"- tone: {tone or 'default'}",
                ]
            )
        section_map = (
            ("Activation", "activation"),
            ("Authority boundary", "authority"),
            ("Core identity", "identity"),
            ("Response behavior", "response"),
            ("Language", "language"),
            ("Lexicon", "lexicon"),
            ("Epistemic behavior", "epistemics"),
            ("Interaction behavior", "interaction"),
            ("Formatting", "formatting"),
            ("Speech and audio", "speech"),
            ("Runtime constraints", "runtime"),
        )
        for title, key in section_map:
            section = _mapping(title, selected.get(key))
            if section:
                lines.extend(["", *section])
        rules = selected.get("rules", [])
        active_rules = (
            [
                rule
                for rule in rules
                if isinstance(rule, dict) and rule.get("disabled") is not True
            ]
            if isinstance(rules, list)
            else []
        )
        rule_lines = _bullets("Explicit rules", active_rules)
        if rule_lines:
            lines.extend(["", *rule_lines])
        if contract.bodies:
            lines.extend(
                [
                    "",
                    "## Additional Markdown guidance",
                    "Later source blocks are more specific and override conflicting earlier blocks.",
                ]
            )
            for path, body in contract.bodies:
                if include_provenance:
                    lines.extend(["", f"### Source: {path}", body])
                else:
                    lines.extend(["", body])

    result = "\n".join(lines).strip(VOICE_TRIM_CHARS)
    if max_chars is None:
        runtime = selected.get("runtime", {})
        if isinstance(runtime, dict) and isinstance(runtime.get("max_prompt_chars"), int):
            max_chars = runtime["max_prompt_chars"]
    if max_chars is not None and max_chars < 256:
        raise CompileError("runtime.max_prompt_chars must be at least 256")
    if output_format in {"nemotron", "nemotron-ascii", "ascii"}:
        result = to_ascii(result)
        if not result.isascii():
            raise CompileError("ASCII compilation failed to remove all non-ASCII characters")
    if max_chars is not None and len(result) > max_chars:
        suffix = "\n[VOICE.md prompt truncated to configured character budget.]"
        result = result[: max(0, max_chars - len(suffix))].rstrip(VOICE_TRIM_CHARS) + suffix
    return result
