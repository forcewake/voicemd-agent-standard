# Architecture

## Component model

```text
                         authoring
                            |
             +--------------+--------------+
             |                             |
       plain VOICE.md                structured VOICE.md
             |                  YAML frontmatter + Markdown
             +--------------+--------------+
                            |
                    discovery + extends
                            |
                     deterministic merge
                            |
          profile/audience/surface/tone selection
                            |
             exact selected-contract validation
                            |
             +--------------+-------------------+
             |              |                   |
       prompt compiler   JSON contract       lint/eval model
             |              |                   |
      +------+------+   application API     CI / observability
      |             |
 Agent Skill     runtime injection
      |             |
 coding agents   apps / local models / speech
```

## Separation of concerns

VoiceMD intentionally separates seven concerns:

1. **Authorship:** humans define recognizable communication behavior in Markdown and optional YAML.
2. **Resolution:** discovery and inheritance create one deterministic active contract.
3. **Selection:** runtime context selects audience, surface, tone, and profile.
4. **Validation:** the exact selected result must pass the resolved-contract schema and semantic checks.
5. **Compilation:** the selected contract becomes provider-neutral instructions or JSON.
6. **Delivery:** a harness reads the skill/file, or an application injects the compiled prompt.
7. **Verification:** lint rules, eval cases, and language-neutral conformance vectors check observable behavior.

This split prevents a harness adapter from becoming the standard. Codex, Claude Code, Gemini CLI, an internal orchestrator, and a local vLLM server can use different delivery mechanisms while sharing one contract.

## Why Agent Skills are the default harness adapter

A coding agent does not need a long communication contract while editing source, generating tests, or producing tool payloads. An Agent Skill exposes only a name and trigger description until the task requires human-facing output. This is progressive disclosure: the full instructions are loaded on demand.

A small bootstrap in the harness-native instruction file improves trigger reliability without copying the entire contract into every task. The bootstrap establishes activation and authority boundaries; the skill handles discovery and application.

## Runtime contract pipeline

A production application should make the selection explicit:

```text
request context
  surface=spoken
  audience=novice
  tone=neutral
  profile=voicechat
       |
       v
resolve VOICE.md sources
       |
       v
merge and select profile
       |
       v
validate exact selected contract
       |
       +--> fail closed on any schema or semantic error
       |
       v
compile prompt + contract hash
       |
       +--> append to system/developer instructions
       |
       +--> record source/version/hash in telemetry
       |
       +--> lint/evaluate output where appropriate
```

Do not ask the model to infer every surface and audience when the application already knows them.

## Source of truth

`VOICE.md` is the authored source of truth. Compiled prompts are build artifacts. They should not be manually edited because doing so creates drift.

Recommended production metadata:

```json
{
  "voice_spec": "0.1",
  "contract_name": "Principal architect",
  "contract_version": "1.2.0",
  "source_paths": ["VOICE.md", "apps/support/VOICE.override.md"],
  "profile": "spoken_support",
  "compiler": "voicemd/0.1.0a2",
  "compiled_sha256": "..."
}
```

`voicemd compile --format canonical-json` emits the path-independent canonical selected-contract payload using RFC 8785 JSON Canonicalization Scheme (JCS) after applying VoiceMD's stricter safe-integer interoperability profile. `voicemd compile --format sha256` emits the lowercase SHA-256 of those canonical UTF-8 bytes. Portable JSON output omits host paths unless a trusted local operator explicitly requests provenance. Add the compiler version and output format when using the fingerprint as a rendered-prompt cache key.

Structured frontmatter is parsed as the YAML 1.2 JSON schema subset, not with YAML 1.1 implicit scalar rules, and explicit YAML tags are rejected. Mapping keys and values are both charged to the expanded-node budget. Executable count/budget fields normalize finite integral JSON Numbers to safe integers. Selector blankness uses a pinned Unicode code-point set rather than host-language trimming. Deprecated `default_language` aliases are normalized and conflict-checked after selection so the canonical selected object contains only `language.default`. The selected object must also satisfy VoiceMD's cross-language canonicalization domain before JCS serialization.

## Failure strategy

Applications should choose one of three explicit policies:

- **fail closed:** reject startup/request when the pinned contract is invalid;
- **last known good:** continue with a previously validated compiled artifact;
- **voice optional:** omit voice adaptation and continue with base system behavior.

Silent fallback to a different contract is not recommended.

The reference runtime uses fail closed at compile, lint, sidecar, and provider boundaries. `last known good` and `voice optional` are application policies that require an explicit, separately controlled artifact or behavior; they are not silent parser fallbacks.

## Source boundary and resource model

Every explicit, discovered, and inherited source resolves canonically inside an operator-approved root. A symlink cannot widen that root, and `.env`/`.env.*` path components are rejected. Remote `extends` remain disabled in the core implementation.

The default resource envelope is 1 MiB per source, 4 MiB and 64 unique sources across one load, 20,000 expanded YAML nodes (including mapping keys) and 100 alias references per source, 256 selectable contexts per whole-contract validation, and eight `extends` edges. Applications should lower these values where tenant isolation or latency matters. A duplicate canonical source in an inheritance DAG consumes byte/source budgets once.

## Performance and caching

Resolution and compilation are deterministic and can be cached by:

- source path identity, size, change/modification times, plus selectors;
- source content hashes plus compiler version;
- contract semantic version plus deployment version.

Do not cache only by filename. A nested override or changed `extends` source would be missed.

## Cross-language conformance boundary

The vectors in `conformance/vectors.json` are language-neutral. `integrations/typescript/generated/conformance-verifier.js` independently checks core merge, selection, compact rendering, RFC 8785 JCS, and SHA-256 behavior:

```bash
node integrations/typescript/generated/conformance-verifier.js \
  conformance/vectors.json
```

This gives an interoperability check for the deterministic core. It is not a second full implementation of YAML parsing, filesystem discovery, security budgets, adapters, or the runtime API.

## Model behavior is not deterministic

The contract makes expected behavior explicit; it does not guarantee exact compliance. Stronger consistency comes from combining:

- concrete contrasts and examples;
- compact, non-conflicting instructions;
- model selection appropriate to the task;
- deterministic lint checks;
- model-based evals;
- regression tests against representative prompts;
- optional fine-tuning or preference optimization for high-volume cases.
