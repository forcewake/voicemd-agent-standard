# OpenAI-compatible endpoints

The example uses only Python's standard library plus the installed `voicemd` package. It works with servers that implement `/v1/chat/completions`, including many vLLM, SGLang, llama.cpp-server, and local gateway deployments.

```bash
export OPENAI_BASE_URL=http://127.0.0.1:8000/v1
export OPENAI_MODEL=my-model
python chat_completions.py \
  --voice ../../VOICE.md \
  --profile architecture_review \
  "Review this design."
```

The word “compatible” does not guarantee identical role precedence across servers. Test whether the model/template preserves multiple system messages. If not, concatenate base instructions and compiled voice into one system message with the authority boundary first.
