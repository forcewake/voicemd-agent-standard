# VoiceMD Azure Voice Proof Lab

This example exercises several Azure OpenAI audio lanes against contrasting
`VOICE.md` communication contracts and writes a reviewable evidence bundle for
each run. It is a proof harness, not a production voice-agent application or a
vendor benchmark.

The included contracts deliberately produce different spoken behavior:

- `incident_commander`: concise operational status, uncertainty, and next action;
- `calm_support`: calm customer-facing explanation without false reassurance;
- `executive_brief`: decision-relevant impact and risk with aggressive compression.

The CLI keeps application authority separate from communication behavior. A
compiled `VOICE.md` may shape human-facing wording and delivery, but it cannot
change facts, permissions, safety, tools, raw transcripts, or required schemas.

## Install

From the repository root, install VoiceMD and the WebSocket dependency used by
the realtime and transcription lanes:

```bash
pip install -e '.[azure-voice]'
```

Confirm that the command is available:

```bash
voicemd-azure --help
```

## Azure configuration

The CLI currently authenticates with an Azure OpenAI API key. Do not put a key
in source code, a command argument, a committed file, or captured terminal
output. The hidden `--api-key` argument is deliberately rejected.

The minimum shared configuration can live in the repository's ignored `.env`
file, which the CLI loads by default. Keep the file mode at `0600`:

```dotenv
AZURE_OPENAI_ENDPOINT=https://YOUR-RESOURCE.openai.azure.com
AZURE_OPENAI_API_KEY=YOUR-KEY
```

```bash
chmod 600 .env
```

Set deployment names when your Azure deployment names differ from the defaults:

```dotenv
AZURE_OPENAI_AUDIO_DEPLOYMENT=gpt-audio-1.5
AZURE_OPENAI_REALTIME_DEPLOYMENT=gpt-realtime-2.1
AZURE_OPENAI_REALTIME_MINI_DEPLOYMENT=gpt-realtime-2.1-mini
AZURE_OPENAI_TRANSCRIBE_DEPLOYMENT=gpt-live-transcribe
```

The deployment defaults are the four values shown above. An explicit
`--deployment` takes precedence over the corresponding environment variable,
which takes precedence over the default.

If the lanes live in different Azure resources, use lane-specific connection
overrides:

| Lane | Endpoint override | API-key override |
| --- | --- | --- |
| Audio completion | `AZURE_OPENAI_AUDIO_ENDPOINT` | `AZURE_OPENAI_AUDIO_API_KEY` |
| Realtime, including `--mini` | `AZURE_OPENAI_REALTIME_ENDPOINT` | `AZURE_OPENAI_REALTIME_API_KEY` |
| Live transcription | `AZURE_OPENAI_TRANSCRIBE_ENDPOINT` | `AZURE_OPENAI_TRANSCRIBE_API_KEY` |

Lane-specific values take precedence over `AZURE_OPENAI_ENDPOINT` and
`AZURE_OPENAI_API_KEY`. There is no separate mini connection: `realtime
--mini` uses the Realtime endpoint and key with
`AZURE_OPENAI_REALTIME_MINI_DEPLOYMENT`.

`voicemd-azure` also supports a global `--env-file` option before the
subcommand, for example:

```bash
voicemd-azure --env-file /secure/local/path/azure-voice.env doctor
```

Exported variables are not overwritten by values from that file. Keep any
environment file outside version control.

## Prepare audio input

The `transcribe` and `showcase` commands require an uncompressed PCM16 WAV at
24 kHz with one channel. Convert common source formats with FFmpeg:

```bash
ffmpeg -i input.m4a -vn -c:a pcm_s16le -ar 24000 -ac 1 input-24k-mono.wav
```

Optionally inspect the result:

```bash
ffprobe -v error \
  -show_entries stream=codec_name,sample_rate,channels \
  -of default=noprint_wrappers=1 \
  input-24k-mono.wav
```

The expected values are `pcm_s16le`, `24000`, and `1`. Transcription input is
limited by the harness to 20 MiB and 300 seconds. The `audio` command accepts
WAV or MP3 input up to 20 MiB and does not impose the 24 kHz mono requirement.

