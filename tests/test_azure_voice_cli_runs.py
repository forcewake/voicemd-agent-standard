from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from voicemd.azure_voice import cli
from voicemd.azure_voice.audio import AudioCompletionResult
from voicemd.azure_voice.common import (
    AzureConnection,
    WavInfo,
    bytes_sha256,
    inspect_wav_bytes,
    wav_bytes_from_pcm24_mono,
)
from voicemd.azure_voice.evidence import verify_manifest
from voicemd.azure_voice.realtime import RealtimeResult
from voicemd.azure_voice.transcribe import TranscriptionResult

ROOT = Path(__file__).parents[1]
DEMO = ROOT / "examples" / "azure-voice"
VOICE = DEMO / "contracts" / "incident_commander" / "VOICE.md"
BASE = DEMO / "base-instructions.txt"
SCENARIOS = DEMO / "scenarios.json"


def _shared_args(tmp_path: Path, **overrides: object) -> Namespace:
    values: dict[str, object] = {
        "deployment": None,
        "prompt": "Give a grounded service status update.",
        "scenario": None,
        "scenario_file": str(SCENARIOS),
        "voice": str(VOICE),
        "voice_root": None,
        "profile": "default",
        "base_instructions_file": str(BASE),
        "input_audio": None,
        "acoustic_voice": "alloy",
        "timeout_seconds": 10.0,
        "output_root": str(tmp_path / "artifacts"),
    }
    values.update(overrides)
    return Namespace(**values)


def _connection(_lane: str) -> AzureConnection:
    return AzureConnection("https://example.openai.azure.com", "never-persist-this-key")


def _realtime_result(transcript: str) -> RealtimeResult:
    return RealtimeResult(
        audio_pcm=b"\x00\x00" * 240,
        transcript=transcript,
        requested_session={"type": "realtime", "instructions": "acknowledged"},
        effective_session={"type": "realtime", "instructions": "acknowledged"},
        event_counts={"response.done": 1},
        event_trace=({"type": "response.done", "offset_ms": 8},),
        timings_ms={"session_created": 1, "session_updated": 2, "total": 8},
        usage={"total_tokens": 4},
        provider_model="gpt-realtime-test-snapshot",
    )


def _transcription_result(transcript: str, pcm: bytes) -> TranscriptionResult:
    return TranscriptionResult(
        transcript=transcript,
        segments=(transcript,),
        input_info=WavInfo(
            channels=1,
            sample_rate=24_000,
            sample_width=2,
            frames=len(pcm) // 2,
            duration_ms=round(len(pcm) / 48),
        ),
        input_pcm_sha256=bytes_sha256(pcm),
        input_pcm_bytes=len(pcm),
        requested_session={"type": "transcription"},
        effective_session={"type": "transcription"},
        event_counts={"conversation.item.input_audio_transcription.completed": 1},
        event_trace=(
            {
                "type": "conversation.item.input_audio_transcription.completed",
                "offset_ms": 5,
            },
        ),
        timings_ms={"session_created": 1, "session_updated": 2, "first_text": 4, "total": 5},
        chunks_sent=1,
        commits_sent=2,
        transcript_commits=1,
        flush_chunks_sent=1,
        flush_silence_ms=1000,
        usage={"seconds": 1},
        provider_model="gpt-live-transcribe-test-snapshot",
        compatibility_fallback_used=False,
        unconfirmed_session_fields=("audio.input.transcription.delay",),
    )


def test_audio_run_writes_schema_valid_hash_bound_evidence(tmp_path: Path, monkeypatch):
    transcript = "The service is degraded. Keep the rollout paused."
    wav = wav_bytes_from_pcm24_mono(b"\x00\x00" * 240)
    monkeypatch.setattr(cli, "load_azure_connection", _connection)
    monkeypatch.setattr(
        cli,
        "create_audio_completion",
        lambda *args, **kwargs: AudioCompletionResult(
            audio=wav,
            transcript=transcript,
            wav_info=inspect_wav_bytes(wav),
            total_ms=12,
            usage={"total_tokens": 5},
            request_body={"model": "gpt-audio-1.5", "messages": []},
            provider_model="gpt-audio-test-snapshot",
        ),
    )

    path, passed = cli._audio_run(_shared_args(tmp_path))
    manifest = json.loads(path.read_text(encoding="utf-8"))

    assert passed is True
    assert verify_manifest(path)["status"] == "verified"
    assert manifest["artifacts"]["checksums"]["path"] == "checksums.sha256"
    assert manifest["response"]["transcript_sha256"] == manifest["artifacts"][
        "output_transcript"
    ]["sha256"]
    assert "never-persist-this-key" not in path.read_text(encoding="utf-8")


