# Release checklist

- [ ] Update draft/spec/package versions consistently.
- [ ] Start from a clean, committed Git source revision and record its full hash.
- [ ] Run the complete test suite on CPython 3.10 through 3.14 on Linux.
- [ ] Run the cross-platform suite on current macOS and Windows runners.
- [ ] Run strict validation on all structured templates.
- [ ] Run `node integrations/typescript/generated/conformance-verifier.js conformance/vectors.json`.
- [ ] Regenerate compiled examples.
- [ ] Set `SOURCE_DATE_EPOCH` from the source commit, build the sdist and wheel twice, canonicalize each setuptools sdist with `scripts/build_release.py --normalize-sdist ...`, and require byte-identical output.
- [ ] Install the exact tool versions from `constraints/build.txt` and build with `--no-isolation`.
- [ ] Install wheel into a clean virtual environment.
- [ ] Run CLI smoke tests from the installed wheel.
- [ ] Test adapter installation and uninstall in a temporary repository.
- [ ] Recheck official harness documentation and update compatibility date.
- [ ] Recheck NVIDIA VoiceChat API constraints and model card.
- [ ] Run security regression cases.
- [ ] Review schema compatibility and migration notes.
- [ ] Update changelog.
- [ ] Generate canonical `SBOM.spdx.json` and `PROVENANCE.intoto.jsonl` with `scripts/build_release.py --distributions ...`.
- [ ] Verify the wheel, sdist, SBOM, and provenance offline with `scripts/verify_release.py --distributions ...`.
- [ ] Create checksums for the package artifacts and both release-metadata files.
- [ ] Record every artifact and checksum in `release/BUILD_INFO.json`.
- [ ] Record both `artifacts` and `release_metadata` in `release/BUILD_INFO.json`.
- [ ] Record and verify `source_sha256` for the embedded non-release source paths, executable modes, and bytes.
- [ ] Set `artifact_status` to `current` only after the artifacts and source revision match.
- [ ] Commit the final release tree; the outer ZIP builder rejects tracked or untracked changes.
- [ ] Build the outer ZIP twice with `scripts/build_release.py` and compare hashes.
- [ ] Generate an external outer-ZIP statement with `--provenance-output`; do not try to embed a commit hash that self-identifies the commit containing that same file.
- [ ] Run metadata verification against the final outer ZIP and its expected release revision. Metadata-only verification is the default.
- [ ] For a self-built or otherwise trusted archive only, rerun with `--trusted-runtime-checks`; this explicitly installs and executes archive content on the host.
- [ ] Confirm external archive provenance passes before any optional trusted runtime checks. The local unsigned statement proves consistency, not publisher identity or code safety.
- [ ] Confirm trusted runtime subprocesses receive only the release verifier's path, locale, certificate, credential-free proxy, fixed isolation variables, and an empty temporary home. Do not pass cloud, API, CI-token, user-home, or arbitrary inherited variables.
- [ ] Confirm hosted CI ran the full release verifier, independent TypeScript conformance runner, package/client jobs, and Docker build-and-run smoke test.
- [ ] Confirm the ZIP contains no environment, cache, untracked, symlink, or build-context files.
- [ ] Tag the exact verified commit with `v<package-version>`.
- [ ] Confirm the PyPI Trusted Publisher, protected `pypi` environment, tag policy, and required reviewers are configured before dispatching `.github/workflows/publish.yml`.

## Revision and attestation semantics

`source_revision` identifies the commit whose non-release source snapshot produced the Python artifacts. `release_revision`, when present in `BUILD_INFO.json`, identifies the checkout used to generate the release metadata. Neither field proves that a tracked file belongs to the commit hash written inside itself; that would be a self-reference and cannot be made stable.

The external outer-ZIP provenance statement solves that boundary. It names the final ZIP and SHA-256, records the exact Git revision from which the ZIP was built, and can be verified with `--expected-release-revision`. The local `PROVENANCE.intoto.jsonl` is deterministic but unsigned. It becomes signed evidence only when a trusted system signs it or the subjects. The publish workflow uses GitHub's short-lived OIDC/Sigstore attestation mechanism for the wheel and sdist; it does not claim a SLSA level.

When `--provenance` is supplied, the verifier validates archive structure, integrity, subject digest, and expected release revision before extraction. The statement is unsigned local evidence and does not authenticate the publisher. Metadata-only verification is the default and does not execute archive code. `--trusted-runtime-checks` is an explicit opt-in for self-built or otherwise trusted artifacts; it is not a sandbox. Those subprocesses use a small environment allowlist, an empty temporary home, bounded output, and timeouts. Pip also runs with isolated configuration, no prompts, and no cache. Credential-bearing proxy URLs and private indexes that depend on credential environment variables are intentionally unsupported.

PyPI publication requires a separately configured Trusted Publisher for this repository, workflow filename, and `pypi` environment. The workflow intentionally has no long-lived PyPI token. See the [PyPI Trusted Publisher setup](https://docs.pypi.org/trusted-publishers/adding-a-publisher/) and [GitHub artifact attestation documentation](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations).
