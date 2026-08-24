# VoiceMD: the `VOICE.md` Agent Communication Contract

**Status:** independent draft `0.1.0-draft.1`, dated 2026-08-24. It is usable, tested, and intentionally not presented as an adopted industry standard.

Russian entry point: [`START_HERE_RU.md`](START_HERE_RU.md). Full inventory: [`PACKAGE_CONTENTS.md`](PACKAGE_CONTENTS.md).

VoiceMD defines a vendor-neutral, version-controlled contract for **how an AI agent communicates**. It separates communication behavior from agent capability, product design, narrative, safety, and tool policy:

```text
AGENTS.md      what the agent does and how it works
DESIGN.md      how the product looks and behaves visually
STORYLINE.md   how the experience or argument unfolds
VOICE.md       how the agent communicates and interacts
```

A `VOICE.md` can be plain Markdown, structured YAML plus Markdown, or an executable/testable contract. The same source can drive coding agents, application agents, cloud APIs, OpenAI-compatible servers, small local text models, and real-time speech models.

## Why this exists

“Friendly, concise, professional” is not a useful behavioral specification. It does not tell a model how to disagree, express uncertainty, adapt to an executive versus an engineer, speak through TTS, handle repeated requests for certainty, or avoid changing machine-readable output.

VoiceMD makes those behaviors explicit and testable:

- linguistic voice and register;
- epistemic behavior: certainty, uncertainty, sourcing, correction;
- interaction behavior: disagreement, challenge, clarification, escalation;
- audience, surface, tone, and runtime profiles;
- spoken-dialogue and TTS constraints;
- deterministic lint rules and model-evaluation cases;
- hierarchical project overrides;
- strict authority boundaries so voice cannot override facts, safety, permissions, tools, or schemas.

## Three ways to use it

### 1. Zero-install, plain Markdown

Copy `templates/simple/VOICE.md` into a project. Tell any model or application to read it only for human-facing output.

```python
from pathlib import Path

voice = Path("VOICE.md").read_text(encoding="utf-8")
system_prompt = BASE_SYSTEM_PROMPT + "\n\n" + voice
```

This is conformance level **L0 Plain**. It requires no parser, package, or schema.

### 2. Coding agents and harnesses: on-demand loading

Install the CLI and bootstrap the repository:

```bash
python -m pip install -e .
voicemd init --mode full
voicemd install --target all --mode auto
voicemd doctor
```

`--mode auto` installs a small Agent Skill or native rule. The harness sees only the skill description by default; it loads the full communication contract when the output is human-facing. This avoids spending context on voice rules while editing code, producing JSON, or calling tools.

Supported adapter pack:

- OpenAI Codex;
- Claude Code;
- Gemini CLI;
- Cursor;
- GitHub Copilot coding agent and CLI surfaces;
- Cline;
- Windsurf;
- OpenCode;
- Aider;
- any harness that can read Agent Skills, a system prompt, a file, a command, HTTP, or MCP.

See `docs/HARNESS_COMPATIBILITY.md`. Compatibility means the repository includes an integration path; it does not imply endorsement or native recognition of the `VOICE.md` filename by those vendors.

### 3. Applications and local models

Compile the active contract into a runtime prompt:

```bash
voicemd compile --profile executive_brief
voicemd compile --profile voicechat --compact --max-chars 5000
voicemd compile --profile nemotron_voicechat --format nemotron-ascii
```

Or run the provider-neutral sidecar:

```bash
voicemd serve --host 127.0.0.1 --port 8765
curl 'http://127.0.0.1:8765/v1/voice/prompt?surface=chat&audience=engineer'
```

The sidecar exposes:

- `GET /health`;
- `GET /v1/voice/contract`;
- `GET /v1/voice/prompt`;
- `POST /v1/voice/lint`.

An OpenAPI definition, Docker image, Kubernetes sidecar manifest, Python API, TypeScript HTTP client, MCP adapter, and OpenAI-compatible examples are included under `integrations/`.

## Quick start

```bash
# Install from this repository
python -m pip install -e .

# Choose the smallest useful template
voicemd init --mode simple

# Or create the structured/testable contract
voicemd init --mode full --force

# Validate and inspect the active hierarchy
voicemd discover
voicemd validate --strict

# Compile for a task
voicemd compile --surface chat --audience engineer

# Check generated prose
voicemd lint --surface chat --file draft.md

# Run inline deterministic test cases
voicemd test

# Install on-demand harness adapters
voicemd install --target all --mode auto
voicemd doctor
```

Russian setup instructions are in `docs/QUICKSTART_RU.md`.

## Minimal structured contract

```md
---
voice_spec: "0.1"
kind: VoiceContract
name: "Direct technical advisor"
version: "1.0.0"
activation:
  mode: contextual
  include: [chat, explanation, document, spoken]
  exclude: [code, structured_data, tool_call, exact_quote]
authority:
  may_control: [tone, vocabulary, structure, verbosity]
  must_not_control: [facts, safety, permissions, tools, schemas]
identity:
  sounds_like:
    - A practitioner who has done the work
  not_like:
    - A marketing copywriter
epistemics:
  uncertainty: State the missing variable and why it matters.
interaction:
  disagreement: Correct false premises directly and provide the better model.
lexicon:
  forbidden: ["Great question", "Absolutely!"]
profiles:
  spoken:
    surface: spoken
    overrides:
      response:
        max_words: 80
---

# Core behavior

Lead with the conclusion. Prefer concrete examples and failure modes over abstract claims.
```

