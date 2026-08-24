# Changelog

## 0.1.0a3 reference implementation - 2026-08-24

- Added an optional Azure Voice Proof Lab for `gpt-audio-1.5`, `gpt-realtime-2.1`, `gpt-realtime-2.1-mini`, and `gpt-live-transcribe`.
- Added three contrasting EN/RU L3 spoken contracts, grounded scenarios, playable WAV output, provider-segment preservation, deterministic assertions, sanitized event timing, effective-session acknowledgement, usage capture, artifact verification, and a static comparison gallery.
- Kept exact raw transcription outside VoiceMD activation and added an end-to-end transcribe-to-Realtime authority-boundary showcase.
- Consolidated public setup and repository inventory into one redesigned README with real Azure output comparisons and a Russian quick start.
- Added a sanitized, checksum-bound GitHub Pages proof snapshot, canonical project URLs, and PyPI/GitHub publication metadata.
- Hardened release ZIP verification with binary-safe required-file checks, a closed `release/` inventory, canonical container boundaries, and explicit member-type validation.
- Restored Python 3.10 compatibility in the eval tools, made the sdist regression version-aware, and updated pinned GitHub Actions to their Node 24 releases.

## 0.1.0-draft.2 specification - 2026-08-24

- Defined YAML 1.2 JSON-subset parsing, duplicate-key rejection, bounded alias expansion, null deletion, selector-array replacement, and empty-override discovery behavior.
- Aligned the core schema and semantic validator, added typed core sections, made invalid contracts `nonconforming`, and required fail-closed validation of each exact selected context.
- Restricted explicit, discovered, and inherited sources to approved canonical roots; rejected `.env` paths and symlink escapes; added file, aggregate, source-count, YAML-node, alias, and inheritance-depth budgets.
- Switched portable canonical selected-contract bytes to RFC 8785 JCS, excluded host paths by default, and added language-neutral vectors plus an independent TypeScript core verifier for merge, selection, compact rendering, JCS, and SHA-256 behavior.
- Defined the bounded `portable-safe-v1` regex subset and consistent `max_words: 0` semantics.
- Made activation selector-aware and separated trusted marker metadata from untrusted prompt content.
- Hardened compile, lint, sidecar, MCP, generic OpenAI-compatible, lite-loader, and Nemotron runtime boundaries, including selected-contract validation, strict request parsing, path redaction, timeouts, and activation-aware injection.
- Hardened Azure/OpenAI-compatible evaluation transport with HTTPS and environment-only credentials, redirect rejection, corpus/result/request/response provenance binding, atomic outputs, and contract-aware model-judge validation.
- Hardened installer path containment, atomic rollback, ownership hashes, mode transitions, explicit-only harness metadata, and adapter diagnostics.
- Made release building Git-tracked, pinned, and reproducibility-checked; tied artifacts to a complete source snapshot, rejected nested build/secret files, tightened dependency and Docker-context controls, and expanded CI and cross-runtime checks.

## 0.1.0-draft.1 specification - 2026-08-24

- Initial public draft of the VOICE.md Agent Communication Contract.
- L0-L3 conformance model.
- Hierarchical discovery, local inheritance, deterministic merge semantics, and authority boundary.
- Audience, surface, tone, speech, runtime, and profile model.
- JSON Schema and Python reference implementation.
- CLI for init, discovery, validation, compilation, linting, tests, harness installation, diagnostics, and HTTP sidecar.
- On-demand Agent Skill and adapters for major coding-agent harnesses.
- Application, local text-model, and NVIDIA NemotronLabs VoiceChat examples.
- Security model, eval pack, CI, governance, and RFC process.
