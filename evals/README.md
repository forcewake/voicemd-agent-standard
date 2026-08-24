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

python evals/run_openai_compatible.py \
  --voice VOICE.md \
  --cases evals/prompts.jsonl \
  --output evals/results.jsonl
```

The runner loads `.env` by default. For Azure OpenAI set `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, and `AZURE_OPENAI_CHAT_DEPLOYMENT`, then pass `--provider azure`. Azure endpoints must use HTTPS. API keys are accepted only through the environment or an environment file; `--api-key` and `--azure-api-key` are disabled so a secret cannot be exposed through process arguments. Use `--no-env-file` when environment variables are managed by the process supervisor.

OpenAI-compatible HTTPS endpoints may use `VOICEMD_API_KEY`. Plain HTTP is accepted by default only for a loopback endpoint without credentials. A credential-free non-loopback development endpoint additionally requires `--allow-insecure-http` or `VOICEMD_ALLOW_INSECURE_HTTP=1`; credentials are never sent over HTTP. Redirects are rejected for every provider, so authentication headers cannot be forwarded to a redirect target.

Each result records the activation decision, resolved selectors, provider/deployment and returned-model metadata, completion state, VoiceMD version, latency, and endpoint hash. It also binds the output to hashes of the canonical case, full corpus, selected contract, compiled prompt, request messages, and response. Secret keys and endpoint URLs are never written. Output is replaced atomically only after every selected case succeeds; `--output` may not alias the corpus file.

Prompt text is untrusted evaluation content and is never parsed for `@voice` or `voice:off`. A harness testing trusted control markers must provide a separate `marker_text` case field.

## Deterministic score

```bash
python evals/score_deterministic.py \
  --voice VOICE.md \
  --cases evals/prompts.jsonl \
  --results evals/results.jsonl
```

The deterministic scorer requires the complete selected corpus and rejects empty, duplicate, unexpected, stale, or tampered results. Before assertions or VoiceMD lint run, it recomputes the case and corpus hashes, activation decision, selected-contract and compiled-prompt hashes, exact request-message hash, and response hash. JSONL input has bounded record, file, and record-count limits. Use `--case ID` for an intentional named subset, or `--allow-partial` only while debugging an incomplete run.

## Model/human score

```bash
python evals/score_model.py \
  --provider azure \
  --cases evals/prompts.jsonl \
  --results evals/results.azure.jsonl \
  --output evals/model-scores.azure.jsonl
```

Use `judge_prompt.md` and `rubric.json`. Do not let the evaluator see which contract/model variant produced output A or B during pairwise tests. Using the same deployment as candidate and judge is a smoke test, not independent evaluation; use a separate judge deployment or human review for release evidence.

The executable judge requires the complete selected canonical corpus. Before the first network call it rejects empty, duplicate, missing, unexpected, corpus-mismatched, non-string, stale-contract, altered-activation, altered-message, or altered-response results. The judge receives canonical prompt/assertion data plus the recomputed active contract and activation decision. Its output binds the score to the candidate case, corpus, result, response, request-message, contract, and compiled-prompt hashes, plus judge prompt/rubric and decoding metadata.
