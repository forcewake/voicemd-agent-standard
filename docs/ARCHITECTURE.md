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
               profile/audience/surface/tone
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

VoiceMD intentionally separates six concerns:

1. **Authorship:** humans define recognizable communication behavior in Markdown and optional YAML.
2. **Resolution:** discovery and inheritance create one deterministic active contract.
3. **Selection:** runtime context selects audience, surface, tone, and profile.
4. **Compilation:** the selected contract becomes provider-neutral instructions or JSON.
5. **Delivery:** a harness reads the skill/file, or an application injects the compiled prompt.
6. **Verification:** lint rules and eval cases check observable output.

This split prevents a harness adapter from becoming the standard. Codex, Claude Code, Gemini CLI, an internal orchestrator, and a local vLLM server can use different delivery mechanisms while sharing one contract.

## Why Agent Skills are the default harness adapter

A coding agent does not need a long communication contract while editing source, generating tests, or producing tool payloads. An Agent Skill exposes only a name and trigger description until the task requires human-facing output. This is progressive disclosure: the full instructions are loaded on demand.

A small bootstrap in the harness-native instruction file improves trigger reliability without copying the entire contract into every task. The bootstrap establishes activation and authority boundaries; the skill handles discovery and application.

## Runtime contract pipeline

A production application should make the selection explicit:

```text
request context
  surface=spoken
  audience=customer
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
  "compiler": "voicemd/0.1.0a1",
  "compiled_sha256": "..."
}
```

## Failure strategy

Applications should choose one of three explicit policies:

- **fail closed:** reject startup/request when the pinned contract is invalid;
- **last known good:** continue with a previously validated compiled artifact;
- **voice optional:** omit voice adaptation and continue with base system behavior.

Silent fallback to a different contract is not recommended.

## Performance and caching

Resolution and compilation are deterministic and can be cached by:

- source file modification times plus selectors;
- source content hashes plus compiler version;
- contract semantic version plus deployment version.

Do not cache only by filename. A nested override or changed `extends` source would be missed.

## Model behavior is not deterministic

The contract makes expected behavior explicit; it does not guarantee exact compliance. Stronger consistency comes from combining:

- concrete contrasts and examples;
- compact, non-conflicting instructions;
- model selection appropriate to the task;
- deterministic lint checks;
- model-based evals;
- regression tests against representative prompts;
- optional fine-tuning or preference optimization for high-volume cases.
