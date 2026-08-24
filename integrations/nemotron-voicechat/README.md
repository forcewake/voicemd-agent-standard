# NVIDIA NemotronLabs VoiceChat

```bash
python -m pip install -e '../..[nemotron]'

python session_update.py \
  --url ws://localhost:9000/v1/realtime \
  --voice ../../VOICE.md \
  --base-instructions-file ../../examples/application/base-agent-instructions.txt \
  --profile nemotron_voicechat \
  --timeout-seconds 30
```

The base file is required, must be ASCII, and owns safety, task, tool, data-access, and output requirements. The client places it before a labeled lower-priority VoiceMD fragment and enforces a 5000-character budget across the complete `session.instructions` value.

The client bounds connection, send, receive, and close operations; rejects server
`error` events; and verifies that `session.updated` echoes the requested instructions
and audio configuration. It does not implement audio capture/playback; use NVIDIA's
current reference clients for the audio loop.

See `../../docs/NEMOTRON_VOICECHAT.md` for current constraints and source links.
