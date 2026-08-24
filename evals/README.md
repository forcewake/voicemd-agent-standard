# VoiceMD eval pack

## Files

- `prompts.jsonl`: representative regression prompts with selectors.
- `rubric.json`: model/human scoring dimensions.
- `judge_prompt.md`: evaluator instructions.
- `run_openai_compatible.py`: generate candidate responses from any compatible endpoint.
- `score_deterministic.py`: apply the active contract's deterministic linter to results.

## Generate results

```bash
export VOICEMD_BASE_URL=http://127.0.0.1:8000/v1
export VOICEMD_MODEL=my-local-model
export VOICEMD_API_KEY=local

python evals/run_openai_compatible.py \
  --voice VOICE.md \
  --cases evals/prompts.jsonl \
  --output evals/results.jsonl
```

## Deterministic score

```bash
python evals/score_deterministic.py \
  --voice VOICE.md \
  --results evals/results.jsonl
```

## Model/human score

Use `judge_prompt.md` and `rubric.json`. Do not let the evaluator see which contract/model variant produced output A or B during pairwise tests.
