# Release artifacts

> **Not current:** the committed `0.1.0a1` wheel and source distribution predate the active remediation work. Their recorded hashes remain valid for those historical files, but they must not be published as artifacts of the current source tree. Rebuild them, set `artifact_status`, `source_revision`, and `source_sha256` in `BUILD_INFO.json`, regenerate `SHA256SUMS`, commit the release tree, and run `scripts/build_release.py` plus `scripts/verify_release.py` before release.

- `voicemd-0.1.0a1-py3-none-any.whl`: installable Python reference CLI/library.
- `voicemd-0.1.0a1.tar.gz`: Python source distribution containing the full source pack except generated release artifacts.
- `SHA256SUMS`: checksums for both package artifacts.
- `BUILD_INFO.json`: machine-readable build and verification metadata.
- `VERIFICATION.md`: completed quality-gate summary.

Install the wheel:

```bash
python -m pip install voicemd-0.1.0a1-py3-none-any.whl
voicemd --version
```

The historical wheel declares `PyYAML>=6.0` and `jsonschema>=4.21`. The repository-level `lite/` loaders remain the zero-dependency option.
