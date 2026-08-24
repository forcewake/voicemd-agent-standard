# Primary references

Checked on 2026-08-24 unless otherwise stated.

## Data formats and canonicalization

- RFC 8785, JSON Canonicalization Scheme (JCS): https://www.rfc-editor.org/rfc/rfc8785.html
- YAML 1.2.2 specification: https://yaml.org/spec/1.2.2/
- JSON Schema Draft 2020-12: https://json-schema.org/draft/2020-12
- JSON Schema Draft 2020-12 meta-schema: https://json-schema.org/draft/2020-12/schema

VoiceMD structured frontmatter uses the YAML 1.2 JSON schema subset. The resolved contract is validated against the packaged Draft 2020-12 schema. Portable canonical selected-contract bytes use RFC 8785 JCS after an additional VoiceMD safe-integer interoperability check; that narrower numeric policy is a VoiceMD rule, not a requirement imposed by RFC 8785.

## Agent instructions and skills

- OpenAI Codex, AGENTS.md: https://developers.openai.com/codex/agent-configuration/agents-md
- OpenAI Codex, skills: https://developers.openai.com/codex/skills
- Agent Skills open specification: https://agentskills.io/specification
- Claude Code memory/imports: https://code.claude.com/docs/en/memory
- Gemini CLI configuration: https://geminicli.com/docs/reference/configuration/
- Gemini CLI Agent Skills: https://geminicli.com/docs/cli/tutorials/skills-getting-started/
- Cursor skills: https://cursor.com/docs/skills
- Cursor rules: https://cursor.com/docs/rules
- GitHub Copilot repository instructions: https://docs.github.com/en/copilot/customizing-copilot/adding-repository-custom-instructions-for-github-copilot
- GitHub Copilot skills: https://docs.github.com/en/copilot/concepts/agents/about-agent-skills
- Cline rules: https://docs.cline.bot/features/cline-rules
- Cline skills: https://docs.cline.bot/features/skills
- Windsurf skills: https://docs.windsurf.com/windsurf/cascade/skills
- OpenCode rules: https://opencode.ai/docs/rules/
- OpenCode skills: https://opencode.ai/docs/skills/
- Aider conventions: https://aider.chat/docs/usage/conventions.html

## NVIDIA NemotronLabs VoiceChat

- Model card: https://huggingface.co/nvidia/NVIDIA-NemotronLabs-VoiceChat-11B
- NVIDIA NeMo Speech branch: https://github.com/NVIDIA-NeMo/Speech/tree/nemotron-labs-voicechat
- Realtime API reference: https://github.com/NVIDIA-NeMo/Speech/blob/nemotron-labs-voicechat/voicechat_realtime_instructions/api-reference.md

## Azure OpenAI evaluation transport

- REST authentication and API versioning: https://learn.microsoft.com/azure/ai-foundry/openai/reference

## Prior art

- Efeonce `voice.md`: https://github.com/efeoncepro/voice.md

These references document integration substrates and prior art. They do not imply vendor adoption of this specification.
