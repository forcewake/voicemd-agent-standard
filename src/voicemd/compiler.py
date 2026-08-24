from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, Iterable

from .ascii import to_ascii
from .merge import deep_merge
from .model import ResolvedVoiceContract


class CompileError(ValueError):
    pass


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
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


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
    selected = deepcopy(data)
    profile_overrides: dict[str, Any] = {}
    if profile:
        profiles = selected.get("profiles", {})
        if profile not in profiles:
            raise CompileError(f"Unknown profile: {profile}")
        profile_data = profiles[profile]
        if not isinstance(profile_data, dict):
            raise CompileError(f"Profile '{profile}' must be a mapping")
        audience = audience or profile_data.get("audience")
        surface = surface or profile_data.get("surface")
        tone = tone or profile_data.get("tone")
        raw_overrides = profile_data.get("overrides", {})
        if not isinstance(raw_overrides, dict):
            raise CompileError(f"Profile '{profile}' overrides must be a mapping")
        profile_overrides = raw_overrides

    # Named variants establish the selected context. Profile-local overrides are
    # applied last because they are the most specific part of a profile.
    for category, name in (("audiences", audience), ("surfaces", surface), ("tones", tone)):
        if name:
            variants = selected.get(category, {})
            if name not in variants:
                raise CompileError(f"Unknown {category[:-1]}: {name}")
            selected = deep_merge(selected, variants[name])
    selected = deep_merge(selected, profile_overrides)
    return selected, audience, surface, tone


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
    selected, audience, surface, tone = _apply_profile(
        contract.data,
        profile=profile,
        audience=audience,
        surface=surface,
        tone=tone,
    )

    if max_chars is not None and max_chars < 256:
        raise CompileError("max_chars must be at least 256")

    if output_format == "json":
        payload = {
            "contract": selected,
            "markdown_bodies": [
                {"source": str(path), "content": body} for path, body in contract.bodies
            ],
            "active": {
                "profile": profile,
                "audience": audience,
                "surface": surface,
                "tone": tone,
            },
            "sources": [str(path) for path in contract.source_paths()],
        }
        return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)

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
            if isinstance(rule, dict) and not rule.get("disabled"):
                instruction = rule.get("instruction") or rule.get("description")
                if instruction:
                    lines.append(f"rule.{rule.get('id', 'unnamed')}={instruction}")
        if contract.body:
            lines.extend(["Additional guidance:", contract.body])
    else:
        lines = [
            "# Active VOICE.md communication contract",
            "",
            "This contract controls communication behavior only. It never overrides higher-priority "
            "system/developer instructions, safety policy, permissions, factual requirements, tool "
            "contracts, exact quotations, or required machine-readable schemas.",
        ]
        if any((profile, audience, surface, tone)):
            lines.extend(
                [
                    "",
                    "## Active context",
                    f"- profile: {profile or 'default'}",
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
        rule_lines = _bullets("Explicit rules", selected.get("rules", []))
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

    result = "\n".join(lines).strip()
    if max_chars is None:
        runtime = selected.get("runtime", {})
        if isinstance(runtime, dict) and isinstance(runtime.get("max_prompt_chars"), int):
            max_chars = runtime["max_prompt_chars"]
    if max_chars is not None and max_chars < 256:
        raise CompileError("runtime.max_prompt_chars must be at least 256")
    if max_chars is not None and len(result) > max_chars:
        suffix = "\n[VOICE.md prompt truncated to configured character budget.]"
        result = result[: max(0, max_chars - len(suffix))].rstrip() + suffix
    if output_format in {"nemotron", "nemotron-ascii", "ascii"}:
        result = to_ascii(result)
        if not result.isascii():
            raise CompileError("ASCII compilation failed to remove all non-ASCII characters")
    elif output_format != "prompt":
        raise CompileError(f"Unknown output format: {output_format}")
    return result
