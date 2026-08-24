# NVIDIA NemotronLabs VoiceChat

```bash
python -m pip install -e '../..[nemotron]'

python session_update.py \
  --url ws://localhost:9000/v1/realtime \
  --voice ../../VOICE.md \
  --profile nemotron_voicechat
```

The client sends the compiled ASCII contract through `session.update.session.instructions`. It does not implement audio capture/playback; use NVIDIA's current reference clients for the audio loop.

See `../../docs/NEMOTRON_VOICECHAT.md` for current constraints and source links.
