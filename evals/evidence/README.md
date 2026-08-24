# Evaluation evidence

This directory contains checked-in, secret-free raw candidate results used as
release evidence. It is not a claim of independent model evaluation or vendor
certification.

## 0.1.0a2 Azure smoke corpus

`0.1.0a2-azure-results.jsonl` was generated on 2026-08-24 with the complete
14-case `evals/prompts.jsonl` corpus through the hardened Azure transport:

```bash
PYTHONPATH=src python evals/run_openai_compatible.py \
  --env-file .env \
  --provider azure \
  --output /tmp/voicemd-azure-full.jsonl \
  --timeout 60

PYTHONPATH=src python evals/score_deterministic.py \
  --voice VOICE.md \
  --cases evals/prompts.jsonl \
  --results /tmp/voicemd-azure-full.jsonl
```

Observed result: 14/14 cases passed the deterministic scorer. All provider
requests finished with `stop`. The returned provider model identifier was
`gpt-5.6-terra-2026-07-09`; this records what the endpoint reported, not a
portable capability claim.

The JSONL is immutable historical `0.1.0a2` evidence; it is not relabeled as an
`0.1.0a3` run. It records prompts and responses plus content hashes, selectors,
activation decisions, model metadata, token usage, and latency. The records contain an
endpoint hash but no endpoint URL, API key, authorization header, or `.env`
value. The general scorer fails closed on package-version, corpus, contract, or
request drift; regression tests validate this record under its recorded a2
version boundary.

No model-judge score is asserted here. Candidate and judge independence,
human review, repeated trials, and statistical quality evaluation remain
separate release gates.
