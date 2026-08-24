# Brand-oriented VOICE.md compatibility

## Prior art

Independent projects already use `VOICE.md` or `voice.md` for brand and copy voice. One visible example is Efeonce's alpha `voice.md` project. VoiceMD acknowledges that prior art and does not claim the filename is novel.

This draft extends the use case from brand copy into agent communication and interaction. The goals overlap but are not identical.

## Shared concepts

Common fields can map naturally:

```text
brand personality       -> identity / traits
register                -> language / response
lexicon                 -> lexicon
audiences               -> audiences
surfaces                -> surfaces
formatting              -> formatting
examples                -> examples or Markdown body
```

## Agent-specific additions

VoiceMD adds or formalizes:

- communication-only authority boundary;
- contextual activation/exclusion;
- epistemic behavior;
- disagreement and clarification behavior;
- confidence-pressure behavior;
- hierarchical project discovery;
- profile selection;
- spoken/TTS runtime constraints;
- deterministic merge semantics;
- lint rules and eval cases;
- Agent Skill and application compilation paths.

## Migration approach

Do not rewrite an existing brand file immediately. Compose it:

```yaml
extends:
  - ./brand/VOICE.md
voice_spec: "0.1"
kind: VoiceContract
name: "Brand voice plus agent behavior"
authority:
  may_control: [tone, register, vocabulary, structure, interaction]
  must_not_control: [facts, safety, permissions, tools, schemas]
epistemics:
  uncertainty: Name the missing variable and its consequence.
interaction:
  disagreement: Correct false premises without imitating hostility.
```

If the existing frontmatter uses fields not defined by VoiceMD, they remain extension data because the schema permits unknown properties. The reference compiler only renders known core sections plus the Markdown body; custom fields require a plugin or explicit prose.

## Namespace collision

Because multiple conventions use the same filename, tooling must inspect `voice_spec` and `kind` rather than assuming every `VOICE.md` follows this specification. Plain L0 documents are intentionally ambiguous and should be treated as unstructured guidance.
