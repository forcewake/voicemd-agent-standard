from __future__ import annotations

import asyncio
import base64
import json
import os
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from voicemd.azure_voice import audio, realtime, transcribe
from voicemd.azure_voice import cli as azure_cli
from voicemd.azure_voice.common import (
    EVIDENCE_SCHEMA,
    AzureConnection,
    audio_chat_messages,
    bind_voice_contract,
    bytes_sha256,
    compose_realtime_instructions,
    inspect_wav_bytes,
    load_env_file,
    normalize_azure_endpoint,
    normalize_streaming_wav,
    raw_transcript_activation,
    read_pcm24_mono_wav,
    text_sha256,
    validate_acoustic_voice,
    wav_bytes_from_pcm24_mono,
)
from voicemd.azure_voice.evidence import (
    artifact_descriptor,
    render_gallery,
    verify_manifest,
    write_checksums,
    write_manifest,
)

ROOT = Path(__file__).parents[1]
DEMO = ROOT / "examples" / "azure-voice"
PACKAGED_DEMO = ROOT / "src" / "voicemd" / "resources" / "azure_voice"
VOICE = DEMO / "contracts" / "incident_commander" / "VOICE.md"


def _binding():
    return bind_voice_contract(VOICE, source_root=VOICE.parent)


def _evidence_manifest(
    run_dir: Path,
    artifacts: dict[str, dict[str, object]],
    *,
    voice: dict[str, object] | None = None,
    **overrides: object,
) -> dict[str, object]:
    declared = dict(artifacts)
    checksums = write_checksums(run_dir, declared)
    declared["checksums"] = artifact_descriptor(
        run_dir,
        checksums,
        media_type="text/plain; charset=utf-8",
    )
    manifest: dict[str, object] = {
        "$schema": EVIDENCE_SCHEMA,
        "created_at": "2026-08-24T00:00:00Z",
        "run_id": run_dir.name,
        "provider": "azure-openai",
        "lane": "audio-completion",
        "deployment": "gpt-audio-1.5",
        "endpoint_sha256": bytes_sha256(b"endpoint"),
        "voice": voice or {"applied": False},
        "request": {"sha256": bytes_sha256(b"request")},
        "response": {},
        "timings_ms": {},
        "assertions": {"passed": True, "checks": []},
        "artifacts": declared,
    }
    manifest.update(overrides)
    return manifest


def test_demo_contracts_are_distinct_and_raw_transcript_is_excluded():
    hashes: set[str] = set()
    for path in sorted((DEMO / "contracts").glob("*/VOICE.md")):
        binding = bind_voice_contract(path, source_root=path.parent)
        hashes.add(binding.contract_sha256)
        assert binding.activation_reason == "human-facing output kind: spoken"
        assert binding.compiled
    assert len(hashes) == 3

    boundary = raw_transcript_activation(VOICE, source_root=VOICE.parent)
    assert boundary["applied"] is False
    assert boundary["reason"] == "exact output required"


def test_packaged_demo_runtime_resources_are_byte_exact_copies():
    expected = {
        Path("base-instructions.txt"),
        Path("evidence.schema.json"),
        Path("scenarios.json"),
        Path("contracts/calm_support/VOICE.md"),
        Path("contracts/executive_brief/VOICE.md"),
        Path("contracts/incident_commander/VOICE.md"),
    }
    assert set(azure_cli.DEMO_RESOURCE_PATHS) == expected
    for relative in sorted(expected):
        assert (PACKAGED_DEMO / relative).read_bytes() == (DEMO / relative).read_bytes()


def test_demo_root_prefers_source_and_falls_back_to_packaged_resources(tmp_path: Path):
    assert azure_cli._select_demo_root(DEMO, PACKAGED_DEMO) == DEMO
    assert azure_cli._select_demo_root(tmp_path / "missing", PACKAGED_DEMO) == PACKAGED_DEMO
    assert azure_cli._demo_resources_complete(PACKAGED_DEMO)


def test_installed_default_artifact_root_is_writable_project_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(azure_cli, "DEMO_ROOT", PACKAGED_DEMO)
    expected = tmp_path / ".voice" / "azure-voice-artifacts"
    assert azure_cli._default_artifacts_root() == expected
    args = azure_cli.build_parser().parse_args(["verify"])
    assert Path(args.path) == expected
    assert not expected.is_relative_to(PACKAGED_DEMO)


