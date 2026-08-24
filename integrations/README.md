# Integration pack

| Directory | Purpose |
|---|---|
| `python/` | direct library use and activation middleware |
| `http/` | provider-neutral sidecar and OpenAPI |
| `typescript/` | dependency-free HTTP client |
| `dotnet/` | .NET HTTP client |
| `openai-compatible/` | generic chat-completions injection |
| `transformers/` | Hugging Face chat-template example |
| `vllm/` | local OpenAI-compatible serving notes |
| `ollama/` | fixed-profile Modelfile wrapper |
| `llama.cpp/` | system-prompt integration notes |
| `nemotron-voicechat/` | ASCII profile and Realtime `session.update` example |
| `mcp/` | optional MCP resource/tool adapter |
| `docker/` | local sidecar image and Compose example |
| `kubernetes/` | sidecar deployment example |

The core contract is provider-neutral. These adapters deliver a compiled contract; they do not change the authority model.
