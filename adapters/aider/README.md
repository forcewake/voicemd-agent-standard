# Aider adapter

```bash
voicemd install --target aider --mode explicit

aider --config .aider.voice.yml
```

Aider does not auto-discover `.aider.voice.yml`. The file is inert until the
explicit `aider --config .aider.voice.yml` launch, after which `VOICE.md` is loaded
as conventions for that session. The installer warns when this target is selected:
`auto` and `always` cannot make the dedicated config automatic by themselves. For
a large contract, point the config to a compact compiled artifact instead.
