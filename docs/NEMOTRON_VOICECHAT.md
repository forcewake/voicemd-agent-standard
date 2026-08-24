# NVIDIA NemotronLabs VoiceChat 11B integration

Compatibility basis checked on 2026-08-24 against the NVIDIA Hugging Face model card and the `NVIDIA-NeMo/Speech` `nemotron-labs-voicechat` branch.

## Relevant runtime properties

The released NVIDIA NemotronLabs VoiceChat model is an 11B real-time, full-duplex speech model. The published implementation exposes a bidirectional WebSocket interface compatible with the OpenAI Realtime protocol. A client sends `session.update` after connecting and can set `session.instructions` to an arbitrary string for the session's first inference.

The current NVIDIA documentation requires system prompts and API/tool responses to be ASCII-only. The released checkpoint uses one fixed acoustic voice and does not support voice cloning. The published hardware guidance calls for an NVIDIA GPU with at least 80 GB of memory.

These facts affect the adapter:

- VoiceMD controls conversational behavior, not acoustic voice identity.
- Use an English spoken profile rather than a long multilingual contract.
- Compile with ASCII normalization.
- Keep tool results concise and TTS-friendly without changing facts.
- Treat the model's fixed voice as independent from `VOICE.md` communication behavior.

Official sources:

- https://huggingface.co/nvidia/NVIDIA-NemotronLabs-VoiceChat-11B
- https://github.com/NVIDIA-NeMo/Speech/tree/nemotron-labs-voicechat
- https://github.com/NVIDIA-NeMo/Speech/blob/nemotron-labs-voicechat/voicechat_realtime_instructions/api-reference.md

## Compile the profile

The full template includes `nemotron_voicechat`:

```bash
voicemd compile \
  --path VOICE.md \
  --profile nemotron_voicechat \
  --format nemotron-ascii \
  --compact \
  --max-chars 5000 \
  --output .voice/nemotron-voice.txt
```

This output is only the lower-priority communication fragment. Do not send it as the sole `session.instructions` value. The reference adapter prepends required application-owned base instructions and budgets the complete combined value.

`--format nemotron-ascii`:

- normalizes Unicode punctuation;
- transliterates common Cyrillic characters;
- removes remaining non-ASCII code points;
- verifies the result is ASCII.

Transliteration is lossy. The preferred production approach is to author the active spoken profile directly in English/ASCII.

## Send `session.update`

The reference example under `integrations/nemotron-voicechat/session_update.py` connects to:

```text
ws://localhost:9000/v1/realtime
```

and sends:

```json
{
  "type": "session.update",
  "event_id": "...",
  "session": {
    "audio": {
      "input": {"format": {"type": "audio/pcm", "rate": 24000}},
      "output": {"format": {"type": "audio/pcm", "rate": 24000}}
    },
    "instructions": "<ASCII application authority, then lower-priority VoiceMD fragment>",
    "tools": []
  }
}
```

The example requires `--base-instructions-file`; the file must be ASCII and contain application-owned safety, task, tool, data-access, and output requirements. It only configures and verifies the session; it does not implement microphone capture or playback. NVIDIA's client examples should remain the source of truth for audio streaming.

## Tool responses

A tool response must remain factually exact but can be rendered into speakable ASCII:

Bad:

```json
{"temp":21.5,"unit":"°C","status":"partly_cloudy"}
```

Better payload sent to the speech model:

```text
The temperature is 21.5 degrees Celsius. Conditions are partly cloudy.
```

Keep the original structured result in application state for audit. The spoken rendering is a presentation adapter, not the source of truth.

## Full-duplex behavior fields

A Nemotron profile should specify:

```yaml
speech:
  turn_length: short
  sentence_length: short
  tts_friendly: true
  ascii_only: true
  interruptions: Let the user finish unless safety requires immediate intervention.
interaction:
  clarification: Ask one focused question only when the missing fact blocks the answer.
response:
  max_words: 75
  max_sentences: 5
```

The standard does not currently define low-level duplex timing, VAD parameters, audio codecs, or barge-in thresholds. Those remain runtime configuration.

## Hardware caveat

The included adapter does not make the model run on smaller hardware. It only supplies session instructions. Follow NVIDIA's current deployment requirements and test the exact container/checkpoint combination.
