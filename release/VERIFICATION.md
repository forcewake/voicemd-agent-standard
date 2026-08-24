# Verification record — 2026-08-25

This record applies to VoiceMD `0.1.0a3`, built from source revision `6f58f31bcb5aac7ffe7730d7af9d576000dff182`. The embedded provenance is deterministic and unsigned.

- [x] 355 unit and regression tests passed; source tests ran on Python 3.13.11 and clean wheel/sdist runtime checks ran on Python 3.14.5.
- [x] Branch-aware coverage was 79%, above the configured 75% gate.
- [x] Ruff completed with no findings.
- [x] Root, full, spoken, and three Azure demonstration contracts passed strict L3 validation and their inline cases.
- [x] Python, Node.js, and shell lite loaders produced equivalent output.
- [x] Independent TypeScript core verification covered all 57 conformance vectors; strict TypeScript compilation completed.
- [x] `npm audit` reported zero vulnerabilities; .NET 8 built with zero warnings and zero errors.
- [x] The standard-first GitHub Pages tree passed its closed-inventory verifier: 125 files, 117 checksummed evidence files, and 11 sanitized Azure proof runs.
- [x] The real Azure OpenAI evidence is checksum-bound and excludes endpoint and secret fields; exact transcription remains outside VoiceMD activation.
- [x] Wheel and normalized sdist were built twice with the pinned toolchain and were byte-identical across both builds.
- [x] Twine metadata checks, wheel `RECORD`, package contents, and exact sdist inventory were verified.
- [x] Clean installs exercised the wheel with the `azure-voice` extra, `voicemd-azure doctor`, Nemotron compilation, the TypeScript verifier, and the sdist test suite.
- [x] SPDX 2.3 SBOM and unsigned in-toto/SLSA provenance were generated deterministically and verified against both distributions.
- [x] Release verification covers a closed `release/` inventory, canonical ZIP boundaries, local and central ZIP records, member types, binary WAV assets, and controlled UTF-8 errors.
- [x] Source containment, symlink and `extends` handling, YAML resource limits, selector tombstones, sidecar limits, archive limits, and evaluation provenance have regression coverage.
- [x] Nemotron compilation is ASCII-only, preserves higher-priority application instructions, and stays within the total 5,000-character instruction budget.

Outside this local record: GitHub-hosted Linux/Windows/macOS CI, GitHub artifact attestations, PyPI trusted publication, an independent security review, independent implementations, and vendor or standards-body adoption. Those states must be checked at their respective public endpoints.
