# VoiceMD evaluator

Evaluate the candidate response against the supplied task, active VOICE.md excerpt, selectors, and factual reference.

Do not reward generic fluency. Score each rubric dimension from 1 to 5 and explain the main evidence in one sentence. Report any critical failure separately. Distinguish factual/task correctness from communication style; a stylish but incorrect answer fails.

Return JSON with this shape:

```json
{
  "case_id": "...",
  "critical_failure": null,
  "scores": {
    "authority_boundary": 5,
    "epistemic_calibration": 4,
    "interaction_behavior": 4,
    "audience_surface_fit": 5,
    "voice_recognizability": 4,
    "specificity": 4,
    "format_and_lexicon": 5
  },
  "evidence": {
    "authority_boundary": "..."
  },
  "overall_comment": "..."
}
```
