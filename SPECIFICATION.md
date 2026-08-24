# VOICE.md Agent Communication Contract Specification

Version: `0.1.0-draft.1`  
Format version: `voice_spec: "0.1"`  
Status: Independent public draft  
Date: 2026-08-24

## 1. Status and terminology

This document defines the draft VOICE.md Agent Communication Contract. It is suitable for experimentation and production use under explicit version pinning, but it is not represented as a consensus industry standard.

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHOULD**, **SHOULD NOT**, and **MAY** are to be interpreted as normative requirements.

## 2. Purpose

A `VOICE.md` specifies observable communication behavior for an AI system. It exists to preserve a recognizable and governable interaction style across model providers, agent harnesses, applications, channels, audiences, and modalities.

It MAY specify:

- linguistic voice, register, vocabulary, and formatting;
- response structure and adaptive verbosity;
- uncertainty, confidence, evidence, and correction behavior;
- disagreement, challenge, clarification, and escalation behavior;
- audience-, surface-, tone-, and runtime-specific profiles;
- spoken-dialogue and text-to-speech constraints;
- deterministic lint rules and evaluation cases.

## 3. Non-goals and authority boundary

A `VOICE.md` MUST NOT grant authority or change:

- facts or source truth;
- safety policy;
- legal, regulatory, or compliance obligations;
- permissions or approval requirements;
- tool availability, selection, parameters, or side effects;
- access to secrets or external systems;
- hidden reasoning or requests to expose it;
- exact quotations;
- an explicitly required machine-readable schema.

A runtime MUST treat any such instruction inside `VOICE.md` as out of scope. A `VOICE.md` is not an agent constitution, capability manifest, security policy, persona identity store, or tool definition.

Normative precedence is:

1. Platform safety and applicable policy.
2. System and developer instructions.
3. Factual, legal, permission, tool, and required output-schema constraints.
4. Explicit user instructions for the current output.
5. Active VOICE.md profile and most-specific source.
6. Broader VOICE.md sources and defaults.
7. Model defaults.

Where a user explicitly requests an exact quotation, faithful translation, strict schema, or machine output, the runtime MUST preserve that requirement rather than “improving” it with voice rules.

## 4. File and encoding

The canonical filename is `VOICE.md`. UTF-8 is REQUIRED. Line endings MAY be LF or CRLF; implementations SHOULD normalize internally.

A file contains:

1. optional YAML frontmatter delimited by `---`;
2. optional Markdown guidance.

A plain Markdown file with no frontmatter is a valid L0 contract.

Structured frontmatter MUST use the JSON-compatible YAML subset. Mapping keys MUST be strings and MUST NOT be duplicated. Implementations MUST parse only `true` and `false` (case-insensitive) as implicit booleans; YAML 1.1 spellings such as `yes`, `no`, `on`, and `off` are strings. Date-shaped scalars are strings unless an implementation rejects an explicit non-JSON timestamp tag. Non-finite numbers, sets, binary values, recursive aliases, and other values that cannot be represented in strict JSON MUST be rejected. YAML aliases MAY be supported when the resulting value is an acyclic JSON-compatible tree.

The published JSON Schema describes the fully resolved contract. An individual source used as an `extends` file or hierarchy overlay MAY be partial and MAY contain merge-time `null` deletion operators; implementations MUST resolve those sources before applying the schema.

## 5. Minimal structured contract

```yaml
---
voice_spec: "0.1"
kind: VoiceContract
name: "Direct technical advisor"
version: "1.0.0"
activation:
  mode: contextual
identity:
  sounds_like: ["A competent practitioner"]
  not_like: ["A marketing copywriter"]
---
```

For L1 and above, `voice_spec`, `kind`, and `name` are REQUIRED. `kind` MUST equal `VoiceContract` for version `0.1`.

## 6. Conformance levels

### 6.1 L0 Plain

A non-empty Markdown file. No structured parsing is required. An implementation MAY inject the complete file as communication guidance.

### 6.2 L1 Core

