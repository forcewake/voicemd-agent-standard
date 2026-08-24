# Roadmap

## Draft 0.1 external stabilization

- Collect at least ten independent real-world contracts across software, enterprise support, consumer assistants, and voice agents.
- Run the language-neutral conformance vectors against at least one implementation maintained outside this repository.
- Validate the bundled activation, exact-output, translation, and tool-result corpus across independent model/harness deployments.
- Publish a canonical repository remote and stable canonical schema URL.
- Obtain and publish an independent security review.
- Add signed release artifacts, provenance attestations, and a software bill of materials.
- Add signed remote bundle design without enabling implicit remote fetches.
- Improve language-aware linting beyond literal phrases and regex.

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
