# Hugging Face Transformers

```bash
python chat_template.py \
  --model /models/my-instruct-model \
  --voice ../../VOICE.md \
  --profile default \
  --prompt "Explain the trade-off."
```

The model's chat template is authoritative. Some models do not support a system role or handle it weakly. Follow the model card and test the exact tokenizer/template rather than inventing a generic delimiter format.