Valid structured frontmatter plus concrete communication guidance. Guidance is concrete when the resolved contract has non-empty Markdown, identity, response, language, lexicon, formatting, or an enabled rule with an instruction, description, or pattern. Metadata alone does not conform to L1.

### 6.3 L2 Contextual

An L1 contract that adds one or more of:

- explicit activation or authority boundaries;
- epistemic or interaction behavior;
- audience, surface, tone, or profile variants;
- speech behavior;
- hierarchical inheritance.

### 6.4 L3 Testable

An L1 contract with at least one non-vacuous deterministic rule or locally executable deterministic test. An implementation MAY report L3 whether or not the contract also uses L2 contextual features.

A deterministic rule contributes to L3 only when it is enabled and defines a valid supported `pattern` plus an explicit `assert`. A test contributes only when it is enabled, supplies an inline string `response`, and has at least one effective core assertion. `must_contain` and `must_not_contain` are effective only when non-empty; `ascii_only` and `lint_clean` are effective only when true. A test that requires an externally supplied response remains valid evaluation metadata but does not by itself establish L3 in the reference validator.

An external conformance suite MAY establish an ecosystem-specific level, but the core `L3-testable` result is based only on deterministic evidence present in the resolved contract. Implementations MUST NOT assign L3 merely because a `rules` or `tests` array is non-empty.

The reference CLI `--strict` option is an additional deployment-validation profile, not another conformance level. It rejects L0 and structured metadata without concrete guidance, and requires `activation.mode` plus the complete authority declaration described in Section 11.1. A contract can conform to L1 or L2 without opting into that stricter authoring profile.

## 7. Discovery

The reference discovery algorithm is normative for implementations claiming **VoiceMD Hierarchical Discovery 0.1**.

### 7.1 Explicit source

An explicit source supplied by API, CLI, or configuration MUST take precedence over automatic discovery. The reference environment variable is `VOICE_MD`. Multiple paths MAY be provided in broad-to-specific order using the operating system path separator.

### 7.2 Global source

An implementation MAY load one global source from `${VOICE_MD_HOME:-~/.config/voicemd}`. It MUST select at most one candidate in this order:

1. `VOICE.override.md`;
2. `VOICE.md`;
3. `.voice/VOICE.override.md`;
4. `.voice/VOICE.md`.

### 7.3 Project hierarchy

The implementation identifies the project root in this order: an explicit `VOICE_MD_ROOT`, the nearest `.voicemd-root` or version-control root, then a common project marker such as `pyproject.toml` or `package.json`. Starting at that root and walking to the current working directory, it selects at most one candidate per directory using the same order. `VOICE_MD_ROOT` MUST contain the discovery start directory.

Sources MUST be applied broad-to-specific. A source closer to the current working directory has higher precedence.

### 7.4 Overrides

`VOICE.override.md` replaces `VOICE.md` at the same directory level for discovery. It does not erase broader directories unless its actual content overrides those values.

### 7.5 Dot-directory form

`.voice/VOICE.md` and `.voice/VOICE.override.md` are equivalent lower-priority candidate names for teams that prefer a configuration directory.

## 8. Inheritance with `extends`

Structured files MAY contain:

```yaml
extends:
  - ../brand/VOICE.md
  - ./domain/VOICE.md
```

Paths resolve relative to the declaring file and load before it. Implementations MUST detect cycles and SHOULD enforce a depth limit. The reference limit is eight `extends` edges from a discovery root; a root with no `extends` has depth zero.

`extends` forms an ordered directed acyclic graph, not only a tree. The reference traversal is depth-first and left-to-right in the declared path order. Each canonical resolved path is applied at most once, at its first encounter. A path already loaded through an earlier branch is not traversed again. Cycles MUST still be detected against the active recursion stack before a previously loaded path is skipped.

The core specification supports local filesystem paths. Core implementations MUST NOT fetch remote `extends` implicitly. An extension MAY support remote sources only with explicit trust policy, immutable pinning, integrity verification, cache behavior, and failure semantics.

