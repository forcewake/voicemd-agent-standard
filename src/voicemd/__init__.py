"""VOICE.md reference implementation."""

from .api import compile_voice, discover_voice, lint_voice_text, load_voice
from .model import ResolvedVoiceContract, SourceDocument

__all__ = [
    "ResolvedVoiceContract",
    "SourceDocument",
    "compile_voice",
    "discover_voice",
    "lint_voice_text",
    "load_voice",
]

__version__ = "0.1.0a1"
