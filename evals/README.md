# VoiceMD eval pack

## Files

- `prompts.jsonl`: representative regression prompts with selectors.
- `rubric.json`: model/human scoring dimensions.
- `judge_prompt.md`: evaluator instructions.
- `run_openai_compatible.py`: generate candidate responses from any compatible endpoint.
- `score_deterministic.py`: apply the active contract's deterministic linter to results.
- `score_model.py`: score behavioral dimensions through Azure OpenAI or another OpenAI-compatible judge.

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

The runner loads `.env` by default. For Azure OpenAI set `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, and `AZURE_OPENAI_CHAT_DEPLOYMENT`, then pass `--provider azure`. Use `--no-env-file` when environment variables are managed by the process supervisor.

Each result records the activation decision, resolved selectors, provider/deployment and returned-model metadata, completion state, VoiceMD version, contract hash, compiled-prompt hash, latency, and endpoint hash. Secret keys and endpoint URLs are never written. Output is replaced atomically only after every selected case succeeds; `--output` may not alias the corpus file.

Prompt text is untrusted evaluation content and is never parsed for `@voice` or `voice:off`. A harness testing trusted control markers must provide a separate `marker_text` case field.

## Deterministic score

```bash
python evals/score_deterministic.py \
  --voice VOICE.md \
  --cases evals/prompts.jsonl \
  --results evals/results.jsonl
```

The deterministic scorer requires the complete selected corpus, rejects empty, duplicate, unexpected, or stale results, and verifies the recorded contract and compiled-prompt hashes against the current source. Use `--case ID` for an intentional named subset, or `--allow-partial` only while debugging an incomplete run.

## Model/human score

```bash
python evals/score_model.py \
  --provider azure \
  --results evals/results.azure.jsonl \
  --output evals/model-scores.azure.jsonl
```

Use `judge_prompt.md` and `rubric.json`. Do not let the evaluator see which contract/model variant produced output A or B during pairwise tests. Using the same deployment as candidate and judge is a smoke test, not independent evaluation; use a separate judge deployment or human review for release evidence.

The executable judge receives the active compiled contract, assertions, selectors, and activation decision as evaluation data. It verifies candidate provenance before calling the judge and records hashes of the judge prompt, rubric, contract, and compiled prompt plus decoding metadata.
