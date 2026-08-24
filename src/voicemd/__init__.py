"""VOICE.md reference implementation."""

from .activation import ActivationDecision, decide_activation, should_apply_voice
from .api import compile_voice, discover_voice, lint_voice_text, load_voice, require_valid_voice
from .compiler import canonical_contract_json, contract_sha256, resolve_context
from .model import ResolvedVoiceContract, SourceDocument

__all__ = [
    "ActivationDecision",
    "ResolvedVoiceContract",
    "SourceDocument",
    "canonical_contract_json",
    "compile_voice",
    "contract_sha256",
    "decide_activation",
    "discover_voice",
    "lint_voice_text",
    "load_voice",
    "require_valid_voice",
    "resolve_context",
    "should_apply_voice",
]

__version__ = "0.1.0a3"