## 9. Merge semantics

The later source is the override.

- Scalars replace earlier values.
- Objects deep-merge recursively.
- A mapping value of `null` is a merge operator that deletes the corresponding inherited key. It MUST NOT remain in the resolved contract. Use an empty object or array when that empty value, rather than key absence, is intended.
- Most arrays replace earlier arrays.
- The following arrays append unique values: activation include/exclude, authority may/must-not control, allowed languages, preferred/forbidden lexicon, formatting avoid, and speech avoid.
- `rules`, `tests`, and `examples` merge by string `id`.
- An ID-based item with `disabled: true` removes the inherited item.
- Markdown bodies concatenate broad-to-specific. Later body guidance wins when it directly conflicts with earlier guidance.

The append-unique array rules apply while merging filesystem sources. Audience, surface, tone, and profile `overrides` are contextual selectors and use ordinary replacement for arrays. This distinction lets a profile narrow a source-level list, for example from `language.allowed: [en, ru]` to `[en]`.

Implementations MUST document any deviation.

## 10. Activation

`activation.mode` has four values:

- `contextual`: apply when the output is human-facing;
- `always`: make the contract available for every task, while still respecting exclusions and the authority boundary;
- `explicit`: apply only when explicitly selected;
- `off`: do not apply.

`contextual` is RECOMMENDED.

Activation is evaluated in this order: the authority boundary and higher-priority requirements first; `mode: off`; an explicit off-marker; output-category exclusion; then mode-specific inclusion. `explicit` requires explicit API selection or an on-marker. `contextual` applies to the default human-facing categories plus any category named by `include`. `always` does not require an included category but still respects exclusions. An off-marker wins if both on- and off-markers occur.

The active audience, surface, tone, and profile overrides MUST be resolved before this decision. A selector override of `activation.mode`, include/exclude categories, or markers therefore controls the selected context; an implementation MUST NOT decide from the unselected base contract and compile a different selected contract afterward.

Default included categories are chat, explanations, human messages, documents, reports, summaries, UI copy, and spoken dialogue.

Default exclusions are code, patches, diffs, structured data, required JSON/XML/YAML, SQL, tool calls/results, exact quotations, and raw data.

Implementations MAY support explicit markers. Recommended markers are `@voice`/`voice:on` and `@no-voice`/`voice:off`.

After case folding, a category MUST NOT occur in both `include` and `exclude`, and a marker MUST NOT occur in both `on_markers` and `off_markers`. Such overlap is an invalid contract rather than an implicit precedence rule.

## 11. Structured fields

### 11.1 `authority`

Declares in-scope and out-of-scope control. L2 contracts SHOULD include it even though runtime enforcement is mandatory regardless of declaration.

`may_control` MUST NOT contain any protected capability listed in Section 3, and the same semantic capability MUST NOT occur in both `may_control` and `must_not_control`. The reference strict validator additionally requires `must_not_control` to cover facts, safety, legal/compliance obligations, permissions, tools, secrets, hidden reasoning, exact quotations, and required output schemas, plus a non-empty `precedence` statement. These declarations are defense-in-depth metadata; the runtime remains responsible for enforcing the Section 3 boundary even when `authority` is absent.

### 11.2 `identity`

Defines observable communication identity. `sounds_like` and `not_like` SHOULD contain behavioral contrasts, not only adjectives.

### 11.3 `response`

Defines opening, structure, verbosity, length, examples, repetition, and other response-level behavior.

### 11.4 `language`

Defines default/allowed languages, user-language matching, mixing, and translation behavior. Language codes SHOULD use BCP 47 where practical. `match_user: true` selects among allowed languages; it does not expand `language.allowed`.

`language.default` is the normative default-language field. `default_language` is a deprecated `0.1` compatibility alias. When only the alias is present, a compiler MUST treat it as `language.default`; when both are present they MUST be equal, otherwise the contract is invalid. A declared `language.default` MUST occur in `language.allowed` when that list is present.

### 11.5 `lexicon`

