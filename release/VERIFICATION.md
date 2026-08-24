# Verification record — 2026-08-24

Package `0.1.0a2` was built from source revision `fc7adad1b5a7ea5cb17b7ed7349256c5f858ea9c`. `BUILD_INFO.json` binds the artifacts to that revision and to the complete non-release source snapshot hash. The embedded provenance is unsigned; the public release workflow is responsible for platform attestation of the exact committed bytes.

- [x] 297 unit and regression tests passed on Python 3.12.7, 3.13.12, and 3.14.5.
- [x] Branch-aware coverage was 83%, above the configured 75% gate.
- [x] Ruff passed with no findings.
- [x] Root `VOICE.md`, full template, and spoken template passed strict L3 validation.
- [x] All 13 contract example/template files passed their applicable L0-L3 validation profile.
- [x] Python, Node.js, and shell lite loaders produced equivalent output.
- [x] Independent TypeScript core verification passed all 57 conformance vectors; strict TypeScript compilation passed.
- [x] `npm audit` reported zero vulnerabilities; .NET 8 built with zero warnings and zero errors.
- [x] A real Azure OpenAI run completed all 14 eval cases; deterministic scoring passed 14/14 and the committed records are bound to contract, corpus, request, and response hashes without endpoint or secret fields.
- [x] Wheel and normalized sdist were built twice with the exact pinned toolchain and were byte-identical across both builds.
- [x] Twine metadata checks passed; wheel `RECORD`, package contents, and sdist inventory were verified exactly.
- [x] SPDX 2.3 SBOM and unsigned in-toto/SLSA provenance were generated deterministically and verified against the two distributions.
- [x] JSON, JSONL, YAML, TOML, OpenAPI, GitHub Actions, Docker Compose, Kubernetes YAML, CFF, and local Markdown-link checks passed.
- [x] Source containment, symlink and `extends` handling, YAML resource limits, selector tombstones, sidecar limits, release archive limits, and evaluation provenance have regression coverage.
- [x] Nemotron compilation is ASCII-only, preserves higher-priority application instructions, and stays within the total 5,000-character instruction budget.

Not locally verified: Python 3.10 and 3.11; Docker image execution; Linux and Windows hosted CI; GitHub artifact attestation; PyPI trusted publication; an independent security review; external implementations; vendor or standards-body adoption. No public remote or canonical schema URL is configured in this checkout. These are external gates, not properties proven by this local build.
