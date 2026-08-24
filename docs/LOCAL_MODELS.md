# Local and small models

## Main constraint

A smaller model has less instruction-following capacity and a smaller effective context budget. A full enterprise contract can make it worse by creating conflicting or low-salience rules.

Use compact compilation:

```bash
voicemd compile \
  --profile default \
  --compact \
  --max-chars 3500 \
  --output .voice/system.txt
```

## Authoring rules for small models

- Use direct imperatives rather than abstract traits.
- Keep fewer than ten high-value rules active per profile.
- Use one good/bad contrast for difficult behavior.
- Remove redundant synonyms.
- Make the activation boundary explicit.
- Put the highest-value rules first.
- Avoid deeply nested variants.
- Test the exact quantized model and chat template used in production.

## Hugging Face Transformers

`integrations/transformers/chat_template.py` compiles the contract and inserts it as a system message before calling `tokenizer.apply_chat_template`.

Not every tokenizer supports a system role. When it does not, use the model's documented template and place the voice instructions in the designated instruction section rather than inventing a format.

## vLLM and other OpenAI-compatible servers

Pass the compiled contract as a system message through the client. The server does not need to know about VOICE.md:

```bash
VOICE_PROMPT="$(voicemd compile --compact --max-chars 3500)"
```

See `integrations/openai-compatible/`.

## Ollama

Build a model wrapper with the compiled prompt:

```bash
voicemd compile --compact --max-chars 3500 --output integrations/ollama/VOICE.compiled.txt
cd integrations/ollama
./build.sh my-voice-model base-model-name
```

The generated wrapper is convenient for a fixed voice. For dynamic audience/surface selection, inject the system prompt per request instead of baking one profile into a model.

## llama.cpp

Use the model's supported chat template. Pass the compiled text through the CLI/server system-prompt mechanism when available. Do not concatenate it into the user message unless the template has no system/instruction channel and you have tested the behavior.

## Quantization and instruction loss

Aggressive quantization may reduce style and instruction adherence before factual capability visibly collapses. Evaluate:

- activation boundary;
- forbidden boilerplate;
- uncertainty calibration;
- audience adaptation;
- length and formatting constraints;
- tool-call separation.

Do not assume a contract validated on FP16 behaves identically on a 4-bit quantization.

## Context budgeting

Allocate the prompt budget explicitly:

```text
base identity and safety        fixed
operational/task instructions   fixed or task-specific
tool schemas                    variable
retrieved context               variable
VOICE.md                        bounded, preferably 2-5k characters for small models
conversation history            variable
```

Voice instructions should not crowd out the evidence required to answer correctly.