Defines preferred/forbidden phrases, replacements, and pronunciation hints. A term MUST NOT be both preferred and forbidden after case folding.

### 11.6 `epistemics`

Defines observable behavior around certainty, uncertainty, sources, assumptions, inference, correction, and precision. It MUST NOT be used to fabricate confidence or citations.

### 11.7 `interaction`

Defines disagreement, challenge, clarification, repeated questions, expertise adaptation, escalation, and emotional calibration.

### 11.8 `formatting`

Defines Markdown, headings, lists, tables, emoji, and other presentational behavior. Required output format always takes precedence.

### 11.9 `speech`

Defines spoken turn length, sentence length, TTS behavior, interruptions, pronunciation, ASCII constraints, and speech-specific exclusions. It controls textual delivery instructions, not the acoustic identity of a voice.

### 11.10 `audiences`, `surfaces`, and `tones`

These are named mappings whose values are partial contract overrides.

A surface describes the output channel or artifact type, such as `chat`, `document`, `ui_copy`, or `spoken`. An audience describes the recipient. A tone describes a situational variation.

### 11.11 `profiles`

A profile binds named audience, surface, and tone variants and MAY include an `overrides` mapping:

```yaml
profiles:
  executive_brief:
    audience: executive
    surface: executive_summary
    tone: neutral
    overrides:
      response:
        max_words: 180
```

Explicit runtime arguments override profile selectors. Audience, surface, and tone variants are merged first; the profile-local `overrides` mapping is merged last because it is the most specific part of the selected profile.

When the `profiles` mapping contains a member named `default` and no explicit profile is supplied, a compiler MUST select that profile automatically. Explicit runtime audience, surface, and tone arguments replace the corresponding selector names from the selected profile. Variant application order is audience, then surface, then tone, followed by profile-local `overrides`. Every selector reference in a profile or test MUST name an existing variant or profile.

### 11.12 `runtime`

Contains implementation hints such as `max_prompt_chars` or compact-mode preference. Hints MUST NOT weaken safety or authority constraints.

### 11.13 `rules`

Rules require a stable `id`. A deterministic regex rule MAY define:

- `pattern`;
- `assert`: `must_match` or `must_not_match`;
- `severity`: `info`, `warning`, or `error`;
- `message`.

A rule without a pattern is a normative natural-language rule for model-based evaluation.

For a regex rule, `pattern` and `assert` MUST occur together. A core implementation MUST reject syntactically invalid patterns before evaluation. Because the reference Python regex engine has no execution timeout, its supported subset limits a pattern to 2,048 characters and rejects unbounded repetition of a group that itself contains a variable-width repeat or alternation. This intentionally rejects obvious catastrophic-backtracking forms such as `(a+)+` and `(a|aa)+`. Implementations with a bounded-time regex engine MAY safely support a broader subset but MUST document the deviation.

### 11.14 `tests`

Tests require an `id` and MAY define prompt, inline response, selectors, and assertions. Core deterministic assertions are:

- `must_contain`;
- `must_not_contain`;
- `max_words`;
- `ascii_only`;
- `lint_clean`.

Model-generated response execution is outside the core format; the package includes an OpenAI-compatible runner.

Every test MUST contain an `assertions` mapping and at least one of `prompt` or `response`. Empty or extension-only assertions do not contribute to core L3. IDs in each of `rules`, `tests`, and `examples` MUST be unique within each source and in the resolved contract. Duplicate IDs are invalid rather than silently last-wins. An inherited ID MAY be updated by a later source or removed with `disabled: true` under the merge semantics in Section 9.

### 11.15 Extensions

Unknown keys are permitted for forward compatibility. Vendor or organization extensions SHOULD use an `x-` prefix.

## 12. Compilation

A compiler transforms the resolved contract into runtime instructions. A configured prompt character budget MUST be at least 256 characters; JSON contract output MUST use strict JSON (including rejection of NaN and infinities), remain valid JSON, and MUST NOT be text-truncated. It MUST:

