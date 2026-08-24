# Historical verification record — 2026-08-24

> This record applies to the committed `0.1.0a1` artifacts, not to the current remediated source tree. `release/BUILD_INFO.json` marks them `stale`; the hardened release verifier intentionally rejects them until a clean rebuild replaces this record.

- [x] 30 unit and regression tests passed.
- [x] Root `VOICE.md`, full template, and spoken template passed strict L3 validation.
- [x] All 13 VoiceMD example/template files passed their applicable L0–L3 validation level.
- [x] Wheel installed and executed from a clean target directory.
- [x] Source distribution extracted and passed the complete test suite.
- [x] Packaged schema, templates, and Agent Skill were present in the wheel.
- [x] Shared adapter ownership and non-destructive uninstall were regression-tested.
- [x] `--mode explicit` did not create automatic bootstraps and emitted explicit-only skill metadata.
- [x] HTTP sidecar health, prompt compilation, and lint endpoints passed smoke tests.
- [x] Nemotron profile compiled to ASCII within its prompt budget.
- [x] Python, Node.js, and shell lite loaders produced equivalent output.
- [x] JSON, JSONL, OpenAPI, Docker Compose, and Kubernetes YAML parsed successfully.
- [x] Local Markdown links resolved.
- [x] Release artifact checksums generated.
