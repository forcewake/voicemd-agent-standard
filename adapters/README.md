# Harness adapters

The canonical portable adapter is `../.agents/skills/voice-contract/SKILL.md`. Harness-specific directories document native discovery and provide snippets for cases where progressive disclosure is unavailable or an always-loaded contract is desired.

Use the installer instead of manually copying where possible:

```bash
voicemd install --target all --mode auto
```

Modes:

- `auto`: small bootstrap plus on-demand skill/rule;
- `always`: contract is requested/imported for every task but exclusions still apply;
- `explicit`: install discoverable skills/files without changing instruction bootstraps.

The installer uses managed markers and refuses to overwrite unmanaged generated files.