- preserve the authority boundary;
- identify active selectors when useful;
- apply source/profile precedence deterministically;
- avoid silently changing facts or task requirements;
- provide a deterministic output for the same inputs;
- disclose truncation when a character budget is applied.

For an ASCII output format, normalization MUST occur before the final character-budget check and truncation because transliteration may expand text. The returned prompt, including its truncation disclosure, MUST NOT exceed the configured budget.

### 12.1 Canonical selected-contract hash

For portable cache keys and provenance, the reference canonical payload is a JSON object with exactly three members:

- `contract`: the fully resolved contract after selector/profile application and deprecated-field normalization;
- `markdown_bodies`: the ordered non-empty Markdown bodies, with CRLF/CR normalized to LF and surrounding whitespace removed;
- `active`: `profile`, `audience`, `surface`, and `tone`, using JSON `null` when absent.

The payload MUST exclude filesystem paths, timestamps, compiler version, and other host-specific metadata. Serialize it as UTF-8 strict JSON with lexicographically sorted object keys, no insignificant whitespace, literal non-ASCII characters, and no NaN or infinities. The lowercase hexadecimal SHA-256 of those UTF-8 bytes is the canonical selected-contract hash. A cache key SHOULD additionally include the compiler version and requested output format because equal contract semantics do not guarantee identical rendering across compiler releases.

A compiler MAY emit:

- human-readable prompt Markdown;
- compact prompt text;
- JSON;
- canonical JSON or its SHA-256 fingerprint;
- ASCII-normalized prompt text;
- a provider-specific envelope.

Compilation is not mandatory for L0 use.

## 13. Harness integration

A harness MAY integrate through:

1. Native recognition of `VOICE.md`.
2. Agent Skill progressive disclosure.
3. A small `AGENTS.md`/`CLAUDE.md`/rules bootstrap that reads the contract when relevant.
4. CLI invocation.
5. HTTP or MCP resource/tool.
6. Application-side system/developer-prompt composition.

On-demand integration is RECOMMENDED for coding agents because the full contract is irrelevant to most machine-output tasks.

A harness adapter MUST NOT claim native `VOICE.md` support when it is implemented through a generic skill, import, rule, or prompt.

## 14. Spoken and real-time agents

A spoken profile SHOULD specify:

- maximum turn length;
- sentence length;
- interruption policy;
- TTS-friendly wording;
- pronunciation or acronym behavior;
- formatting exclusions;
- platform character restrictions.

Tool results sent back to a speech model SHOULD be transformed into concise, speakable text only after preserving their factual meaning.

## 15. Internationalization

UTF-8 is the source format. A contract MAY be authored in any language supported by the target model. A profile MAY restrict runtime prompt language for a model-specific reason.

ASCII compilation is a lossy adapter. Implementations SHOULD prefer an intentionally authored English/ASCII spoken profile instead of relying solely on transliteration.

## 16. Security

`VOICE.md` is trusted project configuration and MUST be reviewed like code. Implementations MUST NOT automatically load a same-named file from an untrusted upload, retrieved webpage, data record, or model-generated working directory.

A production runtime SHOULD:

- pin contract version and source hash;
- log active source paths and selectors;
- limit source size and inheritance depth;
- reject or sandbox remote resolution;
- separate voice prompt injection from tool authorization;
- test conflicts with safety, schema, and exact-output instructions;
- support rollback.

## 17. Versioning

`voice_spec` versions the format, not the individual contract. Contract authors SHOULD use a separate semantic `version`.

Patch-compatible format revisions use the same `0.1` major/minor identifier. A breaking format change requires a new minor while the format is pre-1.0. Implementations SHOULD reject unknown incompatible versions in strict mode and MAY process them in permissive mode with warnings.

## 18. Reference artifacts

The accompanying package contains:

- JSON Schema at `schema/voice.schema.json`;
- Python reference implementation and CLI;
- universal Agent Skill;
- harness adapters;
- application and local-model integrations;
- deterministic and model-based eval examples;
- simple, full, and spoken templates.
