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

Command-line `--profile`, `--audience`, `--surface`, and `--tone` override case-local selectors. Without them, each JSONL case selects its own context.

### Azure OpenAI

The runner can load an ignored `.env` file and use an Azure deployment without exposing the key in arguments:

```dotenv
AZURE_OPENAI_ENDPOINT=https://RESOURCE.openai.azure.com
AZURE_OPENAI_API_KEY=replace-locally
AZURE_OPENAI_CHAT_DEPLOYMENT=chat-deployment
AZURE_OPENAI_API_VERSION=2024-10-21
```

```bash
python evals/run_openai_compatible.py \
  --provider azure \
  --cases evals/prompts.jsonl \
  --output evals/results.azure.jsonl
```

The API key is used only in the request header and is never written to results. Results record provider, deployment/model, API version, decoding settings, VoiceMD version, contract and prompt hashes, response metadata, and an endpoint hash.

The runner also records the provider-returned model identifier, finish reason, content-filter metadata, and prompt-filter metadata. Non-text, truncated, tool-call, or filtered completions fail the run instead of being scored as ordinary answers. The output file is updated atomically after the complete selected run.

Then run deterministic checks:

```bash
python evals/score_deterministic.py \
  --voice VOICE.md \
  --cases evals/prompts.jsonl \
  --results evals/results.jsonl
```

This gate is non-vacuous: by default it requires every corpus ID and rejects empty, duplicate, unexpected, corpus-mismatched, or provenance-mismatched results. `--case ID` selects an intentional subset. `--allow-partial` is a debugging escape hatch, not release evidence.

### Pairwise evaluation

For subtle voice quality, compare baseline and candidate outputs without revealing which contract version produced each. Ask an evaluator to choose based on a fixed rubric, not general preference.

`evals/score_model.py` executes the bundled judge prompt and rubric through Azure OpenAI or another OpenAI-compatible endpoint, supplies the active compiled VoiceMD contract, validates candidate provenance and the exact returned schema, calculates the weighted score, and fails when the judge reports a critical failure. Its output records judge configuration and prompt/rubric hashes. A same-model judge is useful for plumbing smoke tests but is not independent evidence.

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

The bundled corpus includes each category as a regression fixture. It is still a starter corpus, not evidence of cross-model conformance until results are generated and reviewed across multiple deployments.

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