def test_realtime_run_writes_acknowledged_context_and_event_evidence(
    tmp_path: Path,
    monkeypatch,
):
    async def fake_realtime(*args, **kwargs):
        return _realtime_result("The service is degraded. Keep the rollout paused.")

    monkeypatch.setattr(cli, "load_azure_connection", _connection)
    monkeypatch.setattr(cli, "run_realtime_text_turn", fake_realtime)

    path, passed = cli._realtime_run(_shared_args(tmp_path))
    manifest = json.loads(path.read_text(encoding="utf-8"))

    assert passed is True
    assert verify_manifest(path)["status"] == "verified"
    assert manifest["lane"] == "realtime"
    assert manifest["request"]["instructions_sha256"] == manifest["artifacts"][
        "session_instructions"
    ]["sha256"]


def test_transcribe_run_hashes_sent_pcm_and_preserves_raw_rendering(
    tmp_path: Path,
    monkeypatch,
):
    input_path = tmp_path / "input.wav"
    input_path.write_bytes(b"original-container")
    sent_pcm = b"\x01\x00" * 240
    transcript = "  exact provider segment  "

    async def fake_transcribe(*args, **kwargs):
        input_path.write_bytes(b"changed-after-decode")
        return _transcription_result(transcript, sent_pcm)

    monkeypatch.setattr(cli, "load_azure_connection", _connection)
    monkeypatch.setattr(cli, "transcribe_wav", fake_transcribe)
    args = _shared_args(
        tmp_path,
        input_audio=str(input_path),
        language="en",
        delay="medium",
        pace_realtime=False,
        commit_seconds=3.0,
        flush_silence_ms=1000,
    )

    path, passed = cli._transcribe_run(args)
    manifest = json.loads(path.read_text(encoding="utf-8"))

    assert passed is True
    assert verify_manifest(path)["status"] == "verified"
    assert manifest["request"]["input_audio_sha256"] == bytes_sha256(sent_pcm)
    assert manifest["request"]["input_audio_bytes"] == len(sent_pcm)
    assert (path.parent / "raw.transcript.txt").read_text(encoding="utf-8") == transcript
    assert manifest["voice"]["applied"] is False


def test_showcase_keeps_raw_boundary_separate_from_spoken_contract(
    tmp_path: Path,
    monkeypatch,
):
    input_path = tmp_path / "input.wav"
    input_path.write_bytes(b"container")
    sent_pcm = b"\x01\x00" * 240

    async def fake_transcribe(*args, **kwargs):
        return _transcription_result("Raw user speech.", sent_pcm)

    async def fake_realtime(*args, **kwargs):
        assert "untrusted user speech" in kwargs["prompt"]
        return _realtime_result("The service is degraded. Keep the rollout paused.")

    monkeypatch.setattr(cli, "load_azure_connection", _connection)
    monkeypatch.setattr(cli, "transcribe_wav", fake_transcribe)
    monkeypatch.setattr(cli, "run_realtime_text_turn", fake_realtime)
    args = _shared_args(
        tmp_path,
        input_audio=str(input_path),
        language="en",
        delay="medium",
        pace_realtime=False,
        commit_seconds=3.0,
        flush_silence_ms=1000,
        transcribe_deployment=None,
        realtime_deployment=None,
    )

    path, passed = cli._showcase_run(args)
    manifest = json.loads(path.read_text(encoding="utf-8"))

    assert passed is True
    assert verify_manifest(path)["status"] == "verified"
    assert manifest["transcription_voice_boundary"]["applied"] is False
    assert manifest["voice"]["applied"] is True
    assert manifest["response"]["rendered_transcript_sha256"] == manifest["artifacts"][
        "raw_transcript"
    ]["sha256"]
