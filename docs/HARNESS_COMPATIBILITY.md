# Harness compatibility

Verified against official documentation available on 2026-08-24. Product behavior may change; rerun compatibility checks before publishing a release.

“Supported” below means this package provides a practical adapter. It does not mean the vendor natively recognizes the `VOICE.md` filename.

## Integration strategy

| Harness | On-demand path | Always-loaded path | Package files |
|---|---|---|---|
| OpenAI Codex | `.agents/skills/voice-contract/SKILL.md` plus small `AGENTS.md` bootstrap | `AGENTS.md` instructs reading `VOICE.md`; optional fallback config when no `AGENTS.md` exists | `.agents/skills`, `AGENTS.md`, `adapters/codex/` |
| Claude Code | `.claude/skills/voice-contract/SKILL.md` | `CLAUDE.md` import with `@VOICE.md` | `.claude/skills`, `CLAUDE.md`, `adapters/claude/` |
| Gemini CLI | `.agents/skills` alias or `.gemini/skills` | `GEMINI.md`/configured context file | `.agents/skills`, `GEMINI.md`, `adapters/gemini/` |
| Cursor | Agent-requested `.cursor/rules/*.mdc` | same rule with `alwaysApply: true` | `.cursor/rules/voice-contract.mdc` |
| GitHub Copilot | Agent Skill plus repository instruction bootstrap | repository instructions | `.agents/skills`, `.github/copilot-instructions.md` |
| Cline | `.cline/skills` plus rule | `.clinerules` rule | `.cline/skills`, `.clinerules/voice-contract.md` |
| Windsurf | `.agents/skills` plus rule | `.windsurf/rules` | `.agents/skills`, `.windsurf/rules/voice-contract.md` |
| OpenCode | `.agents/skills` plus `AGENTS.md` bootstrap | configuration `instructions` entry | `.agents/skills`, `AGENTS.md`, `adapters/opencode/` |
| Aider | no native on-demand semantic selector in this pack | read-only conventions file through dedicated config | `.aider.voice.yml` |
| Generic harness | execute CLI, read file, call HTTP/MCP | inject compiled system prompt | `integrations/` |

## OpenAI Codex

Codex reads `AGENTS.md` before work and merges project instructions from root to current directory. In each directory it checks `AGENTS.override.md`, `AGENTS.md`, then configured fallback filenames, selecting at most one file per directory. Because fallback names are considered only after the AGENTS candidates, adding `VOICE.md` as a fallback is not sufficient in repositories that already have `AGENTS.md`.

The recommended adapter is therefore:

1. canonical skill under `.agents/skills/voice-contract/SKILL.md`;
2. a short managed `AGENTS.md` bootstrap that activates it for human-facing output;
3. the full `VOICE.md` discovered by the skill or compiled by the CLI.

Optional user config:

```toml
# ~/.codex/config.toml
# Useful only as an additional fallback; do not rely on it when AGENTS.md exists.
project_doc_fallback_filenames = ["VOICE.md"]
```

Official references:

- https://developers.openai.com/codex/agent-configuration/agents-md
- https://developers.openai.com/codex/build-skills

## Claude Code

Claude Code loads `CLAUDE.md` and supports file imports with `@path/to/import`. It also supports skills. On-demand mode uses a skill and small bootstrap; always mode can add `@VOICE.md` to `CLAUDE.md`.

Official reference:

- https://code.claude.com/docs/en/memory

## Gemini CLI

Gemini CLI can configure one or multiple context filenames and supports Agent Skills under `.gemini/skills` and the `.agents/skills` alias. The universal skill path is therefore sufficient for on-demand integration.

An always-loaded configuration can use:

```json
{
  "context": {
    "fileName": ["GEMINI.md", "VOICE.md"]
  }
}
```

Do not replace an existing settings file blindly; merge this property through the project's normal configuration management.

Official references:

- https://geminicli.com/docs/reference/configuration/
- https://geminicli.com/docs/cli/tutorials/skills-getting-started/

## Cursor

Cursor rules are the least-common-denominator path. The generated `.mdc` rule is not always active by default; its description tells the agent when to use it. Set `--mode always` only when the context cost is acceptable.

Official reference:

- https://docs.cursor.com/context/rules

## GitHub Copilot

The package uses the shared Agent Skills path and repository custom instructions. Different Copilot surfaces can have different feature availability; treat the managed bootstrap as a portability layer rather than proof of native VOICE.md support.

Official references:

- https://docs.github.com/en/copilot/customizing-copilot/adding-repository-custom-instructions-for-github-copilot
- https://docs.github.com/en/copilot/customizing-copilot/extending-copilot-coding-agent-with-skills

## Cline

Cline supports rules and skills. The pack installs both a skill and a concise rule because deployed versions and organization settings can differ.

Official references:

- https://docs.cline.bot/features/cline-rules
- https://docs.cline.bot/features/skills

## Windsurf

Windsurf supports skills and can discover the `.agents/skills` alias. The additional rule makes activation intent visible.

Official reference:

- https://docs.windsurf.com/windsurf/cascade/skills

## OpenCode

OpenCode supports `AGENTS.md`, configured instruction files, and skills. Use the universal skill plus bootstrap for contextual mode. An explicit always-loaded example is under `adapters/opencode/`.

Official references:

- https://opencode.ai/docs/rules/
- https://opencode.ai/docs/skills/

## Aider

The generated `.aider.voice.yml` reads `VOICE.md` as a conventions file:

```bash
aider --config .aider.voice.yml
```

This is always-loaded, not progressive disclosure. Keep the contract compact or use a compiled artifact.

Official reference:

- https://aider.chat/docs/usage/conventions.html

## Reliability levels

Adapters should be described using one of these labels:

- **native:** harness explicitly defines VOICE.md semantics;
- **skill:** harness discovers the standard Agent Skill and activates it contextually;
- **bootstrap:** a native instructions file tells the harness when to read the contract;
- **import:** the contract is always loaded through an include/import mechanism;
- **application:** the host compiles and injects the contract;
- **manual:** user explicitly selects or reads it.

At this draft date, the package does not claim `native` status for any major vendor harness.
