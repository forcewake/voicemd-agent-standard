# Harness adapters

The canonical portable adapter is `../.agents/skills/voice-contract/SKILL.md`. Harness-specific directories document native discovery and provide snippets for cases where progressive disclosure is unavailable or an always-loaded contract is desired.

Use the installer instead of manually copying where possible:

```bash
voicemd install --target all --mode auto
```

Modes:

- `auto`: small bootstrap plus a model-invocable skill;
- `always`: contract is requested/imported for every task, while machine-output exclusions still apply;
- `explicit`: no instruction bootstrap; invoke the installed skill with the harness-native command.

In explicit mode use `$voice-contract` in Codex and `/voice-contract` in Claude Code,
GitHub Copilot CLI, or Cursor. `@voice` and `voice:on` remain portable request markers,
but cannot load a skill that a harness has hidden from model invocation.

Several targets share `.agents/skills/voice-contract`. They may mix `auto` and
`always`, because those modes use the same skill content. `explicit` cannot share
that file with either implicit mode. The `universal`, `codex`, and `opencode`
targets also share one `AGENTS.md` block and must use the same `auto` or `always`
mode. The installer rejects conflicts during preflight without changing files.

The installer rejects symlinked artifact paths, applies a preflighted transaction,
and records artifact SHA-256 ownership in `.voicemd/install-state.json`. Reinstall
does not overwrite a modified managed artifact. Uninstall preserves modified files
or blocks and reports `modified-retained`.
