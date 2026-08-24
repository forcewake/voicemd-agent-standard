from __future__ import annotations

import asyncio
import base64
import inspect
import json
import math
import time
import uuid
from collections import Counter
from dataclasses import dataclass

from .common import (
    MAX_EVENTS,
    MAX_TRANSCRIPT_CHARS,
    AzureConnection,
    AzureVoiceError,
    WavInfo,
    aggregate_numeric_usage,
    bytes_sha256,
    confirmed_session_subset,
    harden_websocket_connect,
    numeric_usage,
    read_pcm24_mono_wav,
    safe_error_detail,
    strict_json_loads,
    transcription_url,
    validate_deployment_name,
    validate_timeout,
)

TRANSCRIPTION_DELAYS = frozenset({"minimal", "low", "medium", "high", "xhigh"})


@dataclass(frozen=True)
class TranscriptionResult:
    transcript: str
    segments: tuple[str, ...]
    input_info: WavInfo
    input_pcm_sha256: str
    input_pcm_bytes: int
    requested_session: dict[str, object]
    effective_session: dict[str, object]
    event_counts: dict[str, int]
    event_trace: tuple[dict[str, object], ...]
    timings_ms: dict[str, int | None]
    chunks_sent: int
    commits_sent: int
    transcript_commits: int
    flush_chunks_sent: int
    flush_silence_ms: int
    usage: object | None
    provider_model: str | None
    compatibility_fallback_used: bool
    unconfirmed_session_fields: tuple[str, ...]


def _websocket_connect():
    try:
        from websockets.asyncio.client import connect
        from websockets.exceptions import SecurityError
    except ImportError:
        try:
            from websockets import connect
            from websockets.exceptions import SecurityError
        except ImportError as exc:
            raise RuntimeError(
                "Azure transcription support requires: pip install 'voicemd[azure-voice]'"
            ) from exc
    return harden_websocket_connect(connect, SecurityError)


async def _recv_event(websocket: object, timeout_seconds: float) -> dict[str, object]:
    try:
        raw = await asyncio.wait_for(websocket.recv(), timeout=timeout_seconds)
    except asyncio.TimeoutError as exc:
        raise AzureVoiceError("timed out waiting for an Azure transcription event") from exc
    event = strict_json_loads(raw)
    if not isinstance(event, dict) or not isinstance(event.get("type"), str):
        raise TypeError("Azure transcription event must have a string type")
    if event["type"] == "error":
        raise AzureVoiceError(f"Azure transcription error: {safe_error_detail(event)}")
    return event


