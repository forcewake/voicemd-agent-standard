# llama.cpp

Compile a bounded prompt:

```bash
voicemd compile --compact --max-chars 3000 --output /tmp/voice.txt
```

Use the current llama.cpp CLI/server option that corresponds to the model's system message or chat-template input. Options differ between releases; check the local binary's `--help` and the model's chat-template metadata.

Do not prepend the contract to raw prompt text without the correct model template. A malformed chat template can have a larger effect than the voice contract itself.
