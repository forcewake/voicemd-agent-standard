# Ollama

Create a fixed-profile wrapper:

```bash
voicemd compile \
  --path ../../VOICE.md \
  --profile default \
  --compact \
  --max-chars 3500 \
  --output VOICE.compiled.txt

BASE_INSTRUCTIONS_FILE=../../examples/application/base-agent-instructions.txt \
  ./build.sh my-agent llama3.1:8b
ollama run my-agent
```

The base instructions are application-owned authority for safety, task, tool, data-access, and output requirements. `build.sh` refuses a missing or empty base file, places it first, and labels VoiceMD as lower-priority communication guidance. Customize the example base file before production use.

This bakes one compiled profile into the model wrapper. For dynamic audience/surface selection, send both the application authority and selected VoiceMD fragment per request instead.
