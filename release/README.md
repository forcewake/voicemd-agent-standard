# Release artifacts

This directory contains the complete local release bundle for VoiceMD `0.1.0a3`, built from source revision `35d0f9325c369a7a982d24a3cb63ceb25e13cb27`.

- `voicemd-0.1.0a3-py3-none-any.whl`: installable Python CLI and library.
- `voicemd-0.1.0a3.tar.gz`: normalized Python source distribution.
- `SBOM.spdx.json`: SPDX 2.3 software bill of materials.
- `PROVENANCE.intoto.jsonl`: unsigned in-toto/SLSA build statement.
- `SHA256SUMS`: checksums for the two distributions and two supply-chain records.
- `BUILD_INFO.json`: source identity, source snapshot, toolchain, checksums, and verified gates.
- `VERIFICATION.md`: local verification evidence and its explicit limits.

Install the wheel directly:

```bash
python -m pip install release/voicemd-0.1.0a3-py3-none-any.whl
voicemd doctor
```

The wheel declares `PyYAML>=6.0`, `jsonschema>=4.21`, and `rfc8785>=0.1.4,<1`. The repository-level `lite/` loaders remain the dependency-free path.

Verify the distributions and their supply-chain metadata without executing artifact code:

```bash
python scripts/verify_release.py \
  --distributions release \
  --metadata release \
  --source-root . \
  --source-revision 35d0f9325c369a7a982d24a3cb63ceb25e13cb27 \
  --release-revision 35d0f9325c369a7a982d24a3cb63ceb25e13cb27
```

`--trusted-runtime-checks` is available for the complete outer release ZIP. It installs and executes self-built artifact code on the host; it is not a sandbox or an authenticity proof.
