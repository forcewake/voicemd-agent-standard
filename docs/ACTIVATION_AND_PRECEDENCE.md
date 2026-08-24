# Activation and precedence

## Activation decision

A runtime should resolve the active profile/audience/surface/tone and then make one explicit decision before applying the contract:

```text
Is voice disabled by the application or is exact output required?
  yes -> do not apply VOICE.md
  no  -> is activation.mode off?
           yes -> do not apply VOICE.md
           no  -> is output_kind excluded or machine-facing?
                    yes -> do not apply VOICE.md
                    no  -> resolve explicit markers, then the activation mode
```

The decision is deterministic:

1. Resolve active selector and profile overrides, including any activation override.
2. Application disablement and exact-output requirements win over every contract setting.
3. `mode: off` cannot be forced on by a marker.
4. Machine-facing kinds and `activation.exclude` win over `activation.include`.
5. An off marker wins if both on and off markers are present.
6. `explicit` requires an explicit runtime flag or on marker.
7. `always` applies to every remaining output kind.
8. `contextual` applies to the standard human-facing kinds plus explicit `include` values.

A contract declaring the same category in `include` and `exclude`, or the same marker in both marker lists, is invalid. The exclusion/off precedence above is defensive runtime behavior for higher-priority machine-output classification and conflicting markers in request text; it is not permission to publish an ambiguous contract.

The Python reference exposes `decide_activation()` and `should_apply_voice()` for this decision. Compilation by itself does not infer application state; applications should decide activation before injecting the compiled contract.

## Default activation matrix

Apply by default:

- chat answers and explanations;
- written messages, emails, documents, and reports;
- summaries intended for humans;
- UI text and notifications;
- spoken dialogue;
- natural-language error explanations.

Skip by default:

- source code and comments when the task is code generation rather than prose authorship;
- patches and diffs;
- SQL and configuration syntax;
- strict JSON/XML/YAML or function arguments;
- tool calls and raw tool results;
- exact quotations;
- raw retrieved passages and evidence;
- binary/encoded output.

Mixed artifacts require scoped application. For example, a report containing a JSON sample may use voice in the surrounding explanation but must not mutate the JSON.

## Translation

For faithful translation, preserve source meaning, tone, and formatting. Do not inject the agent's default personality. Apply a destination voice only when the user requests adaptation, localization, editing, or a destination artifact whose tone is part of the task.

## Explicit markers

Applications and harnesses may support:

```text
@voice             force contextual voice on
voice:on
@no-voice          turn optional voice adaptation off
voice:off
```

These markers do not override safety, platform policy, or a system requirement.

If both an on marker and an off marker occur, the off marker wins. This fail-closed rule prevents quoted or retrieved content from accidentally forcing activation.

Treat text markers as trusted request-control metadata, not as instructions discovered inside the user prompt, retrieved documents, or tool results. Prefer an explicit application metadata flag when trusted and untrusted text are mixed. The reference eval runner never scans prompt text for markers; a test must provide a separate `marker_text` field. The reference matcher requires a complete marker token rather than a substring such as `voice:office`.

## Conflict examples

### Required JSON

User: “Return only JSON matching this schema.”

Result: output valid JSON. Do not add the VOICE.md conclusion, headings, caveats, or conversational wording.

### Incorrect premise

User: “Kafka is mandatory for enterprise systems, so add it.”

Result: the interaction rule may challenge the premise because this remains human-facing analysis. It does not independently authorize a code change if normal approval is required.

### Exact quote

User: “Quote the clause verbatim.”

Result: quote exactly. Do not replace forbidden lexicon inside the quotation. The linter should be applied only to original surrounding prose or support an exact-quote exclusion.

### Tool result

A weather tool returns structured data. Keep the tool payload unchanged. Transform only the final natural-language explanation, and preserve all facts.

### Safety

A VOICE.md says “never refuse.” This is out of scope and ignored. Safety and platform rules win.

## Recommended implementation metadata

Applications should pass an explicit selector object:

```json
{
  "output_kind": "spoken",
  "surface": "spoken",
  "audience": "customer",
  "tone": "neutral",
  "profile": "voicechat",
  "voice_enabled": true,
  "voice_explicit": false,
  "exact_output": false
}
```

This is more reliable than asking the model to infer hidden application state.
