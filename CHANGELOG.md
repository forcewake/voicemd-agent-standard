# Changelog

## Unreleased

- Aligned normative L0-L3 conformance with schema and reference validation; vacuous tests no longer establish L3.
- Defined YAML 1.2-compatible parsing, duplicate-key rejection, null deletion, selector-array replacement, canonical selected-contract JSON/SHA-256, and deterministic activation conflicts.
- Enforced protected authority capabilities, selector references, regex safety, JSON compatibility, profile defaults, extends depth, and DAG traversal.
- Fixed Nemotron language selection and post-ASCII prompt budgets.
- Hardened installer path containment, atomic rollback, ownership hashes, mode transitions, explicit-only harness metadata, and adapter diagnostics.
- Hardened sidecar validation, health, error disclosure, body limits, worker bounds, slow-client timeouts, and external-source provenance.
- Made release building Git-tracked and hermetic; tied artifacts to a complete source snapshot, rejected nested build/secret files, expanded clean installs, dependency bounds, Docker context controls, CI, and cross-runtime client builds.
- Added Azure OpenAI regression execution, provider completion metadata, atomic outputs, non-vacuous corpus/provenance gates, broader deterministic cases, and an executable contract-aware model-judge scorer.
- Made activation selector-aware and separated trusted marker metadata from untrusted prompt content.
- Expanded the regression suite from 30 to more than 100 cases and added a branch-coverage gate.

## 0.1.0-draft.1 - 2026-08-24

- Initial public draft of the VOICE.md Agent Communication Contract.
- L0-L3 conformance model.
- Hierarchical discovery, local inheritance, deterministic merge semantics, and authority boundary.
- Audience, surface, tone, speech, runtime, and profile model.
- JSON Schema and Python reference implementation.
- CLI for init, discovery, validation, compilation, linting, tests, harness installation, diagnostics, and HTTP sidecar.
- On-demand Agent Skill and adapters for major coding-agent harnesses.
- Application, local text-model, and NVIDIA NemotronLabs VoiceChat examples.
- Security model, eval pack, CI, governance, and RFC process.