## Commands

In a source checkout, paid runs use fresh directories under
`examples/azure-voice/artifacts/`. An installed wheel uses the writable
`.voice/azure-voice-artifacts/` directory under the current working directory.
`--output-root` overrides either default.

### `doctor`

Check local configuration, installed dependencies, deployment-name resolution,
and the bundled contracts:

```bash
voicemd-azure doctor
```

`doctor` makes no Azure request. A `ready: true` result means the required
variables are present, `websockets` is installed, and the local contracts
compile. It does not prove that a deployment exists, has quota, accepts the
requested API, or can complete a call.

### `audio`

Run an audio completion through the `gpt-audio-1.5` deployment and save the
returned WAV and transcript:

```bash
voicemd-azure audio \
  --scenario degraded-service-en \
  --voice examples/azure-voice/contracts/calm_support/VOICE.md
```

Send an audio input together with a human-facing request:

```bash
voicemd-azure audio \
  --input-audio input.mp3 \
  --prompt 'Explain the caller request and state only supported next actions.' \
  --voice examples/azure-voice/contracts/incident_commander/VOICE.md
```

This lane uses Azure OpenAI Chat Completions with text and audio output. It is
not a low-latency duplex session.

### `realtime`

Run one fresh Realtime WebSocket text-to-audio turn with the full deployment:

```bash
voicemd-azure realtime \
  --scenario certainty-pressure-en \
  --voice examples/azure-voice/contracts/incident_commander/VOICE.md
```

Run the same scenario through the mini deployment:

```bash
voicemd-azure realtime --mini \
  --scenario certainty-pressure-en \
  --voice examples/azure-voice/contracts/incident_commander/VOICE.md
```

The harness opens a new server-side WebSocket session, sends text, and records
audio output, its transcript, sanitized event timing, and numeric usage. It
requires Azure to confirm the exact composed application and VoiceMD
instructions in `session.updated` before sending the turn.

Realtime and transcription clients reject every WebSocket redirect before a
credential-bearing reconnect can occur.

This command does not stream microphone audio, exercise VAD, test barge-in, or
measure natural full-duplex turn taking. Those require a separate WebRTC or
audio-input harness.

### `transcribe`

Stream a prepared PCM16 WAV to the `gpt-live-transcribe` deployment:

```bash
voicemd-azure transcribe \
  --input-audio input-24k-mono.wav \
  --language en \
  --delay medium
```

Supported delay values are `minimal`, `low`, `medium`, `high`, and `xhigh`.
Add `--pace-realtime` to wait between chunks according to their audio duration:

```bash
voicemd-azure transcribe \
  --input-audio input-24k-mono.wav \
  --language ru \
  --delay low \
  --pace-realtime
```

Without `--pace-realtime`, the file is sent as quickly as the connection
allows. The resulting timing is therefore not live-caption latency.

The file adapter commits source audio every three seconds by default and sends
one explicit trailing-silence flush so delayed final segments are emitted. The
flush is recorded separately and is never included as a source transcript
segment. Advanced replay controls are explicit:

```bash
voicemd-azure transcribe \
  --input-audio input-24k-mono.wav \
  --commit-seconds 3 \
  --flush-silence-ms 1000
```

Raw transcription is intentionally outside VoiceMD. The manifest records that
the contract activation decision was `false` for exact raw data; it does not
lint or rewrite the transcript. Exact provider segments are stored in
`raw.segments.jsonl`. `raw.transcript.txt` is a display derivative made only by
joining those segments with one space; it can expose boundary repetitions and
is not presented as a cleaned transcript.

The transcription usage object aggregates only source-audio commits. It
deliberately excludes the trailing-silence flush, so it is deterministic across
event arrival orders but must not be presented as complete billed usage.

### `showcase`

Demonstrate the authority boundary end to end: first store the model's raw
transcript without VoiceMD rewriting, then pass that transcript as untrusted
user speech to a fresh Realtime response governed by a selected `VOICE.md`:

```bash
voicemd-azure showcase \
  --input-audio input-24k-mono.wav \
  --language en \
  --voice examples/azure-voice/contracts/executive_brief/VOICE.md
```

