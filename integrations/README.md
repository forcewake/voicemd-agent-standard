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
| `voicemd.azure_voice` | optional Azure audio, Realtime, transcription, evidence, and gallery adapter shipped in the Python package |
| `mcp/` | optional MCP resource/tool adapter |
| `docker/` | local sidecar image and Compose example |
| `kubernetes/` | sidecar deployment example |

The core contract is provider-neutral. These adapters deliver a compiled contract; they do not change the authority model.

The Azure adapter is installed with `pip install 'voicemd[azure-voice]'` and
exposed as `voicemd-azure`. Its contrasting contracts, scenarios, evidence
schema, and end-to-end instructions live under `examples/azure-voice/`.

The TypeScript example includes a package manifest, lockfile, and strict compiler configuration:

```bash
npm --prefix integrations/typescript ci
npm --prefix integrations/typescript run check
```

The .NET example is a buildable .NET 8 project:

```bash
dotnet build integrations/dotnet/VoiceMd.Example.csproj
```
