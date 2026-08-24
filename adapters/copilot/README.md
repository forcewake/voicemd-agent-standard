# GitHub Copilot adapter

Install the universal Agent Skill and repository bootstrap:

```bash
voicemd install --target copilot --mode auto
```

The exact feature set varies across Copilot surfaces. This adapter is a portability layer and does not claim native recognition of the VOICE.md filename.

For Copilot CLI explicit invocation:

```bash
voicemd install --target copilot --mode explicit
```

Then invoke `/voice-contract`. The shared skill sets
`disable-model-invocation: true`, and no repository custom-instructions block is
installed. Other Copilot surfaces may not expose the same skill command.
