# VoiceMD Lite

This path has no Python package dependencies and no YAML/schema behavior. It is for projects that only need a readable `VOICE.md` and deterministic file discovery.

## Python standard library

```python
from voice_loader import load_voice, should_apply

if should_apply("chat"):
    system_prompt += "\n\n" + load_voice()
```

## Shell

```bash
VOICE_PROMPT="$(./load-voice.sh)"
```

Lite behavior:

- finds `VOICE.override.md`, `VOICE.md`, `.voice/VOICE.override.md`, or `.voice/VOICE.md` from `VOICE_MD_ROOT`, `.voicemd-root`, a VCS root, or a common project manifest to the current directory;
- concatenates raw files broad-to-specific;
- does not parse YAML, `extends`, profiles, or tests;
- does not validate authority rules;
- leaves runtime activation to the application.

Move to the full CLI when hierarchy, profile selection, linting, ASCII compilation, or governance matters.