The evidence directory keeps the raw transcript, spoken response transcript,
audio response, and separate event traces. VoiceMD applies only to the spoken
response.

### `matrix`

Run every contract listed in `scenarios.json` across selected model lanes:

```bash
voicemd-azure matrix --scenario degraded-service-en
```

> **Paid-call warning:** the default matrix runs three contracts across
> `audio`, `realtime`, and `realtime-mini`: nine billable Azure calls. Repeating
> the command creates and bills another matrix. Check Azure pricing, quota, and
> deployment availability before running it.

Limit the paid scope while developing:

```bash
voicemd-azure matrix \
  --scenario degraded-service-en \
  --lanes realtime-mini
```

Available matrix lanes are `audio`, `realtime`, and `realtime-mini`.
Transcription and `showcase` are not part of the matrix. `--input-audio`, when
provided, is consumed only by the audio-completion lane; the two Realtime lanes
remain text-to-audio turns.

Configure each matrix deployment through its lane-specific deployment
environment variable. The matrix intentionally has no shared `--deployment`
flag because one deployment name cannot correctly select three unlike lanes.

The command continues after an individual lane failure, reports each result,
and returns a failure status if any assertion or call fails. When evidence was
produced, it also attempts to refresh the gallery.

### `verify`

Recompute all declared artifact sizes and SHA-256 hashes under the default
evidence root:

```bash
voicemd-azure verify
```

Verify a different tree or one manifest:

```bash
voicemd-azure verify /path/to/artifacts
voicemd-azure verify /path/to/run/manifest.json
```

Verification is offline. It validates the manifest against the bundled JSON
Schema, recomputes every artifact and checksum inventory entry, verifies the
recorded context/output hash links, and rejects missing files, symlinks, path
reuse, directory escapes, unsupported manifests, and known secret-bearing
manifest field names. Schema and secret checks run before a manifest is written.

### `gallery`

Build a static HTML index after verifying every manifest:

```bash
voicemd-azure gallery
```

Or select explicit locations:

```bash
voicemd-azure gallery \
  --root /path/to/artifacts \
  --output /path/to/artifacts/index.html
```

The gallery displays lane, deployment, contract label, assertion status,
client-observed total time, transcript, and playable audio when present. Audio
is referenced with relative paths, so keep `index.html` with its evidence tree;
the HTML file alone is not a portable evidence bundle.

## Scenarios, prompts, and contracts

The default scenario is `degraded-service-en`. Select another bundled scenario
with `--scenario`, or bypass the scenario corpus with `--prompt`:

```bash
voicemd-azure realtime \
  --scenario customer-impact-ru \
  --voice examples/azure-voice/contracts/calm_support/VOICE.md

voicemd-azure realtime \
  --prompt 'State the known facts and the one missing decision.' \
  --voice /approved/contracts/VOICE.md \
  --voice-root /approved/contracts
```

`--voice-root` defines the allowed local source root for contract loading and
local `extends`. Global VoiceMD files are not loaded. Application-owned base
instructions are supplied separately with `--base-instructions-file` and have
higher authority than the compiled communication contract.

For bundled scenarios, deterministic assertions check required or forbidden
phrases and the selected VoiceMD linter checks hard observable rules. These are
narrow regression checks, not a semantic quality score.

## Evidence layout

A successful or assertion-failing paid run creates a uniquely named directory:

```text
examples/azure-voice/artifacts/
  20260824T...-realtime-gpt-realtime-2.1-incident_commander-.../
    manifest.json
    checksums.sha256
    output.wav
    output.transcript.txt
    events.jsonl
    voice.source.md
    voice.resolved.json
    voice.compiled.txt
    base-instructions.txt
    session.instructions.txt
    scenario.json
```

Artifact names vary by lane:

- audio completion: `output.wav` and `output.transcript.txt`;
- realtime: output WAV, output transcript, and `events.jsonl`;
- transcription: `raw.segments.jsonl`, rendered `raw.transcript.txt`, and `events.jsonl`;
- showcase: raw and response transcripts, response WAV, and separate
  transcription and response event traces.

