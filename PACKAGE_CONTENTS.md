# VoiceMD release pack contents

This repository is the complete `0.1.0-draft.1` independent draft and reference implementation of the VOICE.md Agent Communication Contract.

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

- hierarchical discovery and explicit source selection;
- local `extends` with cycle/depth protection;
- deterministic deep merge and ID-based rule/test overrides;
- audience, surface, tone, and profile selection;
- prompt, compact, JSON, ASCII, and Nemotron compilation;
- schema and semantic validation;
- deterministic linting and inline conformance tests;
- safe managed adapter installation and uninstall ownership tracking;
- provider-neutral HTTP sidecar.

The CLI commands are `init`, `discover`, `validate`, `compile`, `lint`, `test`, `install`, `uninstall`, `doctor`, and `serve`.

A prebuilt pure-Python wheel is included under `release/`. Source installation remains available through `pyproject.toml`.

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
- TypeScript and .NET clients;
- OpenAI-compatible chat-completions injection;
- Hugging Face Transformers chat-template integration;
- vLLM, Ollama, and llama.cpp recipes;
- NVIDIA NemotronLabs VoiceChat realtime `session.update` adapter and ASCII tool-result renderer;
- optional MCP server;
- Docker Compose and Kubernetes sidecar deployment.

## Evaluation and QA

- `evals/`: prompts, rubric, judge prompt, OpenAI-compatible runner, deterministic scorer.
- `tests/`: unit and regression suite covering discovery, resolution, merge, compilation, profile precedence, prompt budgets, linting, evaluation, and safe adapter lifecycle.
- `.github/workflows/ci.yml`: CI workflow.
- `scripts/build_release.py`: reproducible source ZIP builder.
- `scripts/verify_release.py`: release integrity and smoke verifier.
- `release/SHA256SUMS`: artifact checksums.

## Dependency-free path

`lite/` provides minimal Python, Node.js, and shell loaders. It does not implement the full schema/compiler; it exists for environments where reading a Markdown contract and injecting it into a prompt is sufficient.

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
