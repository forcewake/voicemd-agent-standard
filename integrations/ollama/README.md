# Ollama

Create a fixed-profile wrapper:

```bash
voicemd compile \
  --path ../../VOICE.md \
  --profile default \
  --compact \
  --max-chars 3500 \
  --output VOICE.compiled.txt

./build.sh my-agent llama3.1:8b
ollama run my-agent
```

This bakes one compiled profile into the model wrapper. For dynamic audience/surface selection, send the selected system prompt per request instead.