Input audio is not copied into the run directory. The audio-completion lane
hashes the exact WAV or MP3 request bytes. Transcription and showcase hash the
exact decoded PCM16 bytes sent over the WebSocket, avoiding a second read of a
possibly changed input file.

Each `manifest.json` records, where applicable:

- lane and deployment name;
- a SHA-256 fingerprint of the normalized Azure endpoint, not its URL;
- VoiceMD source labels, selected profile, contract hash, and compiled-prompt
  hash;
- base-instruction, scenario, prompt, request, session, and input-audio hashes;
- acoustic voice and audio metadata;
- client-observed timings, event counts, and provider numeric usage counters
  within the lane-specific boundary described above;
- requested and provider-confirmed effective session hashes, plus any requested
  fields that Azure accepted but did not echo in `session.updated`;
- deterministic assertion and VoiceMD lint results;
- relative artifact paths, byte sizes, media types, and SHA-256 hashes;
- a declared `checksums.sha256` inventory covering every non-checksum artifact.

Realtime event traces are intentionally reduced to event type, local monotonic
offset, and audio-byte count where relevant. They do not preserve arbitrary
provider event payloads. Manifests and traces do not contain the API key or
endpoint URL.

`evidence.schema.json` is the enforced proof-manifest envelope. Context and
output artifacts are byte-for-byte hashable snapshots: resolved, compiled, and
composed VoiceMD inputs plus stored transcripts/audio match the corresponding
manifest hashes.

Command exit codes are:

- `0`: configured check, paid run, matrix, or verification passed;
- `1`: configuration, transport, validation, or other runtime failure;
- `2`: the provider call completed, but deterministic assertions failed, or at
  least one matrix cell failed.

## Proof boundaries

The evidence can support a bounded statement such as:

> On the recorded run, this client called the named Azure deployment, sent this
> hashed VoiceMD-derived instruction set, received the stored transcript/audio,
> and the stored output passed these deterministic checks.

It does **not** establish any of the following:

- that an Azure portal `Succeeded` state alone means the API call works;
- the underlying provider snapshot or immutable model identity beyond the
  configured deployment name;
- general model quality, word-error rate, multilingual accuracy, naturalness,
  or VoiceMD conformance outside the recorded prompts;
- deterministic behavior on later calls;
- statistically meaningful latency, throughput, availability, cost, or an
  Azure service-level agreement;
- microphone streaming, VAD, interruption handling, barge-in, telephony, or
  production full-duplex behavior;
- that VoiceMD controls acoustic voice identity, transcription truth, model
  safety, permissions, tools, or application authority;
- hard prompt-injection isolation: labeling the transcript as untrusted is an
  instruction-layer control, not a security boundary;
- independent evaluation, vendor certification, security/privacy compliance,
  or production readiness;
- cryptographic provenance: the artifacts are hash-bound to an unsigned local
  manifest, not signed or independently timestamped.

`verify` proves that declared artifacts still match the selected manifest. A
party able to replace both artifacts and the unsigned manifest can create a new
internally consistent bundle.

The harness removes credentials and endpoint URLs from manifests, but generated
audio and transcripts can still contain customer data, personal data, or spoken
secrets. Review the content before sharing or committing an evidence tree.

Microsoft currently documents GPT Realtime 2.x as preview. Preview status,
regional availability, quotas, lifecycle, and supported features can change;
recheck the current Azure documentation before making deployment or production
claims.

## Official Microsoft Azure references

- [Use the GPT Realtime API via WebSockets](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/realtime-audio-websockets)
- [Use the GPT Realtime API via WebRTC](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/realtime-audio-webrtc)
- [Azure OpenAI audio generation quickstart](https://learn.microsoft.com/en-us/azure/foundry/openai/audio-completions-quickstart)
- [Azure Chat Completions REST v1 reference](https://learn.microsoft.com/en-us/rest/api/microsoft-foundry/azureopenai/chat)
- [Realtime GA migration guide](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/realtime-audio-preview-api-migration-guide)
- [GPT Realtime 2.x preview overview](https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/realtime-2)
- [Foundry Models sold directly by Azure](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure)
- [Azure OpenAI pricing](https://azure.microsoft.com/en-us/pricing/details/azure-openai/)
