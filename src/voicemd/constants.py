from __future__ import annotations

SPEC_VERSION = "0.1"
KIND = "VoiceContract"
DEFAULT_FILENAMES = (
    "VOICE.override.md",
    "VOICE.md",
    ".voice/VOICE.override.md",
    ".voice/VOICE.md",
)
GLOBAL_HOME_ENV = "VOICE_MD_HOME"
EXPLICIT_PATH_ENV = "VOICE_MD"
PROJECT_ROOT_ENV = "VOICE_MD_ROOT"
MANAGED_START = "<!-- voicemd:start -->"
MANAGED_END = "<!-- voicemd:end -->"

HUMAN_FACING_KINDS = {
    "chat",
    "message",
    "email",
    "document",
    "report",
    "summary",
    "explanation",
    "ui_copy",
    "spoken",
    "speech",
}
MACHINE_FACING_KINDS = {
    "code",
    "patch",
    "diff",
    "json",
    "xml",
    "yaml",
    "sql",
    "tool_call",
    "tool_result",
    "structured_data",
    "exact_quote",
    "raw_data",
}
