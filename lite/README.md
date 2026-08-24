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
- treats the first existing candidate as authoritative even when it is empty, so an empty `VOICE.override.md` shadows lower-priority files in the same directory;
- resolves the project root, start directory, candidate parents, and candidate files canonically; a file or directory symlink may stay inside that root but cannot widen it, and an unsafe or broken active candidate fails closed;
- concatenates raw files broad-to-specific;
- does not parse YAML, `extends`, profiles, or tests;
- does not validate authority rules;
- provides `should_apply` (Python) and `shouldApply` (Node.js), which apply only to
  the documented, case-insensitive human-facing output kinds and fail closed for
  exact, machine-readable, or unknown kinds;
- leaves profile- and marker-aware activation to the full runtime.

Move to the full CLI when hierarchy, profile selection, linting, ASCII compilation, or governance matters.
