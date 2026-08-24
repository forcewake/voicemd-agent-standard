# Harness compatibility

Verified against official documentation available on 2026-08-24. Product behavior may change; rerun compatibility checks before publishing a release.

“Supported” below means this package provides a practical adapter. It does not mean the vendor natively recognizes the `VOICE.md` filename.

## Integration strategy

| Harness | On-demand path | Always-loaded path | Package files |
|---|---|---|---|
| OpenAI Codex | `.agents/skills/voice-contract/SKILL.md` plus small `AGENTS.md` bootstrap | `AGENTS.md` instructs reading `VOICE.md`; explicit uses `$voice-contract` and `agents/openai.yaml` | `.agents/skills`, `AGENTS.md`, `adapters/codex/` |
| Claude Code | `.claude/skills/voice-contract/SKILL.md`; explicit uses `/voice-contract` | `CLAUDE.md` import with `@VOICE.md` | `.claude/skills`, `CLAUDE.md`, `adapters/claude/` |
| Gemini CLI | `.agents/skills` alias or `.gemini/skills` | `GEMINI.md`/configured context file | `.agents/skills`, `GEMINI.md`, `adapters/gemini/` |
| Cursor | `.cursor/skills/voice-contract/SKILL.md`; explicit uses `/voice-contract` | `alwaysApply: true` rule | `.cursor/skills`, `.cursor/rules/voice-contract.mdc` |
| GitHub Copilot | Agent Skill plus repository instruction bootstrap; CLI explicit uses `/voice-contract` | repository instructions | `.agents/skills`, `.github/copilot-instructions.md` |
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

With `--mode explicit`, the installer omits the `AGENTS.md` block and writes
`agents/openai.yaml` inside the skill with
`policy.allow_implicit_invocation: false`. Invoke `$voice-contract`; `@voice` by
itself cannot inject a skill that is hidden from implicit model invocation.

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

Claude Code loads `CLAUDE.md` and supports file imports with `@path/to/import`. It also supports skills. On-demand mode uses a skill and small bootstrap; always mode can add `@VOICE.md` to `CLAUDE.md`. Explicit mode removes that bootstrap and sets `disable-model-invocation: true` in the skill; invoke `/voice-contract`.

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

Cursor now supports Agent Skills directly. `auto` installs a model-invocable
`.cursor/skills/voice-contract/SKILL.md`; `explicit` sets
`disable-model-invocation: true` and requires `/voice-contract`. Only `always`
also installs the `.mdc` rule with `alwaysApply: true`.

Official reference:

- https://cursor.com/docs/skills

## GitHub Copilot

The package uses the shared Agent Skills path and repository custom instructions. In explicit mode, `disable-model-invocation: true` prevents Copilot CLI from selecting the skill automatically; invoke `/voice-contract`. Different Copilot surfaces can have different feature availability, so treat the managed bootstrap as a portability layer rather than proof of native VOICE.md support.

Official references:

- https://docs.github.com/en/copilot/customizing-copilot/adding-repository-custom-instructions-for-github-copilot
- https://docs.github.com/en/copilot/concepts/agents/about-agent-skills

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

The dedicated config is not discovered automatically. Starting Aider with that
command is the explicit opt-in; the contract is then always loaded for that
session. `--mode auto` and `--mode always` cannot change this Aider limitation,
and the installer emits a warning. Keep the contract compact or use a compiled
artifact.

## Installer mode and ownership constraints

Codex, Gemini CLI, GitHub Copilot, Windsurf, OpenCode, and the universal target
share `.agents/skills/voice-contract`. `auto` and `always` can coexist because
their skill content is identical. `explicit` cannot coexist with either implicit
mode: the shared file cannot be both model-invocable and explicit-only.

The universal, Codex, and OpenCode targets additionally share one `AGENTS.md`
block. Their non-explicit modes must be identical. Conflicts fail during preflight
before any adapter or state file is written.

Install state version 2 records each generated file hash or managed-block hash.
Modified owned content is never silently overwritten. Uninstall preserves it as
`modified-retained` and relinquishes ownership. All artifact paths and their
parent directories must be real paths under the resolved install root; symlinks
are rejected. File replacements are atomic, and a multi-file failure rolls back
earlier writes.

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
