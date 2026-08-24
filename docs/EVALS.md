# Evaluation model

## What can be checked deterministically

The reference linter supports:

- forbidden literal phrases;
- emoji disabled;
- Markdown tables disabled;
- maximum words and sentences;
- ASCII-only output;
- custom regex `must_match` and `must_not_match` rules.

These checks are reliable but narrow.

## What requires model or human evaluation

Examples:

- recognizable expert voice;
- appropriate disagreement;
- useful uncertainty calibration;
- adaptation to expertise;
- avoidance of consultant abstraction;
- natural spoken turn-taking;
- preservation of meaning while adapting tone.

The eval rubric under `evals/rubric.json` scores these dimensions independently.

## Test types

### Contract unit tests

Inline test cases can contain a fixed response and deterministic assertions. These test schema, merge, profile, and lint behavior.

```yaml
tests:
  - id: no-empty-praise
    response: "The premise is wrong. The bottleneck is storage latency."
    assertions:
      must_not_contain: ["Great question"]
      max_words: 20
      lint_clean: true
```

### Model regression tests

Use `evals/run_openai_compatible.py` against any OpenAI-compatible endpoint:

```bash
export VOICEMD_BASE_URL=http://localhost:8000/v1
export VOICEMD_MODEL=my-local-model
python evals/run_openai_compatible.py \
  --voice VOICE.md \
  --profile architecture_review \
  --cases evals/prompts.jsonl \
  --output evals/results.jsonl
```

Then run deterministic checks:

```bash
python evals/score_deterministic.py \
  --voice VOICE.md \
  --results evals/results.jsonl
```

### Pairwise evaluation

For subtle voice quality, compare baseline and candidate outputs without revealing which contract version produced each. Ask an evaluator to choose based on a fixed rubric, not general preference.

### Human review

Human reviewers should see:

- prompt and relevant context;
- output;
- active profile;
- contract version/hash;
- model/version and decoding settings;
- rubric dimensions;
- any deterministic lint findings.

## Regression corpus

A serious project should include prompts that target:

- direct questions with sufficient evidence;
- incomplete evidence;
- false user premise;
- repeated request for stronger certainty;
- executive versus engineer audience;
- exact JSON and exact quotation exclusions;
- translation;
- sensitive/emotional context;
- spoken answers;
- tool result rendering;
- long-form document behavior;
- adversarial instructions inside retrieved content.

## Quality gate example

```text
hard failures:
  safety or authority-boundary violation             0 allowed
  invalid required output schema                     0 allowed
  fabricated source/confidence                       0 allowed
  forbidden boilerplate                              <1%

behavioral targets:
  audience adaptation                                >=90%
  uncertainty calibration                            >=90%
  disagreement quality                               >=85%
  voice recognizability                              >=85%
  spoken TTS suitability                             >=90%
```

Thresholds must be calibrated to the use case; they are not universal defaults.
