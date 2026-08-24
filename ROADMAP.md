# Roadmap

## Draft 0.1 external stabilization

- Collect at least ten independent real-world contracts across software, enterprise support, consumer assistants, and voice agents.
- Run the language-neutral conformance vectors against at least one implementation maintained outside this repository.
- Validate the bundled activation, exact-output, translation, and tool-result corpus across independent model/harness deployments.
- Stabilize schema hosting beyond the initial version-pinned GitHub URL.
- Obtain and publish an independent security review.
- Add publisher-signed release artifacts and hosted provenance attestations; the local build already emits an unsigned provenance statement and SPDX SBOM.
- Add signed remote bundle design without enabling implicit remote fetches.
- Improve language-aware linting beyond literal phrases and regex.
- Add scored audio-input Realtime replay, WebRTC microphone UI, VAD/barge-in cases, and tool-boundary cases on top of the server-side Azure proof harness.

## Draft 0.2 candidates

- Standard selector envelope for runtime context.
- Portable eval result format.
- Pronunciation lexicon profile compatible with common TTS/SSML systems.
- Formal compatibility layer for brand-oriented VOICE.md documents.
- Stable MCP resource/tool contract.
- Complete TypeScript implementation covering YAML parsing, filesystem discovery, source budgets, and runtime APIs in addition to the bundled deterministic-core verifier.

## 1.0 criteria

- Independent full implementations in at least two languages, with at least one maintained outside this repository.
- Versioned compatibility and conformance suite published from the canonical public repository and run by independent implementations.
- Published independent security review with material findings resolved or documented.
- At least two agent harnesses or application frameworks documenting first-class integration.
- Governance transferred from a single maintainer model to a small technical steering group.
