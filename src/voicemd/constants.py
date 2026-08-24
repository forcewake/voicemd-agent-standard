from __future__ import annotations

import re

SPEC_VERSION = "0.1"
SPEC_VERSION_PATTERN = re.compile(r"^0\.1(?:\.[0-9]+)?$")
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

# Canonical authority capabilities. Contracts may use the documented aliases
# below, but validators compare their semantic category rather than relying on
# spelling alone.
PROTECTED_AUTHORITY_CAPABILITIES = {
    "facts",
    "safety",
    "legal_compliance",
    "permissions",
    "tools",
    "secrets",
    "hidden_reasoning",
    "exact_quotations",
    "required_output_schemas",
}

AUTHORITY_CAPABILITY_ALIASES = {
    "facts": "facts",
    "fact": "facts",
    "source truth": "facts",
    "factual truth": "facts",
    "safety": "safety",
    "safety policy": "safety",
    "policy": "safety",
    "legal": "legal_compliance",
    "compliance": "legal_compliance",
    "legal compliance": "legal_compliance",
    "legal or compliance requirements": "legal_compliance",
    "legal regulatory or compliance obligations": "legal_compliance",
    "permissions": "permissions",
    "permission": "permissions",
    "approval requirements": "permissions",
    "permissions or approval requirements": "permissions",
    "tools": "tools",
    "tool selection": "tools",
    "tool availability": "tools",
    "tool availability selection parameters or side effects": "tools",
    "secrets": "secrets",
    "access to secrets": "secrets",
    "hidden reasoning": "hidden_reasoning",
    "exact quotes": "exact_quotations",
    "exact quotations": "exact_quotations",
    "required schemas": "required_output_schemas",
    "schemas": "required_output_schemas",
    "required output schemas": "required_output_schemas",
    "required machine readable schemas": "required_output_schemas",
}
