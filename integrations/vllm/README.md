# vLLM

Serve the chosen instruction model using its documented chat template. VoiceMD remains client-side:

```bash
voicemd compile --compact --max-chars 3500 --output /tmp/voice-system.txt
```

Then send the file contents as a system message through an OpenAI-compatible client. See `../openai-compatible/chat_completions.py`.

For multi-tenant serving, do not bake one tenant's voice into server-global model configuration. Select and inject the compiled contract per request through an allowlisted profile registry.
