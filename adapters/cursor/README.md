# Cursor adapter

Install an Agent Skill:

```bash
voicemd install --target cursor --mode auto
```

`auto` installs `.cursor/skills/voice-contract/SKILL.md`. Explicit mode adds
`disable-model-invocation: true`; invoke it with `/voice-contract`. `always` also
installs an `alwaysApply: true` rule. Mode transitions remove the obsolete rule
when it is still byte-for-byte owned by VoiceMD.
