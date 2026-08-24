from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from voicemd.azure_voice import transcribe
from voicemd.azure_voice.common import (
    AzureConnection,
    AzureVoiceError,
    bytes_sha256,
    wav_bytes_from_pcm24_mono,
)


class _AsyncContext:
    def __init__(self, websocket: object):
        self.websocket = websocket

    async def __aenter__(self):
        return self.websocket

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class _ScriptedTranscriptionSocket:
    def __init__(self, events: list[dict[str, object]], *, expected_commits: int):
        self.events = list(events)
        self.expected_commits = expected_commits
        self.sent: list[dict[str, object]] = []
        self.received = 0

    async def send(self, raw: str) -> None:
        self.sent.append(json.loads(raw))

    async def recv(self) -> str:
        self.received += 1
        if self.received == 1:
            return json.dumps({"type": "session.created", "session": {}})
        if self.received == 2:
            return json.dumps(
                {"type": "session.updated", "session": self.sent[-1]["session"]}
            )
        while (
            sum(event["type"] == "input_audio_buffer.commit" for event in self.sent)
            < self.expected_commits
        ):
            await asyncio.sleep(0)
        if not self.events:
            await asyncio.sleep(60)
            raise AssertionError("unreachable")
        return json.dumps(self.events.pop(0))


def _run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    events: list[dict[str, object]],
):
    pcm = b"\x01\x00\x02\x00" * 12_000
    input_path = tmp_path / "input.wav"
    input_path.write_bytes(wav_bytes_from_pcm24_mono(pcm))
    websocket = _ScriptedTranscriptionSocket(events, expected_commits=3)

    def connect(url, *, additional_headers, max_size, open_timeout, close_timeout):
        return _AsyncContext(websocket)

    monkeypatch.setattr(transcribe, "_websocket_connect", lambda: connect)
    result = asyncio.run(
        transcribe.transcribe_wav(
            AzureConnection("https://example.openai.azure.com", "secret"),
            deployment="gpt-live-transcribe",
            input_path=str(input_path),
            commit_seconds=0.5,
            timeout_seconds=1,
        )
    )
    return result, pcm


def test_mixed_canonical_and_unbound_compatibility_preserves_exact_segments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    result, pcm = _run(
        tmp_path,
        monkeypatch,
        [
            {"type": "input_audio_buffer.committed", "item_id": "source-1"},
            {"type": "input_audio_buffer.committed", "item_id": "source-2"},
            {
                "type": "conversation.item.input_audio_transcription.completed",
                "item_id": "source-1",
                "transcript": "  first segment\n",
                "usage": {"input_tokens": 3},
            },
            {"type": "response.text.done", "text": "\tsecond segment  "},
        ],
    )

    assert result.segments == ("  first segment\n", "\tsecond segment  ")
    assert result.transcript == "  first segment\n \tsecond segment  "
    assert result.compatibility_fallback_used is True
    assert result.usage == {"input_tokens": 3}
    assert result.input_pcm_sha256 == bytes_sha256(pcm)
    assert result.input_pcm_bytes == len(pcm)


def test_flush_completion_usage_is_excluded_from_source_usage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    result, _ = _run(
        tmp_path,
        monkeypatch,
        [
            {"type": "input_audio_buffer.committed", "item_id": "source-1"},
            {"type": "input_audio_buffer.committed", "item_id": "source-2"},
            {"type": "input_audio_buffer.committed", "item_id": "flush"},
            {
                "type": "conversation.item.input_audio_transcription.completed",
                "item_id": "source-1",
                "transcript": "first",
                "usage": {"input_tokens": 3, "seconds": 1},
            },
            {
                "type": "conversation.item.input_audio_transcription.completed",
                "item_id": "flush",
                "transcript": "",
                "usage": {"input_tokens": 99, "seconds": 99},
            },
            {
                "type": "conversation.item.input_audio_transcription.completed",
                "item_id": "source-2",
                "transcript": "second",
                "usage": {"input_tokens": 4, "seconds": 1},
            },
        ],
    )

    assert result.segments == ("first", "second")
    assert result.usage == {"input_tokens": 7, "seconds": 2}
    assert result.event_counts[
        "conversation.item.input_audio_transcription.completed"
    ] == 3


def test_all_whitespace_provider_segments_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    with pytest.raises(AzureVoiceError, match="completed without text"):
        _run(
            tmp_path,
            monkeypatch,
            [
                {"type": "input_audio_buffer.committed", "item_id": "source-1"},
                {"type": "input_audio_buffer.committed", "item_id": "source-2"},
                {
                    "type": "conversation.item.input_audio_transcription.completed",
                    "item_id": "source-1",
                    "transcript": " \t\n",
                },
                {
                    "type": "conversation.item.input_audio_transcription.completed",
                    "item_id": "source-2",
                    "transcript": "  ",
                },
            ],
        )
