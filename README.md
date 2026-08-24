# VoiceMD: the `VOICE.md` Agent Communication Contract

**Status:** independent draft `0.1.0-draft.2`, dated 2026-08-24, with Python reference implementation `0.1.0a3`. It is usable and testable, and it is intentionally not presented as an adopted industry standard.

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

`--mode explicit` installs an explicit-only skill where the harness supports one. Invoke `$voice-contract` in Codex and `/voice-contract` in Claude Code, GitHub Copilot CLI, or Cursor. Portable `@voice` text markers affect an already available contract; they cannot load a skill hidden by native invocation policy. Aider requires an explicit `aider --config .aider.voice.yml` session and cannot provide the same mode semantics.

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
voicemd compile --profile executive_brief --format sha256
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

### Azure Voice Proof Lab

The optional Azure adapter exercises `gpt-audio-1.5`, `gpt-realtime-2.1`,
`gpt-realtime-2.1-mini`, and `gpt-live-transcribe` against contrasting spoken
contracts. It writes playable WAV files, provider transcripts, sanitized event
timings, effective-session fingerprints, deterministic assertions, and
hash-bound context artifacts:

```bash
python -m pip install -e '.[azure-voice]'
voicemd-azure doctor
voicemd-azure matrix --scenario degraded-service-en --lanes audio realtime-mini
voicemd-azure gallery
```

The transcription lane deliberately records `VOICE.md` activation as false for
the exact raw transcript. The `showcase` command applies the selected contract
only to a subsequent human-facing response. See
[`examples/azure-voice/README.md`](examples/azure-voice/README.md) for the paid-call warning,
security boundaries, input format, all commands, and current Microsoft Azure
references. A successful recorded run proves that specific request and its
stored artifacts; it is not a general quality, latency, SLA, or production-readiness claim.

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

Every source must resolve inside an operator-approved source root; symlinks cannot widen that boundary, and `.env`/`.env.*` files are never accepted as contracts. The reference loader also enforces per-file, aggregate-byte, source-count, YAML-node, alias, and inheritance-depth budgets. Applications may lower these defaults for multi-tenant or latency-sensitive runtimes.

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
- **L1 Core:** valid structured frontmatter plus concrete communication guidance.
- **L2 Contextual:** activation, authority, epistemics, interaction, audience/surface/tone profiles, or speech behavior.
- **L3 Testable:** a non-vacuous deterministic rule or inline executable test case. A skipped external-response case does not establish core L3.

An invalid or empty contract is `nonconforming`; it must not receive an L0-L3 label. Use `voicemd validate` to report the active level. Runtime selection is also fail-closed: the exact audience/surface/tone/profile result is revalidated before compilation, linting, sidecar output, or provider submission.

Core deterministic regex rules use the bounded `portable-safe-v1` subset. It supports ASCII patterns with fixed explicit character classes, anchors, ordinary groups, control/ASCII-hex escapes, and separate `i`, `m`, and `s` flags. Alternation, repetition, shorthand character classes, lookarounds, inline modifiers, backreferences, Unicode escapes, and named groups are outside core L3. Candidate line endings, U+2028, and U+2029 are normalized before matching.

## Portable data and conformance

Structured frontmatter uses the YAML 1.2 JSON schema subset rather than YAML 1.1 implicit typing. For example, `true`, `false`, `null`, and JSON-form numbers are typed; legacy spellings such as `yes`, `012`, `1_000`, and `1:20` remain strings. YAML resource limits count mapping keys and values after alias expansion, so aliases cannot hide an oversized mapping.

Executable count/budget fields accept finite integral JSON Numbers such as `1.0` or `1e0`, normalize them to integers, and reject values outside their field range or above `9007199254740991`. Selector names use an explicitly pinned Unicode whitespace set rather than a language runtime's `trim()` behavior; U+200B ZERO WIDTH SPACE is nonblank.