def test_azure_voice_evidence_schema_is_valid_draft_2020_12():
    schema = json.loads((DEMO / "evidence.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)


@pytest.mark.parametrize(
    ("endpoint", "expected"),
    [
        ("https://Example.openai.azure.com/", "https://example.openai.azure.com"),
        (
            "https://Example.openai.azure.com/openai/v1/",
            "https://example.openai.azure.com",
        ),
        ("https://example.openai.azure.com:443", "https://example.openai.azure.com:443"),
    ],
)
def test_normalize_azure_endpoint(endpoint: str, expected: str):
    assert normalize_azure_endpoint(endpoint) == expected


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://example.openai.azure.com",
        "https://user:pass@example.openai.azure.com",
        "https://example.openai.azure.com/path",
        "https://example.openai.azure.com?api-key=secret",
        "not-a-url",
    ],
)
def test_normalize_azure_endpoint_rejects_unsafe_urls(endpoint: str):
    with pytest.raises(ValueError):
        normalize_azure_endpoint(endpoint)


def test_dotenv_loader_does_not_overwrite_and_does_not_expand(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://kept.openai.azure.com")
    env_file = tmp_path / ".env"
    env_file.write_text(
        "AZURE_OPENAI_ENDPOINT=https://ignored.openai.azure.com\n"
        "AZURE_OPENAI_API_KEY='literal-$NOT_EXPANDED'\n",
        encoding="utf-8",
    )
    load_env_file(env_file)
    assert os.environ["AZURE_OPENAI_ENDPOINT"] == "https://kept.openai.azure.com"
    assert os.environ["AZURE_OPENAI_API_KEY"] == "literal-$NOT_EXPANDED"


def test_instruction_composition_keeps_application_authority_first():
    binding = _binding()
    rendered = compose_realtime_instructions("Facts are immutable.", binding)
    assert rendered.startswith("APPLICATION AUTHORITY (higher priority):")
    assert rendered.index("Facts are immutable.") < rendered.index(
        "VOICEMD COMMUNICATION CONTRACT (lower priority):"
    )
    assert rendered.index("VOICEMD COMMUNICATION CONTRACT") < rendered.index(
        binding.compiled
    )

    messages = audio_chat_messages(
        base_instructions="Facts are immutable.",
        binding=binding,
        prompt="Give a status update.",
    )
    assert [message["role"] for message in messages] == ["developer", "user"]
    assert str(messages[0]["content"]).startswith("APPLICATION AUTHORITY")
    assert binding.compiled in messages[0]["content"]

    with pytest.raises(ValueError, match="wav or mp3"):
        audio_chat_messages(
            base_instructions="Facts are immutable.",
            binding=binding,
            prompt="Status?",
            input_audio=("flac", b"not-empty"),
        )
    with pytest.raises(ValueError, match="nonempty"):
        audio_chat_messages(
            base_instructions="Facts are immutable.",
            binding=binding,
            prompt="Status?",
            input_audio=("wav", b""),
        )


def test_acoustic_voice_is_validated_against_current_builtin_ids():
    assert validate_acoustic_voice("cedar") == "cedar"
    with pytest.raises(ValueError, match="acoustic voice"):
        validate_acoustic_voice("made-up-but-safe")


def test_cli_lints_generated_transcript_against_selected_contract():
    result = azure_cli._lint_result(
        VOICE,
        "default",
        "The service is degraded. No data loss is reported. Keep the rollout paused.",
    )
    assert result == {"clean": True, "issues": []}


def test_context_artifacts_bind_exact_contract_prompt_and_authority(tmp_path: Path):
    binding = _binding()
    base = "Use only supplied facts."
    artifacts = azure_cli._write_context_artifacts(
        tmp_path,
        voice_path=VOICE,
        profile="default",
        binding=binding,
        base_path=DEMO / "base-instructions.txt",
        base_instructions=base,
        scenario={"id": "case", "prompt": "Status?"},
    )
    assert artifacts["voice_resolved"]["sha256"] == binding.contract_sha256
    assert artifacts["voice_compiled"]["sha256"] == binding.compiled_sha256
    assert artifacts["base_instructions"]["sha256"] == text_sha256(base)
    assert artifacts["session_instructions"]["sha256"] == text_sha256(
        compose_realtime_instructions(base, binding)
    )


def test_context_artifacts_and_lint_honor_explicit_parent_source_root(tmp_path: Path):
    base_voice = tmp_path / "base.md"
    base_voice.write_text(
        "---\nvoice_spec: '0.1'\nkind: VoiceContract\nname: Parent\n"
        "activation: {mode: contextual, include: [spoken], exclude: [raw_data]}\n"
        "response: {max_words: 10}\n---\nBe concise.\n",
        encoding="utf-8",
    )
    child_dir = tmp_path / "child"
    child_dir.mkdir()
    child_voice = child_dir / "VOICE.md"
    child_voice.write_text(
        "---\nvoice_spec: '0.1'\nkind: VoiceContract\nextends: ../base.md\n---\n"
        "State the result first.\n",
        encoding="utf-8",
    )
    binding = bind_voice_contract(child_voice, profile=None, source_root=tmp_path)

    artifacts = azure_cli._write_context_artifacts(
        tmp_path / "run",
        voice_path=child_voice,
        profile=None,
        source_root=tmp_path,
        binding=binding,
    )
    assert artifacts["voice_resolved"]["sha256"] == binding.contract_sha256
    assert azure_cli._lint_result(
        child_voice,
        None,
        "Service degraded.",
        source_root=tmp_path,
    )["clean"] is True


def test_evidence_verifier_binds_context_hashes(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    resolved = run_dir / "voice.resolved.json"
    resolved.write_text("{}", encoding="utf-8")
    descriptor = artifact_descriptor(run_dir, resolved, media_type="application/json")
    manifest = _evidence_manifest(
        run_dir,
        {"voice_resolved": descriptor},
        voice={
            "applied": False,
            "contract_sha256": descriptor["sha256"],
        },
    )
    path = write_manifest(run_dir, manifest)
    assert verify_manifest(path)["status"] == "verified"

    manifest["voice"]["contract_sha256"] = bytes_sha256(b"other")
    write_manifest(run_dir, manifest)
    with pytest.raises(ValueError, match="does not match"):
        verify_manifest(path)


def test_pcm_wav_round_trip(tmp_path: Path):
    pcm = (b"\x00\x00\x01\x00" * 240)
    wav = wav_bytes_from_pcm24_mono(pcm)
    info = inspect_wav_bytes(wav)
    assert info.sample_rate == 24_000
    assert info.channels == 1
    assert info.sample_width == 2
    path = tmp_path / "sample.wav"
    path.write_bytes(wav)
    decoded, decoded_info = read_pcm24_mono_wav(path)
    assert decoded == pcm
    assert decoded_info == info


def test_streaming_wav_sentinel_lengths_are_normalized():
    wav = bytearray(wav_bytes_from_pcm24_mono(b"\x00\x00" * 24_000))
    data_offset = wav.index(b"data")
    wav[4:8] = b"\xff\xff\xff\xff"
    wav[data_offset + 4 : data_offset + 8] = b"\xff\xff\xff\xff"
    normalized = normalize_streaming_wav(bytes(wav))
    assert normalized[4:8] == (len(normalized) - 8).to_bytes(4, "little")
    assert inspect_wav_bytes(normalized).duration_ms == 1000


class _FakeHttpResponse:
    def __init__(self, payload: object):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self, limit: int) -> bytes:
        return self.payload[:limit]


class _FakeOpener:
    def __init__(self, payload: object):
        self.payload = payload
        self.request = None

    def open(self, request, timeout):
        self.request = request
        return _FakeHttpResponse(self.payload)


def test_audio_completion_extracts_playable_wav_and_never_serializes_key(monkeypatch):
    wav = wav_bytes_from_pcm24_mono(b"\x00\x00" * 240)
    opener = _FakeOpener(
        {
            "choices": [
                {
                    "message": {
                        "audio": {
                            "data": base64.b64encode(wav).decode("ascii"),
                            "transcript": "The service is degraded.",
                        }
                    }
                }
            ],
            "usage": {"prompt_tokens": 12, "completion_tokens": 4},
        }
    )
    monkeypatch.setattr(audio, "_OPENER", opener)
    connection = AzureConnection("https://example.openai.azure.com", "not-in-evidence")
    result = audio.create_audio_completion(
        connection,
        deployment="gpt-audio-1.5",
        base_instructions="Use only supplied facts.",
        binding=_binding(),
        prompt="Give a status update.",
    )
    assert result.audio == wav
    assert result.transcript == "The service is degraded."
    assert result.wav_info.sample_rate == 24_000
    assert opener.request.get_header("Api-key") == "not-in-evidence"
    assert b"not-in-evidence" not in opener.request.data


class _RealtimeWebSocket:
    def __init__(self):
        self.sent: list[dict[str, object]] = []
        self.received = 0

    async def send(self, raw: str):
        self.sent.append(json.loads(raw))

    async def recv(self):
        self.received += 1
        if self.received == 1:
            return json.dumps({"type": "session.created", "session": {"model": "returned"}})
        if self.received == 2:
            session = self.sent[-1]["session"]
            return json.dumps({"type": "session.updated", "session": session})
        if self.received == 3:
            return json.dumps(
                {"type": "response.output_audio_transcript.delta", "delta": "Degraded."}
            )
        if self.received == 4:
            return json.dumps(
                {
                    "type": "response.output_audio.delta",
                    "delta": base64.b64encode(b"\x00\x00" * 120).decode("ascii"),
                }
            )
        return json.dumps(
            {
                "type": "response.done",
                "response": {
                    "status": "completed",
                    "output": [{"content": [{"transcript": "Degraded."}]}],
                    "usage": {"total_tokens": 7},
                },
            }
        )


class _TranscribeWebSocket:
    def __init__(self):
        self.sent: list[dict[str, object]] = []
        self.received = 0

    async def send(self, raw: str):
        self.sent.append(json.loads(raw))

    async def recv(self):
        self.received += 1
        if self.received == 1:
            return json.dumps({"type": "session.created", "session": {}})
        if self.received == 2:
            return json.dumps(
                {"type": "session.updated", "session": self.sent[-1]["session"]}
            )
        if self.received == 3:
            return json.dumps(
                {"type": "input_audio_buffer.committed", "item_id": "item-1"}
            )
        return json.dumps(
            {
                "type": "conversation.item.input_audio_transcription.completed",
                "item_id": "item-1",
                "transcript": "Raw AC-42 transcript.",
            }
        )


class _MultiTranscribeWebSocket(_TranscribeWebSocket):
    async def recv(self):
        self.received += 1
        if self.received == 1:
            return json.dumps({"type": "session.created", "session": {}})
        if self.received == 2:
            return json.dumps(
                {"type": "session.updated", "session": self.sent[-1]["session"]}
            )
        if self.received == 3:
            return json.dumps(
                {"type": "input_audio_buffer.committed", "item_id": "item-1"}
            )
        if self.received == 4:
            return json.dumps(
                {"type": "input_audio_buffer.committed", "item_id": "item-2"}
            )
        item_id = "item-2" if self.received == 5 else "item-1"
        return json.dumps(
            {
                "type": "conversation.item.input_audio_transcription.completed",
                "item_id": item_id,
                "transcript": "first segment" if item_id == "item-1" else "second segment",
                "usage": {"input_tokens": 3},
            }
        )


class _AsyncContext:
    def __init__(self, websocket):
        self.websocket = websocket

    async def __aenter__(self):
        return self.websocket

    async def __aexit__(self, exc_type, exc, traceback):
        return False


def test_realtime_adapter_verifies_session_and_collects_audio(monkeypatch):
    websocket = _RealtimeWebSocket()

    def connect(url, *, additional_headers, max_size, open_timeout, close_timeout):
        assert url.endswith("?model=gpt-realtime-2.1")
        assert additional_headers == {"api-key": "secret"}
        return _AsyncContext(websocket)

    monkeypatch.setattr(realtime, "_websocket_connect", lambda: connect)
    result = asyncio.run(
        realtime.run_realtime_text_turn(
            AzureConnection("https://example.openai.azure.com", "secret"),
            deployment="gpt-realtime-2.1",
            base_instructions="Use supplied facts.",
            binding=_binding(),
            prompt="Status?",
        )
    )
    assert result.transcript == "Degraded."
    assert result.audio_pcm
    assert result.event_counts["session.updated"] == 1
    assert result.timings_ms["first_audio"] is not None
    assert websocket.sent[0]["type"] == "session.update"
    assert websocket.sent[-1]["type"] == "response.create"


def test_transcription_adapter_never_sends_voicemd(tmp_path: Path, monkeypatch):
    input_path = tmp_path / "input.wav"
    input_path.write_bytes(wav_bytes_from_pcm24_mono(b"\x00\x00" * 2400))
    websocket = _TranscribeWebSocket()

    def connect(url, *, additional_headers, max_size, open_timeout, close_timeout):
        assert url.endswith("?intent=transcription")
        assert additional_headers == {"api-key": "secret"}
        return _AsyncContext(websocket)

    monkeypatch.setattr(transcribe, "_websocket_connect", lambda: connect)
    result = asyncio.run(
        transcribe.transcribe_wav(
            AzureConnection("https://example.openai.azure.com", "secret"),
            deployment="gpt-live-transcribe",
            input_path=str(input_path),
        )
    )
    assert result.transcript == "Raw AC-42 transcript."
    assert result.segments == ("Raw AC-42 transcript.",)
    assert result.unconfirmed_session_fields == ()
    assert result.transcript_commits == 1
    assert result.commits_sent == 2
    session = websocket.sent[0]["session"]
    assert session["type"] == "transcription"
    assert "instructions" not in session
    assert session["audio"]["input"]["transcription"]["model"] == "gpt-live-transcribe"
    assert websocket.sent[-1]["type"] == "input_audio_buffer.commit"


def test_transcription_periodically_commits_and_aggregates_every_item(
    tmp_path: Path, monkeypatch
):
    input_path = tmp_path / "input.wav"
    input_path.write_bytes(wav_bytes_from_pcm24_mono(b"\x00\x00" * 24_000))
    websocket = _MultiTranscribeWebSocket()

    def connect(url, *, additional_headers, max_size, open_timeout, close_timeout):
        return _AsyncContext(websocket)

    monkeypatch.setattr(transcribe, "_websocket_connect", lambda: connect)
    result = asyncio.run(
        transcribe.transcribe_wav(
            AzureConnection("https://example.openai.azure.com", "secret"),
            deployment="gpt-live-transcribe",
            input_path=str(input_path),
            commit_seconds=0.5,
        )
    )
    commits = [event for event in websocket.sent if event["type"] == "input_audio_buffer.commit"]
    assert len(commits) == 3
    assert result.transcript_commits == 2
    assert result.commits_sent == 3
    assert result.flush_silence_ms == 1000
    assert result.transcript == "first segment second segment"
    assert result.segments == ("first segment", "second segment")
    assert result.usage == {"input_tokens": 6}


def test_evidence_verifier_detects_tampering_and_gallery_escapes_text(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    transcript = run_dir / "output.transcript.txt"
    transcript.write_text("<script>alert(1)</script>\n", encoding="utf-8")
    descriptor = artifact_descriptor(
        run_dir, transcript, media_type="text/plain; charset=utf-8"
    )
    manifest = _evidence_manifest(
        run_dir,
        {"output_transcript": descriptor},
        voice={"applied": False, "label": "incident_commander"},
        endpoint_sha256=text_sha256("https://example.openai.azure.com"),
        timings_ms={"total": 10},
    )
    path = write_manifest(run_dir, manifest)
    verified = verify_manifest(path)
    assert verified["status"] == "verified"
    gallery = render_gallery(tmp_path)
    html_text = gallery.read_text(encoding="utf-8")
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html_text
    assert "<script>alert(1)</script>" not in html_text

    transcript.write_text("tampered\n", encoding="utf-8")
    with pytest.raises(ValueError, match="mismatch"):
        verify_manifest(path)


def test_evidence_rejects_secret_bearing_fields(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    artifact = run_dir / "x.txt"
    artifact.write_text("safe", encoding="utf-8")
    manifest = _evidence_manifest(
        run_dir,
        {"x": artifact_descriptor(run_dir, artifact, media_type="text/plain")},
        api_key="must-never-be-here",
    )
    with pytest.raises(ValueError, match="forbidden"):
        write_manifest(run_dir, manifest)
    assert not (run_dir / "manifest.json").exists()


def test_evidence_writer_rejects_schema_invalid_manifest_before_disk(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    with pytest.raises(ValueError, match="schema violation"):
        write_manifest(run_dir, {"$schema": EVIDENCE_SCHEMA})
    assert not (run_dir / "manifest.json").exists()


def test_matrix_rejects_contract_path_escape_before_any_paid_call(
    tmp_path: Path,
    monkeypatch,
):
    scenario_file = tmp_path / "scenarios.json"
    scenario_file.write_text(
        json.dumps({"contracts": [{"path": "../outside.md"}], "scenarios": []}),
        encoding="utf-8",
    )
    paid_call_reached = False

    def fail_if_called(*args, **kwargs):
        nonlocal paid_call_reached
        paid_call_reached = True
        raise AssertionError("paid call must not run")

    monkeypatch.setattr(azure_cli, "_audio_run", fail_if_called)
    args = type(
        "Args",
        (),
        {
            "scenario_file": str(scenario_file),
            "lanes": ["audio"],
            "output_root": str(tmp_path / "artifacts"),
        },
    )()
    with pytest.raises(ValueError, match="escapes"):
        azure_cli._matrix(args)
    assert paid_call_reached is False
