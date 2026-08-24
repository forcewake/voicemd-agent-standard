# Release artifacts

These `0.1.0a1` artifacts are current for source revision `7a0e671ad3aead1d5617eb5806bfe7ac702e3738`. Verify `SHA256SUMS`, `BUILD_INFO.json`, and the final outer ZIP before redistribution.

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

The wheel declares `PyYAML>=6.0` and `jsonschema>=4.21`. The repository-level `lite/` loaders remain the zero-dependency option.
