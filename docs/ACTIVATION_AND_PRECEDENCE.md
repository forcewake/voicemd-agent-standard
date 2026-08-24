# Activation and precedence

## Activation decision

A runtime should make one explicit decision before loading or applying the contract:

```text
Is the output primarily for a human to read or hear?
  no  -> do not apply VOICE.md
  yes -> does a stronger requirement demand exact/machine output?
           yes -> preserve the requirement; apply only where compatible
           no  -> select surface/audience/profile and apply
```

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
  "exact_output": false
}
```

This is more reliable than asking the model to infer hidden application state.
