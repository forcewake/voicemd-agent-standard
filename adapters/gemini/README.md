# Gemini CLI adapter

Gemini CLI discovers `.agents/skills` as an alias, so the universal skill is the default on-demand path:

```bash
voicemd install --target gemini --mode auto
```

For always-loaded context, merge the `context.fileName` property from `settings.json.example` into the applicable Gemini settings file. Do not overwrite existing settings.