async def transcribe_wav(
    connection: AzureConnection,
    *,
    deployment: str,
    input_path: str,
    language: str | None = None,
    delay: str = "medium",
    timeout_seconds: float = 90.0,
    pace_realtime: bool = False,
    commit_seconds: float = 3.0,
    flush_silence_ms: int = 1000,
) -> TranscriptionResult:
    deployment = validate_deployment_name(deployment)
    timeout_seconds = validate_timeout(timeout_seconds)
    if not math.isfinite(commit_seconds) or not 0.25 <= commit_seconds <= 30:
        raise ValueError("commit_seconds must be between 0.25 and 30")
    if not isinstance(flush_silence_ms, int) or not 100 <= flush_silence_ms <= 5000:
        raise ValueError("flush_silence_ms must be an integer between 100 and 5000")
    delay = delay.strip().casefold()
    if delay not in TRANSCRIPTION_DELAYS:
        raise ValueError(f"transcription delay must be one of {sorted(TRANSCRIPTION_DELAYS)}")
    if language is not None:
        language = language.strip().casefold()
        if not language or len(language) > 16 or not language.replace("-", "").isalpha():
            raise ValueError("language hint must be a short ISO-style language tag")
    pcm, input_info = read_pcm24_mono_wav(input_path)
    input_pcm_sha256 = bytes_sha256(pcm)
    input_pcm_bytes = len(pcm)
    transcription: dict[str, object] = {"model": deployment, "delay": delay}
    if language:
        transcription["language"] = language
    session: dict[str, object] = {
        "type": "transcription",
        "audio": {
            "input": {
                "format": {"type": "audio/pcm", "rate": 24_000},
                "turn_detection": None,
                "transcription": transcription,
            }
        },
    }
    connect = _websocket_connect()
    header_argument = (
        "additional_headers" if "additional_headers" in inspect.signature(connect).parameters
        else "extra_headers"
    )
    kwargs = {
        header_argument: {"api-key": connection.api_key},
        "max_size": 4 * 1024 * 1024,
        "open_timeout": timeout_seconds,
        "close_timeout": min(timeout_seconds, 30.0),
    }
    started = time.monotonic()
    counts: Counter[str] = Counter()
    trace: list[dict[str, object]] = []
    session_created_ms: int | None = None
    session_updated_ms: int | None = None
    first_text_ms: int | None = None
    provider_model: str | None = None
    effective_session: dict[str, object] | None = None
    unconfirmed_session_fields: tuple[str, ...] = ()

    def record(event: dict[str, object]) -> None:
        event_type = str(event["type"])
        counts[event_type] += 1
        trace.append(
            {
                "offset_ms": round((time.monotonic() - started) * 1000),
                "type": event_type,
            }
        )
        if len(trace) > MAX_EVENTS:
            raise AzureVoiceError(f"Azure transcription session exceeded {MAX_EVENTS} events")

    async with connect(transcription_url(connection), **kwargs) as websocket:
        while True:
            created = await _recv_event(websocket, timeout_seconds)
            record(created)
            if created["type"] == "session.created":
                created_session = created.get("session")
                if isinstance(created_session, dict) and isinstance(
                    created_session.get("model"), str
                ):
                    provider_model = created_session["model"]
                session_created_ms = trace[-1]["offset_ms"]  # type: ignore[assignment]
                break
        await asyncio.wait_for(
            websocket.send(
                json.dumps(
                    {
                        "type": "session.update",
                        "event_id": str(uuid.uuid4()),
                        "session": session,
                    },
                    ensure_ascii=False,
                    allow_nan=False,
                    separators=(",", ":"),
                )
            ),
            timeout=timeout_seconds,
        )
        while True:
            updated = await _recv_event(websocket, timeout_seconds)
            record(updated)
            if updated["type"] == "session.updated":
                effective = updated.get("session")
                acknowledged_transcription = {
                    key: value for key, value in transcription.items() if key != "delay"
                }
                acknowledged_session: dict[str, object] = {
                    "type": "transcription",
                    "audio": {
                        "input": {
                            "format": {"type": "audio/pcm", "rate": 24_000},
                            "turn_detection": None,
                            "transcription": acknowledged_transcription,
                        }
                    },
                }
                confirmed = confirmed_session_subset(effective, acknowledged_session)
                if not isinstance(confirmed, dict):
                    raise AzureVoiceError("Azure returned an invalid effective transcription session")
                effective_session = confirmed
                effective_transcription: object = None
                if isinstance(effective, dict):
                    audio = effective.get("audio")
                    audio_input = audio.get("input") if isinstance(audio, dict) else None
                    effective_transcription = (
                        audio_input.get("transcription")
                        if isinstance(audio_input, dict)
                        else None
                    )
                if isinstance(effective_transcription, dict):
                    echoed_delay = effective_transcription.get("delay")
                    if echoed_delay is None:
                        unconfirmed_session_fields = ("audio.input.transcription.delay",)
                    elif echoed_delay != delay:
                        raise AzureVoiceError(
                            "Azure did not confirm session.audio.input.transcription.delay"
                        )
                    if isinstance(effective_transcription.get("model"), str):
                        provider_model = effective_transcription["model"]
                session_updated_ms = trace[-1]["offset_ms"]  # type: ignore[assignment]
                break
        chunk_size = 4_800
        chunks_per_commit = max(1, round(commit_seconds * 24_000 * 2 / chunk_size))
        sender_done = asyncio.Event()
        transcript_commits = 0
        commits_sent = 0
        chunks_sent = 0
        flush_chunks_sent = 0

        async def send_audio() -> None:
            nonlocal chunks_sent, commits_sent, flush_chunks_sent, transcript_commits
            chunks_since_commit = 0
            try:
                for offset in range(0, len(pcm), chunk_size):
                    chunk = pcm[offset : offset + chunk_size]
                    await asyncio.wait_for(
                        websocket.send(
                            json.dumps(
                                {
                                    "type": "input_audio_buffer.append",
                                    "event_id": str(uuid.uuid4()),
                                    "audio": base64.b64encode(chunk).decode("ascii"),
                                },
                                separators=(",", ":"),
                            )
                        ),
                        timeout=timeout_seconds,
                    )
                    chunks_sent += 1
                    chunks_since_commit += 1
                    if pace_realtime:
                        await asyncio.sleep(len(chunk) / (24_000 * 2))
                    if chunks_since_commit >= chunks_per_commit:
                        transcript_commits += 1
                        commits_sent += 1
                        await asyncio.wait_for(
                            websocket.send(
                                json.dumps(
                                    {
                                        "type": "input_audio_buffer.commit",
                                        "event_id": str(uuid.uuid4()),
                                    },
                                    separators=(",", ":"),
                                )
                            ),
                            timeout=timeout_seconds,
                        )
                        chunks_since_commit = 0
                if chunks_since_commit:
                    transcript_commits += 1
                    commits_sent += 1
                    await asyncio.wait_for(
                        websocket.send(
                            json.dumps(
                                {
                                    "type": "input_audio_buffer.commit",
                                    "event_id": str(uuid.uuid4()),
                                },
                                separators=(",", ":"),
                            )
                        ),
                        timeout=timeout_seconds,
                    )
                flush_bytes = b"\x00" * (flush_silence_ms * 24_000 * 2 // 1000)
                for offset in range(0, len(flush_bytes), chunk_size):
                    chunk = flush_bytes[offset : offset + chunk_size]
                    await asyncio.wait_for(
                        websocket.send(
                            json.dumps(
                                {
                                    "type": "input_audio_buffer.append",
                                    "event_id": str(uuid.uuid4()),
                                    "audio": base64.b64encode(chunk).decode("ascii"),
                                },
                                separators=(",", ":"),
                            )
                        ),
                        timeout=timeout_seconds,
                    )
                    flush_chunks_sent += 1
                    if pace_realtime:
                        await asyncio.sleep(len(chunk) / (24_000 * 2))
                commits_sent += 1
                await asyncio.wait_for(
                    websocket.send(
                        json.dumps(
                            {
                                "type": "input_audio_buffer.commit",
                                "event_id": str(uuid.uuid4()),
                            },
                            separators=(",", ":"),
                        )
                    ),
                    timeout=timeout_seconds,
                )
            finally:
                sender_done.set()

        usage_by_item: dict[str, object] = {}
        compatibility_fallback_used = False

        async def receive_transcripts() -> tuple[list[str], list[str]]:
            nonlocal first_text_ms
            nonlocal compatibility_fallback_used
            commit_order: list[str] = []
            canonical_parts: dict[str, str] = {}
            compatibility_by_item: dict[str, str] = {}
            compatibility_parts: list[str] = []
            delta_parts: dict[str, list[str]] = {}

            def ordered_result() -> tuple[list[str], list[str]] | None:
                nonlocal compatibility_fallback_used
                if not sender_done.is_set() or len(commit_order) < transcript_commits:
                    return None
                source_item_order = commit_order[:transcript_commits]

                selected: list[str | None] = []
                unresolved_indexes: list[int] = []
                used_item_fallback = False
                for item_id in source_item_order:
                    if item_id in canonical_parts:
                        selected.append(canonical_parts[item_id])
                    elif item_id in compatibility_by_item:
                        selected.append(compatibility_by_item[item_id])
                        used_item_fallback = True
                    else:
                        unresolved_indexes.append(len(selected))
                        selected.append(None)

                if not unresolved_indexes:
                    compatibility_fallback_used = (
                        compatibility_fallback_used or used_item_fallback
                    )
                    return [part for part in selected if part is not None], source_item_order

                # Some preview protocol revisions emit only unbound response.*.done
                # events. If they form a complete stream, use that stream instead of
                # mixing it with canonical item events whose relationship is ambiguous.
                if len(compatibility_parts) >= transcript_commits:
                    compatibility_fallback_used = True
                    return compatibility_parts[:transcript_commits], source_item_order

                # A mixed stream can also contain canonical/by-item results for some
                # commits and one unbound compatibility result for every unresolved
                # commit. Bind those results deterministically in source commit order.
                if len(compatibility_parts) == len(unresolved_indexes):
                    for index, part in zip(unresolved_indexes, compatibility_parts, strict=True):
                        selected[index] = part
                    compatibility_fallback_used = True
                    return [part for part in selected if part is not None], source_item_order
                return None

            while True:
                ready = ordered_result()
                if ready is not None:
                    return ready
                event = await _recv_event(websocket, timeout_seconds)
                record(event)
                event_type = str(event["type"])
                if event_type == "input_audio_buffer.committed":
                    item_id = event.get("item_id")
                    if not isinstance(item_id, str) or not item_id:
                        raise AzureVoiceError(
                            "Azure input_audio_buffer.committed event has no item_id"
                        )
                    if item_id in commit_order:
                        raise AzureVoiceError("Azure returned a duplicate committed item_id")
                    commit_order.append(item_id)
                elif event_type in {
                    "conversation.item.input_audio_transcription.delta",
                    "response.output_text.delta",
                }:
                    delta = event.get("delta")
                    if isinstance(delta, str):
                        item_key = str(event.get("item_id") or f"unbound-{len(commit_order) + 1}")
                        delta_parts.setdefault(item_key, []).append(delta)
                        if sum(len(part) for values in delta_parts.values() for part in values) > (
                            MAX_TRANSCRIPT_CHARS
                        ):
                            raise AzureVoiceError("Azure transcript exceeded the size limit")
                        if first_text_ms is None and delta.strip():
                            first_text_ms = trace[-1]["offset_ms"]  # type: ignore[assignment]
                elif event_type == "conversation.item.input_audio_transcription.completed":
                    item_id = event.get("item_id")
                    if not isinstance(item_id, str) or not item_id:
                        raise AzureVoiceError("Azure transcription completion has no item_id")
                    final = event.get("text") or event.get("transcript")
                    if isinstance(final, str):
                        part = final
                    else:
                        part = "".join(delta_parts.get(item_id, []))
                    if item_id not in canonical_parts:
                        canonical_parts[item_id] = part
                        usage = numeric_usage(event.get("usage"))
                        if usage is not None:
                            usage_by_item[item_id] = usage
                    if sum(map(len, canonical_parts.values())) > MAX_TRANSCRIPT_CHARS:
                        raise AzureVoiceError("Azure transcript exceeded the size limit")
                    if first_text_ms is None and part.strip():
                        first_text_ms = trace[-1]["offset_ms"]  # type: ignore[assignment]
                elif event_type in {"response.output_text.done", "response.text.done"}:
                    final = event.get("text") or event.get("transcript")
                    part = final if isinstance(final, str) else ""
                    item_id = event.get("item_id")
                    if isinstance(item_id, str) and item_id:
                        if item_id not in canonical_parts:
                            compatibility_by_item.setdefault(item_id, part)
                    else:
                        compatibility_parts.append(part)
                    compatibility_chars = sum(map(len, compatibility_by_item.values())) + sum(
                        map(len, compatibility_parts)
                    )
                    if compatibility_chars > MAX_TRANSCRIPT_CHARS:
                        raise AzureVoiceError("Azure transcript exceeded the size limit")
                    if first_text_ms is None and part.strip():
                        first_text_ms = trace[-1]["offset_ms"]  # type: ignore[assignment]
                elif event_type == "conversation.item.input_audio_transcription.failed":
                    raise AzureVoiceError("Azure transcription reported a failed audio item")

        sender_task = asyncio.create_task(send_audio())
        receiver_task = asyncio.create_task(receive_transcripts())
        try:
            _, received = await asyncio.gather(sender_task, receiver_task)
        except BaseException:
            sender_task.cancel()
            receiver_task.cancel()
            await asyncio.gather(sender_task, receiver_task, return_exceptions=True)
            raise
        final_parts, source_item_order = received
        transcript = " ".join(final_parts)
        if not transcript.strip():
            raise AzureVoiceError("Azure transcription completed without text")
        source_usage = [
            usage_by_item[item_id]
            for item_id in source_item_order
            if item_id in usage_by_item
        ]
        total_ms = round((time.monotonic() - started) * 1000)
        return TranscriptionResult(
            transcript=transcript,
            segments=tuple(final_parts),
            input_info=input_info,
            input_pcm_sha256=input_pcm_sha256,
            input_pcm_bytes=input_pcm_bytes,
            requested_session=session,
            effective_session=effective_session or {},
            event_counts=dict(sorted(counts.items())),
            event_trace=tuple(trace),
            timings_ms={
                "session_created": session_created_ms,
                "session_updated": session_updated_ms,
                "first_text": first_text_ms,
                "total": total_ms,
            },
            chunks_sent=chunks_sent,
            commits_sent=commits_sent,
            transcript_commits=transcript_commits,
            flush_chunks_sent=flush_chunks_sent,
            flush_silence_ms=flush_silence_ms,
            # The trailing-silence flush is transport context, not source audio.
            # Aggregate only source-commit usage so event arrival order cannot
            # nondeterministically add or omit flush usage.
            usage=aggregate_numeric_usage(source_usage),
            provider_model=provider_model,
            compatibility_fallback_used=compatibility_fallback_used,
            unconfirmed_session_fields=unconfirmed_session_fields,
        )