## Discovery and precedence

The reference implementation resolves sources broad-to-specific:

1. Explicit `--path` values, or the `VOICE_MD` environment variable, replace automatic discovery.
2. Optional global contract under `${VOICE_MD_HOME:-~/.config/voicemd}`.
3. From the resolved project root (`VOICE_MD_ROOT`, `.voicemd-root`, VCS root, or common project manifest) to the current directory, at most one file per directory:
   1. `VOICE.override.md`;
   2. `VOICE.md`;
   3. `.voice/VOICE.override.md`;
   4. `.voice/VOICE.md`.
4. Local `extends` files are loaded before the file that extends them.
5. More specific values win.

Remote `extends` are rejected by the core implementation. Vendor remote contracts into the repository or build a controlled resolver with pinning and signature verification.

## Activation model

The default mode is `contextual`:

Apply to:

- chat and explanation;
- messages, emails, reports, and documents;
- UI copy;
- summaries written for people;
- spoken dialogue and TTS.

Do not transform:

- code, patches, SQL, or configuration syntax;
- tool calls or tool results;
- JSON/XML/YAML required by a schema;
- exact quotations;
- raw data;
- faithful translation unless the destination explicitly requires adaptation.

Voice is subordinate to correctness and authority. The normative precedence model is in `SPECIFICATION.md`.

## Conformance levels

- **L0 Plain:** readable Markdown with no required metadata.
- **L1 Core:** valid frontmatter with identity and basic response rules.
- **L2 Contextual:** activation, authority, epistemics, interaction, audience/surface/tone profiles, or speech behavior.
- **L3 Testable:** deterministic rules and/or executable test cases.

Use `voicemd validate` to report the active level.

## Local and small models

Small models usually perform better with an explicit, compressed contract:

```bash
voicemd compile \
  --profile default \
  --compact \
  --max-chars 3500 \
  --output .voice/compiled.prompt.txt
```

The pack includes examples for:

- Hugging Face Transformers chat templates;
- vLLM/OpenAI-compatible servers;
- Ollama Modelfiles;
- llama.cpp-style system-prompt injection;
- NVIDIA NemotronLabs VoiceChat 11B.

For NemotronLabs VoiceChat, compile an English spoken profile with `--format nemotron-ascii`; the released runtime accepts a session instruction string and its current documentation requires system prompts and tool responses to be ASCII-only. See `docs/NEMOTRON_VOICECHAT.md`.

## CLI

```text
voicemd init       create simple, full, or spoken templates
voicemd discover   show active files in precedence order
voicemd validate   schema and semantic validation
voicemd compile    render prompt, JSON, compact, or ASCII output
voicemd lint       deterministic output checks
voicemd test       run inline contract test cases
voicemd install    add managed harness adapters
voicemd uninstall  remove only managed adapter content
voicemd doctor     inspect contract and adapter health
voicemd serve      run the HTTP sidecar
```

Run `voicemd <command> --help` for details.

## Repository layout

```text
SPECIFICATION.md           normative draft
schema/                    JSON Schema
src/voicemd/               Python reference implementation
.agents/skills/            on-demand universal skill
adapters/                  harness-specific integration notes
integrations/              application, local-model, HTTP, MCP, deployment examples
templates/                 simple, full, and spoken starters
evals/                     deterministic and model-based evaluation pack
tests/                     reference implementation tests
docs/                      architecture, security, compatibility, ADRs
lite/                      dependency-free path
```

## Security properties

- Communication rules cannot authorize tools or actions.
- The compiler rejects remote `extends` by default.
- Harness installers use managed markers and refuse to overwrite unmanaged generated files.
- The HTTP sidecar binds to `127.0.0.1` by default and does not provide authentication or remote-contract fetching.
- A `VOICE.md` from an untrusted upload is prompt input and must not be treated as trusted project configuration.
- Generated prompts should be logged by hash/version, not silently changed in production.

See `docs/SECURITY_MODEL.md`.

## Prior art and compatibility

The filename and brand-voice concept have prior art, including the independent Efeonce `voice.md` project. VoiceMD does not claim invention of the filename and is not affiliated with Efeonce. This draft focuses on agent communication, interaction, epistemic behavior, runtime profiles, hierarchy, compilation, and evaluation. A migration/compatibility note is included in `docs/BRAND_COMPATIBILITY.md`.

## What this package does not claim

- It is not yet a vendor-adopted or standards-body-approved format.
- It does not make model behavior perfectly deterministic.
- It does not replace safety policy, identity/role definitions, agent permissions, tool contracts, or product design systems.
- It does not provide voice cloning, acoustic identity, or speaker biometrics. In this standard, “voice” primarily means communication behavior; the `speech` section covers delivery constraints.

## License

Apache License 2.0. See `LICENSE` and `NOTICE`.
