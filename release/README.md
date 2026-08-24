# Release artifacts

These `0.1.0a2` files were built from source revision `fc7adad1b5a7ea5cb17b7ed7349256c5f858ea9c` and are stale for the newer source tree. Do not install or redistribute them as the current release; rebuild and verify replacement artifacts first.

- `voicemd-0.1.0a2-py3-none-any.whl`: installable Python CLI and library.
- `voicemd-0.1.0a2.tar.gz`: normalized Python source distribution.
- `SBOM.spdx.json`: SPDX 2.3 software bill of materials.
- `PROVENANCE.intoto.jsonl`: unsigned in-toto/SLSA build statement.
- `SHA256SUMS`: checksums for all four release files.
- `BUILD_INFO.json`: source revision, source snapshot digest, toolchain, checksums, and verified gates.
- `VERIFICATION.md`: evidence and explicit limits of the local release verification.

Install the wheel:

```bash
python -m pip install release/voicemd-0.1.0a2-py3-none-any.whl
voicemd doctor
```

The wheel declares `PyYAML>=6.0`, `jsonschema>=4.21`, and `rfc8785>=0.1.4,<1`. The repository-level `lite/` loaders remain the dependency-free path.

Verify the distributions and their supply-chain metadata without executing artifact code:

```bash
python scripts/verify_release.py \
  --distributions release \
  --metadata release \
  --source-root . \
  --source-revision fc7adad1b5a7ea5cb17b7ed7349256c5f858ea9c \
  --release-revision fc7adad1b5a7ea5cb17b7ed7349256c5f858ea9c
```

`--trusted-runtime-checks` additionally installs and executes artifact code on the host. It is only appropriate for a self-built or otherwise trusted artifact and is not a sandbox or authenticity proof.
