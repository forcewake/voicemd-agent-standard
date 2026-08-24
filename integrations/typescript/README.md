# VoiceMD TypeScript integration

`voicemd-client.ts` is the HTTP sidecar client. `conformance-verifier.ts` is an
independent resolver, compact compiler, VoiceMD-profiled RFC 8785
canonicalizer, portable regex matcher, deterministic assertion evaluator, and
corpus runner. The verifier does not import or invoke the Python reference
package.

```bash
npm ci
npm run check
npm run conformance
```

The generated JavaScript in `generated/` has no runtime dependencies beyond
Node built-ins. It intentionally implements only the deterministic behaviors in
`conformance/vectors.json`; YAML, discovery, JSON Schema validation, regex
grammar validation, complete contract linting, installation, and HTTP serving
are outside this verifier's scope. In particular, `lint_clean` requires the
selected contract's linter and is documented by the corpus but is not executed
by this standalone verifier.