`voicemd compile --format canonical-json` uses RFC 8785 JSON Canonicalization Scheme (JCS), including ECMAScript number serialization and UTF-16 key ordering, with no Unicode normalization. VoiceMD first applies a stricter cross-language profile that rejects integral values outside the IEEE-754 safe-integer range. `--format sha256` hashes the canonical UTF-8 bytes. Both formats exclude host filesystem paths.

The language-neutral `conformance/vectors.json` covers merge, selection, compact rendering, JCS, and hashing. The bundled TypeScript verifier is independent of the Python compiler for that core:

```bash
node integrations/typescript/generated/conformance-verifier.js \
  conformance/vectors.json
```

This verifier is not a complete second implementation of YAML parsing, filesystem discovery, or runtime adapters.

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

For NemotronLabs VoiceChat, compile an English spoken profile with `--format nemotron-ascii`; the released runtime accepts a session instruction string and its current documentation requires system prompts and tool responses to be ASCII-only. Treat the compiled VoiceMD text as a lower-priority fragment, not the complete session authority. The reference adapter requires separate application-owned base instructions. See `docs/NEMOTRON_VOICECHAT.md`.

## Azure OpenAI evaluation

The evaluation runner supports Azure OpenAI through environment variables or an environment file:

```bash
export AZURE_OPENAI_ENDPOINT='https://YOUR-RESOURCE.openai.azure.com'
export AZURE_OPENAI_API_KEY='...'
export AZURE_OPENAI_CHAT_DEPLOYMENT='YOUR-DEPLOYMENT'

python evals/run_openai_compatible.py \
  --provider azure \
  --cases evals/prompts.jsonl \
  --output evals/results.azure.jsonl
```

The repository-local `.env` is loaded by default and is ignored by Git. Azure mode requires HTTPS, reads API keys only from the environment or `--env-file`, and rejects redirects. Do not pass secrets as command-line arguments. Generated results contain endpoint and request hashes, not the key or endpoint URL. See `evals/README.md` and `docs/EVALS.md`.

## CLI

```text
voicemd init       create simple, full, or spoken templates
voicemd discover   show active files in precedence order
voicemd validate   schema and semantic validation
voicemd compile    render prompt, JSON, canonical hash, compact, or ASCII output
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
conformance/               language-neutral vectors and TypeScript core verifier
tests/                     reference implementation tests
docs/                      architecture, security, compatibility, ADRs
lite/                      no-package-dependency raw loaders (shell uses Python)
```

## Security properties

- Communication rules cannot authorize tools or actions.
- The loader contains every source inside approved roots, rejects `.env` paths and remote `extends`, and applies bounded source/YAML budgets.
- The exact selected contract is validated before any runtime output is emitted.
- Harness installers reject symlink escapes, preflight multi-file changes, record ownership hashes, and preserve modified managed content.
- The HTTP sidecar binds to `127.0.0.1` by default and does not provide authentication or remote-contract fetching.
- A `VOICE.md` from an untrusted upload is prompt input and must not be treated as trusted project configuration.
- Generated prompts should be logged by hash/version, not silently changed in production.

See `docs/SECURITY_MODEL.md`.

## Prior art and compatibility

The filename and brand-voice concept have prior art, including the independent Efeonce `voice.md` project. VoiceMD does not claim invention of the filename and is not affiliated with Efeonce. This draft focuses on agent communication, interaction, epistemic behavior, runtime profiles, hierarchy, compilation, and evaluation. A migration/compatibility note is included in `docs/BRAND_COMPATIBILITY.md`.

## What this package does not claim

- It is not yet a vendor-adopted or standards-body-approved format.
- The repository does not yet identify a canonical public remote or published canonical schema URL.
- The bundled TypeScript core verifier is not a full external implementation, and there is no independent implementation report yet.
- No independent security review has been published, and the ten-contract real-world validation target remains open.
- It does not make model behavior perfectly deterministic.
- It does not replace safety policy, identity/role definitions, agent permissions, tool contracts, or product design systems.
- It does not provide voice cloning, acoustic identity, or speaker biometrics. In this standard, “voice” primarily means communication behavior; the `speech` section covers delivery constraints.

## License

Apache License 2.0. See `LICENSE` and `NOTICE`.
