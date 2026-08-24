# Historical verification record — 2026-08-24

This record applies only to the stale `0.1.0a1` artifacts and does not verify the current source tree.

Package `0.1.0a1` was built from a fresh local clone of source revision `f58043470422a27c4b15eab1d3506cfd2283cb68`. `release/BUILD_INFO.json` binds the artifacts to that revision and to the complete non-release source snapshot hash.

- [x] 119 unit and regression tests passed from the source tree and from a clean sdist installation.
- [x] Branch-aware coverage was 78%, above the configured 75% gate.
- [x] Root `VOICE.md`, full template, and spoken template passed strict L3 validation.
- [x] All 13 contract example/template files passed their applicable L0-L3 validation profile.
- [x] Wheel and sdist contents matched current package and release source files byte-for-byte.
- [x] Wheel installed in a clean Python 3.13 environment; `pip check`, version, strict validation, and CLI compilation passed.
- [x] Source distribution installed in a separate clean Python 3.13 environment; `pip check` and the complete test suite passed.
- [x] Packaged schema, templates, and Agent Skill were present and synchronized.
- [x] Shared adapter ownership, hash health, mode transitions, rollback, and non-destructive uninstall were regression-tested.
- [x] Explicit-only metadata was tested for supported harnesses; Aider limitations are documented.
- [x] HTTP sidecar startup validation, health, generic errors, body limits, worker bounds, timeouts, and source provenance were tested.
- [x] Nemotron profile compiled to ASCII within the 5,000-character budget from the installed wheel.
- [x] Python, Node.js, and shell lite loaders produced equivalent output.
- [x] TypeScript passed strict `tsc --noEmit`; .NET 8 built with zero warnings and errors.
- [x] JSON, JSONL, OpenAPI, GitHub Actions, Docker Compose, Kubernetes YAML, CFF, and local Markdown links parsed successfully.
- [x] Azure OpenAI transport completed with provider-returned model/finish metadata and no secret fields; the complete 14-case deterministic regression score passed.
- [x] Same-deployment Azure model judging was exercised only as a plumbing smoke test and is not claimed as independent quality evidence.
- [x] Release artifact SHA-256 checksums were regenerated and recorded in both `SHA256SUMS` and `BUILD_INFO.json`.

Not locally verified: Docker image execution and hosted GitHub Actions, because Docker is not installed here and no remote is configured. These remain external release gates before public publication or tagging.
