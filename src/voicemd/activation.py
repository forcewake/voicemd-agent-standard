from __future__ import annotations

import re
from dataclasses import dataclass

from .compiler import resolve_context
from .constants import HUMAN_FACING_KINDS, MACHINE_FACING_KINDS
from .contract import ContractError
from .model import ResolvedVoiceContract


@dataclass(frozen=True)
class ActivationDecision:
    apply: bool
    reason: str
    mode: str


def _strings(value: object, fallback: set[str]) -> set[str]:
    if value is None:
        return set(fallback)
    if not isinstance(value, list):
        return set()
    return {str(item).strip().casefold() for item in value if str(item).strip()}


def _has_marker(text: str | None, markers: object) -> bool:
    if not text or not isinstance(markers, list):
        return False
    folded = text.casefold()
    for marker in markers:
        value = str(marker).strip().casefold()
        if not value:
            continue
        pattern = rf"(?<![\w@:+-]){re.escape(value)}(?![\w@:+-])"
        if re.search(pattern, folded):
            return True
    return False


def decide_activation(
    contract: ResolvedVoiceContract,
    output_kind: str,
    *,
    exact_output: bool = False,
    enabled: bool = True,
    explicit: bool = False,
    marker_text: str | None = None,
    profile: str | None = None,
    audience: str | None = None,
    surface: str | None = None,
    tone: str | None = None,
) -> ActivationDecision:
    """Return a deterministic activation decision for one output artifact.

    Application controls, exact-output requirements, contract mode, exclusions,
    and explicit markers are evaluated in that order. Exclusion and off markers
    win conflicts because VOICE.md must not mutate exact or machine output.
    """

    from .validator import validate_selected_contract

    validation = validate_selected_contract(
        contract,
        profile=profile,
        audience=audience,
        surface=surface,
        tone=tone,
        strict=False,
    )
    if not validation.ok:
        raise ContractError(
            "selected VOICE.md failed validation: " + "; ".join(validation.errors)
        )

    selected = resolve_context(
        contract,
        profile=profile,
        audience=audience,
        surface=surface,
        tone=tone,
    )
    activation = selected.get("activation")
    if not isinstance(activation, dict):
        activation = {}
    mode = str(activation.get("mode") or "contextual").strip().casefold()
    kind = output_kind.strip().casefold()

    if not enabled:
        return ActivationDecision(False, "disabled by application", mode)
    if exact_output:
        return ActivationDecision(False, "exact output required", mode)
    if mode == "off":
        return ActivationDecision(False, "contract activation is off", mode)

    include = _strings(activation.get("include"), HUMAN_FACING_KINDS)
    exclude = _strings(activation.get("exclude"), MACHINE_FACING_KINDS)
    if kind in exclude or kind in MACHINE_FACING_KINDS:
        return ActivationDecision(False, f"excluded output kind: {kind}", mode)

    off_marker = _has_marker(marker_text, activation.get("off_markers", ["@no-voice", "voice:off"]))
    if off_marker:
        return ActivationDecision(False, "explicit off marker", mode)
    selected = explicit or _has_marker(
        marker_text, activation.get("on_markers", ["@voice", "voice:on"])
    )

    if mode == "explicit":
        return ActivationDecision(selected, "explicit selection" if selected else "explicit mode", mode)
    if mode == "always":
        return ActivationDecision(True, "always mode", mode)
    if mode != "contextual":
        return ActivationDecision(False, f"unsupported activation mode: {mode}", mode)
    if selected:
        return ActivationDecision(True, "explicit selection", mode)
    if kind in include or kind in HUMAN_FACING_KINDS:
        return ActivationDecision(True, f"human-facing output kind: {kind}", mode)
    return ActivationDecision(False, f"output kind is not human-facing: {kind}", mode)


def should_apply_voice(
    contract: ResolvedVoiceContract,
    output_kind: str,
    *,
    exact_output: bool = False,
    enabled: bool = True,
    explicit: bool = False,
    marker_text: str | None = None,
    profile: str | None = None,
    audience: str | None = None,
    surface: str | None = None,
    tone: str | None = None,
) -> bool:
    return decide_activation(
        contract,
        output_kind,
        exact_output=exact_output,
        enabled=enabled,
        explicit=explicit,
        marker_text=marker_text,
        profile=profile,
        audience=audience,
        surface=surface,
        tone=tone,
    ).apply
