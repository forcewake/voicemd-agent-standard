# OpenAI Codex adapter

Recommended:

```bash
voicemd install --target codex --mode auto
```

This creates the universal `.agents/skills/voice-contract/SKILL.md` and injects a small managed section into `AGENTS.md`.

Explicit invocation:

```bash
voicemd install --target codex --mode explicit
```

Then invoke `$voice-contract`. Explicit mode removes the managed `AGENTS.md`
bootstrap and creates
`.agents/skills/voice-contract/agents/openai.yaml` with
`policy.allow_implicit_invocation: false`. Merely writing `@voice` does not load a
skill that this Codex policy keeps out of model context.

Codex can be configured with fallback instruction filenames, but each directory contributes at most one instruction file and `AGENTS.md` is checked before fallbacks. Therefore `VOICE.md` as a fallback is not a reliable replacement for the skill/bootstrap pattern in repositories that already use `AGENTS.md`.

Optional user configuration is in `config.toml.example`.
