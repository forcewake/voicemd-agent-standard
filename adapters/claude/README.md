# Claude Code adapter

On-demand:

```bash
voicemd install --target claude --mode auto
```

Always loaded:

```bash
voicemd install --target claude --mode always
```

Always mode adds `@VOICE.md` inside the managed `CLAUDE.md` block. Relative imports resolve from the importing file. Keep the imported contract concise enough for the project context budget.

Explicit invocation:

```bash
voicemd install --target claude --mode explicit
```

Then invoke `/voice-contract`. The installed skill has
`disable-model-invocation: true`, and the installer removes any prior managed
`CLAUDE.md` bootstrap or `@VOICE.md` import.
