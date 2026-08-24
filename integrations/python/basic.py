"""Minimal direct integration."""

from voicemd import compile_voice, lint_voice_text

BASE_SYSTEM_PROMPT = "You are the architecture review agent. Follow approved tool and data policies."

voice_prompt = compile_voice(
    path="VOICE.md",
    profile="architecture_review",
)

messages = [
    {"role": "system", "content": BASE_SYSTEM_PROMPT},
    {"role": "system", "content": voice_prompt},
    {"role": "user", "content": "Review the proposed architecture."},
]

# Send `messages` through the model SDK used by the application.
print(messages[1]["content"][:500])

# After generation:
# issues = lint_voice_text(model_output, path="VOICE.md", profile="architecture_review")
