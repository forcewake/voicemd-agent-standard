# VoiceMD

[![PyPI](https://img.shields.io/pypi/v/voicemd.svg?label=PyPI&color=2563eb)](https://pypi.org/project/voicemd/)
[![Python](https://img.shields.io/pypi/pyversions/voicemd.svg?color=0f766e)](https://pypi.org/project/voicemd/)
[![CI](https://github.com/forcewake/voicemd-agent-standard/actions/workflows/ci.yml/badge.svg)](https://github.com/forcewake/voicemd-agent-standard/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-7c3aed.svg)](https://github.com/forcewake/voicemd-agent-standard/blob/main/LICENSE)
[![Spec](https://img.shields.io/badge/spec-0.1.0--draft.2-f59e0b.svg)](https://github.com/forcewake/voicemd-agent-standard/blob/main/SPECIFICATION.md)

**A version-controlled communication contract for AI agents.**

`VOICE.md` defines how an agent communicates: how it explains uncertainty,
disagrees, adapts to an audience, structures an answer, and speaks through a
voice interface. It does not grant capabilities or override facts, safety,
permissions, tools, exact quotations, or required schemas.

[Website](https://forcewake.github.io/voicemd-agent-standard/)
· [Specification](https://github.com/forcewake/voicemd-agent-standard/blob/main/SPECIFICATION.md)
· [JSON Schema](https://raw.githubusercontent.com/forcewake/voicemd-agent-standard/v0.1.0a3/schema/voice.schema.json)
· [Azure proof](https://forcewake.github.io/voicemd-agent-standard/azure-proof.html)
· [Azure Voice Lab](https://github.com/forcewake/voicemd-agent-standard/blob/main/examples/azure-voice/README.md)
· [Security model](https://github.com/forcewake/voicemd-agent-standard/blob/main/docs/SECURITY_MODEL.md)

> **Status:** independent draft `0.1.0-draft.2`, dated 2026-08-24, with Python
> reference implementation `0.1.0a3`. Usable and testable; not a vendor-adopted
> or standards-body-approved format.

```text
AGENTS.md      what the agent does and how it works
DESIGN.md      how the product looks and behaves visually
STORYLINE.md   how the experience unfolds
VOICE.md       how the agent communicates and interacts
```

## See the difference

The three contract-compliant reference outputs below use the same synthetic
incident facts. They are deterministic examples derived from the bundled L3
contract cases; only the selected `VOICE.md` changes.

Known facts: service degraded; p95 latency 840 ms; no data loss reported; cause
not confirmed; rollout paused.

| Contract | Contract-compliant reference output | Communication behavior |
| --- | --- | --- |
| `incident_commander` | “The service is degraded. No data loss is reported. The ninety-fifth percentile latency is 840 milliseconds. Keep the rollout paused while we verify the cause.” | Verified status → impact → next action |
| `calm_support` | “I know this disruption is frustrating. The service is degraded, with 840-millisecond latency, but no data loss is reported. Please keep the rollout paused while the team investigates the unconfirmed cause.” | Acknowledge impact without false reassurance |
| `executive_brief` | “Decision: keep the rollout paused. The service is degraded, with 840-millisecond latency and no reported data loss. The cause is unconfirmed, so resuming now creates avoidable operational risk.” | Decision → evidence → material risk |

[Listen to the recorded Azure samples and inspect their exact transcripts](https://forcewake.github.io/voicemd-agent-standard/azure-proof.html).

### Recorded Azure proof snapshot

One local proof run on 2026-08-24 produced 11 manifests that passed the
evidence schema at capture time and are hash-bound in the public snapshot. The
synthetic 3×3 matrix completed all nine provider calls and retained every exact
output together with its deterministic contract-check record.

| Azure deployment | Lane | Runs completed | What was captured |
| --- | --- | ---: | --- |
| `gpt-audio-1.5` | Chat Completions text + audio | 3/3 | Non-realtime audio output under three contracts |
| `gpt-realtime-2.1` | Realtime WebSocket text → audio | 3/3 | Effective session instructions and spoken responses |
| `gpt-realtime-2.1-mini` | Realtime WebSocket text → audio | 3/3 | The same contract matrix on the smaller Realtime deployment |
| `gpt-live-transcribe` | Realtime transcription | 1/1 | Raw provider segments without VoiceMD rewriting |
| `gpt-live-transcribe` → `gpt-realtime-2.1` | End-to-end showcase | 1/1 | Raw ASR remained raw; VoiceMD shaped only the spoken response |

The proof page includes playable samples, exact transcripts, deterministic
contract-check records, and the authority-boundary showcase. These observations
are not a benchmark, SLA, quality score, fixed model-identity claim, or production
readiness certification. Microsoft currently documents GPT Realtime 2.x as
[preview](https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/realtime-2);
recheck availability and lifecycle before production use.

## Install and run

### Python package

```bash
python -m pip install voicemd

voicemd init --mode full
voicemd validate --strict
voicemd compile --profile executive_brief
voicemd test
```

For Azure audio, Realtime, and transcription demos:

```bash
python -m pip install 'voicemd[azure-voice]'
voicemd-azure doctor
```

Python 3.10–3.14 is supported.

### Zero-install Markdown

Copy the simple template and include it only when generating human-facing
language:

```bash
cp templates/simple/VOICE.md ./VOICE.md
```

```python
from pathlib import Path

voice = Path("VOICE.md").read_text(encoding="utf-8")
system_prompt = BASE_SYSTEM_PROMPT + "\n\n" + voice
```

This is conformance level **L0 Plain** and needs no package or parser. Minimal
loaders are also available in Python, Node.js, and shell:

```bash
python lite/voice_loader.py
node lite/load-voice.mjs
bash lite/load-voice.sh
```

## Write a contract

A `VOICE.md` can be plain Markdown or structured YAML frontmatter plus Markdown.
The structured form can be selected, compiled, linted, and tested.

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

Lead with the conclusion. Prefer concrete examples and failure modes over
abstract claims.
```

Start from the smallest suitable template:

| Template | Level | Use it when |
| --- | --- | --- |
| [`templates/simple/VOICE.md`](https://github.com/forcewake/voicemd-agent-standard/blob/main/templates/simple/VOICE.md) | L0 | A model only needs readable Markdown |
| [`templates/full/VOICE.md`](https://github.com/forcewake/voicemd-agent-standard/blob/main/templates/full/VOICE.md) | L3 | You need profiles, hierarchy, lint rules, and tests |
| [`templates/spoken/VOICE.md`](https://github.com/forcewake/voicemd-agent-standard/blob/main/templates/spoken/VOICE.md) | L3 | The output is speech/TTS or realtime dialogue |

## Coding-agent adapters

```bash
voicemd install --target all --mode auto
voicemd doctor
```

`auto` installs a small managed bootstrap and a `voice-contract` Agent Skill.
The harness loads the full contract for human-facing output, not for code
patches, tool calls, raw data, or mandatory JSON.

`explicit` requires native invocation where supported:

```bash
voicemd install --target all --mode explicit
```

- Codex: `$voice-contract`
- Claude Code, GitHub Copilot CLI, Cursor: `/voice-contract`
- portable marker after a contract is already available: `@voice` or `voice:on`
- Aider: start the opted-in session with `aider --config .aider.voice.yml`

Included compatibility adapters cover Codex, Claude Code, Gemini CLI, Cursor,
GitHub Copilot, Cline, Windsurf, OpenCode, Aider, and generic Agent
Skills-compatible harnesses. Compatibility does not imply vendor endorsement
or native recognition of the `VOICE.md` filename. See
[`docs/HARNESS_COMPATIBILITY.md`](https://github.com/forcewake/voicemd-agent-standard/blob/main/docs/HARNESS_COMPATIBILITY.md).

## Applications and sidecar

Compile a selected contract directly:

```bash
voicemd compile --profile executive_brief
voicemd compile --profile voicechat --compact --max-chars 5000
voicemd compile --profile nemotron_voicechat --format nemotron-ascii
voicemd compile --profile executive_brief --format sha256
```

Or use the provider-neutral HTTP sidecar:

```bash
voicemd serve --host 127.0.0.1 --port 8765
curl 'http://127.0.0.1:8765/v1/voice/prompt?surface=chat&audience=engineer'
```

Endpoints:

- `GET /health`
- `GET /v1/voice/contract`
- `GET /v1/voice/prompt`
- `POST /v1/voice/lint`

The repository includes a Python API/middleware, TypeScript and .NET clients,
OpenAPI, optional MCP server, Docker Compose, Kubernetes sidecar, and examples
for OpenAI-compatible servers, Transformers, vLLM, Ollama, and llama.cpp.

## Azure Voice Proof Lab

The optional proof harness compares three generation deployments against three
contrasting L3 spoken contracts. Separate commands exercise
`gpt-live-transcribe` and the transcription-to-Realtime authority boundary.

Create an ignored `.env` file with mode `0600`; the CLI loads it by default:

```dotenv
AZURE_OPENAI_ENDPOINT=https://YOUR-RESOURCE.openai.azure.com
AZURE_OPENAI_API_KEY=YOUR-KEY
```

```bash
chmod 600 .env

voicemd-azure doctor
voicemd-azure matrix --scenario degraded-service-en
voicemd-azure gallery
```

`matrix` performs nine billable calls by default. Restrict it while developing:

```bash
voicemd-azure matrix \
  --scenario degraded-service-en \
  --lanes realtime-mini
```

Raw live transcription deliberately runs with VoiceMD activation disabled:

```bash
voicemd-azure transcribe \
  --input-audio input-24k-mono.wav \
  --language en \
  --delay medium
```

The end-to-end authority demo first stores raw ASR, then sends it as untrusted
user speech to a fresh VoiceMD-governed Realtime response:

```bash
voicemd-azure showcase \
  --input-audio input-24k-mono.wav \
  --voice examples/azure-voice/contracts/executive_brief/VOICE.md
```

Each run writes a schema-validated manifest, SHA-256 inventory, exact context
snapshots, sanitized event timing, transcript, and playable WAV where
applicable. Credentials stay in environment state or an ignored environment
file. Manifests store only endpoint fingerprints; WebSocket and REST redirects
are rejected. Read the paid-call warning, PCM input requirements, complete
commands, and proof boundaries in
[`examples/azure-voice/README.md`](https://github.com/forcewake/voicemd-agent-standard/blob/main/examples/azure-voice/README.md).

## Discovery, hierarchy, and precedence

The reference implementation resolves sources broad-to-specific:

1. Explicit `--path` values, or `VOICE_MD`, replace automatic discovery.
2. An optional global contract is read from `${VOICE_MD_HOME:-~/.config/voicemd}`.
3. From project root to the current directory, at most one file wins per level:
   `VOICE.override.md`, `VOICE.md`, `.voice/VOICE.override.md`, then
   `.voice/VOICE.md`.
4. Local `extends` files load before the file that extends them.
5. More specific values win; rules and tests merge deterministically by ID.

```text
repo/VOICE.md                         organization defaults
repo/apps/VOICE.md                    product behavior
repo/apps/support/VOICE.override.md   support-agent override
```

Remote `extends` are rejected. Explicit, discovered, and inherited sources must
remain inside an approved canonical root; symlinks and `.env` files cannot
widen that boundary. File, aggregate, source-count, YAML-node, alias, and
inheritance-depth limits are enforced.

## Activation and authority

Apply VoiceMD to:

- chat, explanations, messages, reports, summaries, and UI copy;
- audience-specific or tone-specific human communication;
- spoken dialogue and TTS-friendly rendering.

Do not transform:

- code, patches, SQL, or configuration syntax;
- tool calls or tool results;
- required JSON/XML/YAML or another exact schema;
- exact quotations, raw data, or raw transcripts;
- faithful translation unless adaptation is explicitly required.

Higher-priority safety, facts, permissions, tools, legal requirements, and
application instructions always win. `VOICE.md` is communication policy, not
an authorization system or prompt-injection security boundary.

## Conformance and portability

| Level | Meaning |
| --- | --- |
| L0 Plain | Readable non-empty Markdown |
| L1 Core | Valid structured metadata plus concrete guidance |
| L2 Contextual | Activation, authority, epistemics, interaction, profiles, or speech behavior |
| L3 Testable | At least one non-vacuous deterministic rule or inline executable test |

An invalid or empty contract is `nonconforming`. The exact selected
profile/audience/surface/tone result is validated again before compilation,
linting, sidecar output, or provider submission.

Structured frontmatter uses the YAML 1.2 JSON schema subset. Canonical JSON and
SHA-256 use RFC 8785 JCS after VoiceMD's stricter portable safe-integer checks
and exclude host filesystem paths.

Run the language-neutral core suite with the independent TypeScript verifier:

```bash
node integrations/typescript/generated/conformance-verifier.js \
  conformance/vectors.json
```

The 57 vectors cover merge, selection, compact rendering, JCS, and hashing.
This bundled Python-independent verifier is not a complete second
implementation of YAML parsing,
filesystem discovery, or runtime adapters.

## CLI reference

| Command | Purpose |
| --- | --- |
| `voicemd init` | Create simple, full, or spoken templates |
| `voicemd discover` | Show active files in precedence order |
| `voicemd validate` | Run schema and semantic validation |
| `voicemd compile` | Render prompt, compact, JSON, canonical hash, or ASCII output |
| `voicemd lint` | Apply deterministic rules to generated prose |
| `voicemd test` | Run inline contract cases |
| `voicemd install` | Add managed harness adapters |
| `voicemd uninstall` | Remove only managed adapter content |
| `voicemd doctor` | Inspect contract and adapter health |
| `voicemd serve` | Run the HTTP sidecar |
| `voicemd-azure` | Run Azure audio/Realtime/transcription proof commands |

Use `voicemd <command> --help` or `voicemd-azure --help` for full options.

## Repository map

| Path | Contents |
| --- | --- |
| `SPECIFICATION.md` | Normative discovery, merge, authority, compilation, security, and conformance rules |
| `schema/` | Public JSON Schema |
| `src/voicemd/` | Python reference implementation and packaged resources |
| `.agents/skills/` | Canonical on-demand Agent Skill |
| `templates/` | Simple, full, and spoken starter contracts |
| `adapters/` | Coding-harness compatibility notes and bootstrap payloads |
| `integrations/` | APIs, clients, sidecars, model runtimes, containers, and MCP |
| `examples/azure-voice/` | Azure proof contracts, scenarios, schema, and operator guide |
| `evals/` | Deterministic and model-based evaluation pack |
| `conformance/` | Language-neutral vectors and bundled Python-independent TypeScript core verifier |
| `lite/` | Minimal Python, Node.js, and shell loaders |
| `site/` | Standard website plus checksum-bound Azure evidence page |
| `tests/` | Unit, regression, security, release, and adapter tests |
| `docs/` | Architecture, activation, merge, security, compatibility, ADRs, and references |
| `release/` | Verified wheel, sdist, SBOM, provenance, checksums, and build record |

Governance is explicit: [`GOVERNANCE.md`](https://github.com/forcewake/voicemd-agent-standard/blob/main/GOVERNANCE.md),
[`CONTRIBUTING.md`](https://github.com/forcewake/voicemd-agent-standard/blob/main/CONTRIBUTING.md),
[`CODE_OF_CONDUCT.md`](https://github.com/forcewake/voicemd-agent-standard/blob/main/CODE_OF_CONDUCT.md),
[`SECURITY.md`](https://github.com/forcewake/voicemd-agent-standard/blob/main/SECURITY.md),
[`ROADMAP.md`](https://github.com/forcewake/voicemd-agent-standard/blob/main/ROADMAP.md), and
[`CHANGELOG.md`](https://github.com/forcewake/voicemd-agent-standard/blob/main/CHANGELOG.md).

## Security and release integrity

- Sources are root-contained; remote `extends`, symlink escapes, `.env` paths,
  unbounded YAML expansion, and invalid selected contracts fail closed.
- Harness installation is atomic, ownership-tracked, and non-destructive to
  modified or unowned content.
- The HTTP sidecar binds to `127.0.0.1` by default and is not an authenticated
  public gateway.
- Azure credentials never belong in CLI arguments, captured output, manifests,
  transcripts, or Git.
- Release artifacts are built twice with a pinned toolchain and compared
  byte-for-byte.
- `BUILD_INFO.json`, SHA-256 checksums, SPDX SBOM, and unsigned in-toto/SLSA
  provenance bind artifacts to a source snapshot.
- GitHub publication adds hosted CI and signed attestations; local unsigned
  provenance proves consistency, not publisher identity.

Verify a checked-out release without executing artifact code:

```bash
python scripts/verify_release.py \
  --distributions release \
  --metadata release \
  --source-root . \
  --source-revision "$(jq -r .source_revision release/BUILD_INFO.json)" \
  --release-revision "$(jq -r .release_revision release/BUILD_INFO.json)"
```

See [`docs/SECURITY_MODEL.md`](https://github.com/forcewake/voicemd-agent-standard/blob/main/docs/SECURITY_MODEL.md) and
[`docs/RELEASE_CHECKLIST.md`](https://github.com/forcewake/voicemd-agent-standard/blob/main/docs/RELEASE_CHECKLIST.md).

<details>
<summary><strong>Быстрый старт на русском</strong></summary>

### Без установки

```bash
cp templates/simple/VOICE.md ./VOICE.md
```

Передавайте `VOICE.md` модели только для текста, который читает или слышит
человек. Не применяйте его к code, tool calls/results, обязательному JSON, raw
data, raw transcripts и exact quotations.

### CLI и coding agents

```bash
python -m pip install voicemd
voicemd init --mode full
voicemd validate --strict
voicemd install --target all --mode auto
voicemd doctor
```

`auto` устанавливает маленький managed bootstrap и Agent Skill. Полный contract
загружается для human-facing output, а не для каждой операции агента.

### Azure voice demos

```bash
python -m pip install 'voicemd[azure-voice]'
```

Создайте ignored `.env` с правами `0600`:

```dotenv
AZURE_OPENAI_ENDPOINT=https://YOUR-RESOURCE.openai.azure.com
AZURE_OPENAI_API_KEY=YOUR-KEY
```

```bash
chmod 600 .env

voicemd-azure doctor
voicemd-azure matrix --scenario degraded-service-en --lanes realtime-mini
voicemd-azure gallery
```

Полная matrix делает девять billable calls. `gpt-live-transcribe` сохраняет raw
provider segments без VoiceMD transformation; `showcase` применяет contract
только к следующему spoken response. Ключ читается только из environment или
ignored environment file, а evidence не хранит endpoint URL.

### Главная граница

`VOICE.md` управляет tone, vocabulary, structure, verbosity, disagreement,
uncertainty, audience adaptation и spoken delivery. Он не может менять safety,
facts, permissions, tools, legal obligations, exact quotations или required
output schema.

</details>

## Boundaries and prior art

VoiceMD does not claim deterministic model behavior, voice cloning, acoustic
identity, vendor adoption, independent security certification, or standards
body approval. The filename and brand-voice concept have prior art, including
the independent Efeonce `voice.md` project; VoiceMD does not claim invention of
the filename or affiliation with that project. See
[`docs/BRAND_COMPATIBILITY.md`](https://github.com/forcewake/voicemd-agent-standard/blob/main/docs/BRAND_COMPATIBILITY.md).

## License

Apache License 2.0. See
[`LICENSE`](https://github.com/forcewake/voicemd-agent-standard/blob/main/LICENSE)
and [`NOTICE`](https://github.com/forcewake/voicemd-agent-standard/blob/main/NOTICE).
