# VoiceMD release pack contents

This repository is the complete `0.1.0-draft.2` independent draft and Python reference implementation `0.1.0a3` of the VOICE.md Agent Communication Contract.

## Standard and governance

- `SPECIFICATION.md`: normative format, discovery, merge, precedence, compilation, authority, security, and conformance rules.
- `schema/voice.schema.json`: public JSON Schema.
- `rfcs/`: change-proposal template.
- `GOVERNANCE.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`: project governance and disclosure process.
- `ROADMAP.md`, `CHANGELOG.md`, `CITATION.cff`, `manifest.json`: lifecycle metadata.
- Apache-2.0 `LICENSE` and `NOTICE`.

## Authoring modes

- `templates/simple/VOICE.md`: plain Markdown, zero parser, L0 path.
- `templates/full/VOICE.md`: structured, hierarchical, testable L3 path.
- `templates/spoken/VOICE.md`: speech-oriented path.
- `VOICE.md`: the repository's own full contract.
- `examples/`: hierarchy, brand extension, application context, and precompiled prompt examples.

## Reference implementation

The Python package under `src/voicemd/` provides:

- hierarchical discovery and explicit source selection with approved-root containment;
- local `extends` with symlink-safe containment, cycle/depth protection, and source/YAML resource budgets;
- deterministic deep merge and ID-based rule/test overrides;
- audience, surface, tone, and profile selection with fail-closed validation of the exact selected contract;
- prompt, compact, JSON, RFC 8785 canonical JSON/SHA-256, ASCII, and Nemotron compilation;
- YAML 1.2 JSON-subset parsing plus schema and semantic validation;
- deterministic `portable-safe-v1` linting and inline conformance tests;
- safe managed adapter installation and uninstall ownership tracking;
- provider-neutral HTTP sidecar.

The CLI commands are `init`, `discover`, `validate`, `compile`, `lint`, `test`, `install`, `uninstall`, `doctor`, and `serve`.

A release build may place the pure-Python wheel `voicemd-0.1.0a3-py3-none-any.whl` under `release/`. Treat it as current only when the file exists, `release/BUILD_INFO.json` says `artifact_status: current`, and the release verifier passes; development checkouts may deliberately contain no wheel or mark old artifacts `stale`. Source installation remains available through `pyproject.toml`.

## Harness adapters

Adapters and managed examples are included for:

- OpenAI Codex;
- Claude Code;
- Gemini CLI;
- Cursor;
- GitHub Copilot;
- Cline;
- Windsurf;
- OpenCode;
- Aider;
- any Agent Skills-compatible or file/system-prompt-capable harness.

The canonical on-demand skill is under `.agents/skills/voice-contract/SKILL.md`; Claude and Cline compatibility copies are included. Harness-specific notes and example configuration live under `adapters/`.

“Adapter included” does not claim that a vendor natively recognizes `VOICE.md` as a standard.

## Application and deployment pack

`integrations/` contains:

- Python direct API and middleware;
- HTTP/OpenAPI sidecar examples;
- buildable TypeScript and .NET clients;
- OpenAI-compatible chat-completions injection;
- Hugging Face Transformers chat-template integration;
- vLLM, Ollama, and llama.cpp recipes;
- NVIDIA NemotronLabs VoiceChat realtime `session.update` adapter and ASCII tool-result renderer;
- Azure OpenAI audio-completion, Realtime WebSocket, live-transcription, proof-bundle, and static-gallery adapter;
- optional MCP server;
- Docker Compose and Kubernetes sidecar deployment.

## Evaluation and QA

- `evals/`: prompts, rubric, judge prompt, Azure/OpenAI-compatible runner, deterministic scorer, and model-judge runner.
- `examples/azure-voice/`: three contrasting L3 spoken contracts, EN/RU scenarios, evidence schema, and the Azure Voice Proof Lab guide.
- `conformance/vectors.json`: language-neutral vectors for merge, selection, compact rendering, RFC 8785 JCS, and SHA-256 behavior.
- `integrations/typescript/generated/conformance-verifier.js`: core verifier independent of the Python compiler; it is not a complete second YAML/discovery/runtime implementation.
- `tests/`: unit and regression suite covering discovery, resolution, merge, compilation, profile precedence, prompt budgets, linting, evaluation, and safe adapter lifecycle.
- `.github/workflows/ci.yml`: CI workflow.
- `scripts/build_release.py`: Git-object-backed deterministic source ZIP builder, release metadata generator, and canonical setuptools sdist normalizer.
- `scripts/verify_release.py`: metadata-first release integrity verifier. Optional clean-install and smoke execution requires the explicit `--trusted-runtime-checks` flag and is only for self-built or otherwise trusted artifacts; it is not a sandbox.
- `release/SHA256SUMS`: artifact checksums.

Run the language-neutral core vectors with:

```bash
node integrations/typescript/generated/conformance-verifier.js \
  conformance/vectors.json
```

The Azure eval transport requires HTTPS, reads keys only from the environment or an environment file, and rejects redirects. Candidate and judge records are bound to canonical corpus, case, contract, request, and response hashes; secrets and endpoint URLs are not result fields.

## Dependency-free path

`lite/` provides minimal Python and Node.js loaders plus a shell wrapper around the Python loader. They have no package dependencies, but require their named language runtime. They do not implement the full schema/compiler; this path exists where reading Markdown and injecting it into a prompt is sufficient.

## Documentation map

- `START_HERE_RU.md` and `docs/QUICKSTART_RU.md`: Russian setup paths.
- `docs/ARCHITECTURE.md`: component and runtime architecture.
- `docs/DISCOVERY_AND_MERGE.md`: deterministic hierarchy and merge examples.
- `docs/ACTIVATION_AND_PRECEDENCE.md`: when voice applies and what wins conflicts.
- `docs/HARNESS_COMPATIBILITY.md`: current adapter basis and limits.
- `docs/APPLICATION_INTEGRATION.md`: in-process and sidecar use.
- `docs/LOCAL_MODELS.md`, `docs/NEMOTRON_VOICECHAT.md`: local and spoken models.
- `docs/EVALS.md`: verification strategy.
- `docs/SECURITY_MODEL.md`: prompt-injection and authority controls.
- `docs/BRAND_COMPATIBILITY.md`: relationship to copy/brand-oriented voice files.
- `docs/REFERENCES.md`: primary official sources and prior art.
- `docs/decisions/`: architecture decision records.

## External validation status

The package is self-contained, but external ecosystem evidence remains incomplete. No vendor or standards body has adopted the format. Project metadata does not yet identify a canonical public remote or published canonical schema URL. The TypeScript verifier is bundled project code, not an external full implementation. No independent security review is published, and the roadmap target of ten independent real-world contracts remains open.
