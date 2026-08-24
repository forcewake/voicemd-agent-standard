# VoiceMD core conformance corpus

`vectors.json` is the language-neutral corpus for deterministic VoiceMD core
semantics. It covers:

- source and selector deep-merge behavior, including preservation of dormant
  selector `null` and ID-based `disabled: true` deletion operators, plus
  `rules`/`tests` merge-by-`id`;
- profile and selector precedence;
- RFC 8785 JSON Canonicalization Scheme (JCS) payloads and SHA-256 hashes;
- compact prompt compilation;
- normalized portable regex matching;
- portable deterministic assertion evaluation;
- inputs that implementations must reject.

The VoiceMD JCS interoperability profile rejects every finite mathematical
integer outside `-9007199254740991` through `9007199254740991`, regardless of
whether its source JSON lexeme used decimal or exponent notation. Finite
non-integer numbers otherwise use RFC 8785 serialization. Before canonicalizing
Markdown bodies, implementations normalize CRLF and CR to LF, then trim only
U+0009, U+000A, U+000D, and U+0020. Other Unicode whitespace, including U+0085,
is preserved.

Portable regex matching normalizes CRLF, CR, U+2028, and U+2029 in candidate
text to LF before applying the ASCII-pattern rule with the declared `i`, `m`,
and `s` flags. These vectors exercise matching behavior; regex grammar and
safety validation remain a separate conformance surface.

Core `must_contain` and `must_not_contain` assertions fold ASCII `A`-`Z` only.
They do not perform Unicode case folding or normalization. `max_words` counts
maximal runs of code points outside these ASCII separator ranges: U+0000-002F,
U+003A-0040, U+005B-0060, and U+007B-007E. `ascii_only: true` requires every
code point to be U+0000-007F; false is a no-op. `lint_clean: true` means the
selected contract's deterministic linter returned zero findings of any
severity. The standalone TypeScript corpus runner does not execute
`lint_clean`, because it has no complete contract linter.

An assertion case with no effective core assertion (for example an empty,
extension-only, or false-only assertion mapping) fails instead of passing
vacuously. Executable count/budget fields normalize finite integral JSON
Numbers and are capped at `9007199254740991`. Selector blankness uses exactly
U+0009-U+000D, U+0020, U+0085, U+00A0, U+1680, U+2000-U+200A, U+2028, U+2029,
U+202F, U+205F, and U+3000; U+200B is nonblank.

Run the independent Node verifier from the repository root:

```bash
node integrations/typescript/generated/conformance-verifier.js conformance/vectors.json
```

Or, after installing the TypeScript development dependency:

```bash
npm --prefix integrations/typescript run conformance
```

The TypeScript implementation does not import, invoke, or shell out to the
Python package. Its generated JavaScript uses Node built-ins only. The corpus
tests deterministic resolver/compiler behavior plus the explicitly bounded
regex-matching and assertion semantics above. It does not claim full JSON
Schema validation, YAML parsing, discovery/filesystem security, regex grammar
validation, contract linting, or harness interoperability. Those remain
separate conformance surfaces.

Vector IDs are stable. Changing an expected result is a normative compatibility
change and should be reviewed together with the corresponding specification
language.
