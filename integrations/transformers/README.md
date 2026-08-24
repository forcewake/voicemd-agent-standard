# Hugging Face Transformers

```bash
python chat_template.py \
  --model /models/my-instruct-model \
  --voice ../../VOICE.md \
  --base-instructions-file ../../examples/application/base-agent-instructions.txt \
  --profile default \
  --prompt "Explain the trade-off."
```

The base file is application-owned authority for safety, task, tool, data-access, and output requirements. The adapter places it first and labels the compiled VoiceMD text as lower-priority communication guidance; VoiceMD is never the sole system instruction.

The model's chat template is authoritative. Some models do not support a system role or handle it weakly. Follow the model card and test the exact tokenizer/template rather than inventing a generic delimiter format. Application code must still enforce permissions and tool access outside the model.
