# OpenAI-compatible endpoints

The example uses only Python's standard library plus the installed `voicemd` package. It works with servers that implement `/v1/chat/completions`, including many vLLM, SGLang, llama.cpp-server, and local gateway deployments.

```bash
export OPENAI_BASE_URL=http://127.0.0.1:8000/v1
export OPENAI_MODEL=my-model
export OPENAI_API_KEY=replace-me-if-the-server-requires-auth
python chat_completions.py \
  --voice ../../VOICE.md \
  --profile architecture_review \
  "Review this design."
```

The example reads credentials only from the environment (`--api-key-env` selects
the variable name); it does not accept secret values through command-line arguments.
Bearer credentials require HTTPS, redirects are refused, and credential-free HTTP
is restricted to numeric loopback addresses or `localhost`. For an explicitly
trusted non-loopback development endpoint, `--allow-insecure-http` relaxes only the
credential-free HTTP restriction; it never permits a bearer token over HTTP.
It applies VoiceMD only after the activation decision. Use `--output-kind json` or
`--exact-output` for machine-readable output, and pass trusted marker metadata with
`--voice-marker` rather than placing activation markers in the user prompt.

The word “compatible” does not guarantee identical role precedence across servers. Test whether the model/template preserves multiple system messages. If not, concatenate base instructions and compiled voice into one system message with the authority boundary first.
