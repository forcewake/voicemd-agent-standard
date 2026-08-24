from __future__ import annotations

import asyncio
import inspect
import json
import time
import uuid
from collections import Counter
from dataclasses import dataclass

from .common import (
    MAX_EVENTS,
    MAX_OUTPUT_AUDIO_BYTES,
    MAX_TRANSCRIPT_CHARS,
    AzureConnection,
    AzureVoiceError,
    VoiceBinding,
    compose_realtime_instructions,
    confirmed_session_subset,
    decode_base64_audio,
    harden_websocket_connect,
    numeric_usage,
    realtime_url,
    safe_error_detail,
    strict_json_loads,
    validate_acoustic_voice,
    validate_deployment_name,
    validate_timeout,
)


@dataclass(frozen=True)
class RealtimeResult:
    audio_pcm: bytes
    transcript: str
    requested_session: dict[str, object]
    effective_session: dict[str, object]
    event_counts: dict[str, int]
    event_trace: tuple[dict[str, object], ...]
    timings_ms: dict[str, int | None]
    usage: object | None
    provider_model: str | None


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
                "Azure realtime support requires: pip install 'voicemd[azure-voice]'"
            ) from exc
    return harden_websocket_connect(connect, SecurityError)


def _extract_final_transcript(event: dict[str, object]) -> str | None:
    response = event.get("response")
    if not isinstance(response, dict):
        return None
    output = response.get("output")
    if not isinstance(output, list):
        return None
    chunks: list[str] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict):
                continue
            value = part.get("transcript") or part.get("text")
            if isinstance(value, str):
                chunks.append(value)
    return "".join(chunks).strip() or None


async def _recv_event(websocket: object, timeout_seconds: float) -> dict[str, object]:
    try:
        raw = await asyncio.wait_for(websocket.recv(), timeout=timeout_seconds)
    except asyncio.TimeoutError as exc:
        raise AzureVoiceError("timed out waiting for an Azure realtime event") from exc
    event = strict_json_loads(raw)
    if not isinstance(event, dict) or not isinstance(event.get("type"), str):
        raise TypeError("Azure realtime event must have a string type")
    if event["type"] == "error":
        raise AzureVoiceError(f"Azure realtime error: {safe_error_detail(event)}")
    return event


async def run_realtime_text_turn(
    connection: AzureConnection,
    *,
    deployment: str,
    base_instructions: str,
    binding: VoiceBinding,
    prompt: str,
    acoustic_voice: str = "alloy",
    timeout_seconds: float = 90.0,
) -> RealtimeResult:
    deployment = validate_deployment_name(deployment)
    acoustic_voice = validate_acoustic_voice(acoustic_voice)
    timeout_seconds = validate_timeout(timeout_seconds)
    user_prompt = prompt.strip()
    if not user_prompt:
        raise ValueError("prompt must not be empty")
    instructions = compose_realtime_instructions(base_instructions, binding)
    session: dict[str, object] = {
        "type": "realtime",
        "instructions": instructions,
        "output_modalities": ["audio"],
        "audio": {
            "input": {
                "format": {"type": "audio/pcm", "rate": 24_000},
                "turn_detection": None,
            },
            "output": {
                "voice": acoustic_voice,
                "format": {"type": "audio/pcm", "rate": 24_000},
            },
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
    audio = bytearray()
    transcript_parts: list[str] = []
    transcript_chars = 0
    first_audio_ms: int | None = None
    first_transcript_ms: int | None = None
    session_created_ms: int | None = None
    session_updated_ms: int | None = None
    usage: object | None = None
    provider_model: str | None = None
    effective_session: dict[str, object] | None = None

    def record(event: dict[str, object], *, audio_bytes: int | None = None) -> None:
        event_type = str(event["type"])
        counts[event_type] += 1
        entry: dict[str, object] = {
            "offset_ms": round((time.monotonic() - started) * 1000),
            "type": event_type,
        }
        if audio_bytes is not None:
            entry["audio_bytes"] = audio_bytes
        trace.append(entry)
        if len(trace) > MAX_EVENTS:
            raise AzureVoiceError(f"Azure realtime session exceeded {MAX_EVENTS} events")

    async with connect(realtime_url(connection, deployment=deployment), **kwargs) as websocket:
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
            if updated["type"] != "session.updated":
                continue
            effective = updated.get("session")
            confirmed = confirmed_session_subset(effective, session)
            if not isinstance(confirmed, dict):
                raise AzureVoiceError("Azure returned an invalid effective realtime session")
            effective_session = confirmed
            if isinstance(effective, dict) and isinstance(effective.get("model"), str):
                provider_model = effective["model"]
            session_updated_ms = trace[-1]["offset_ms"]  # type: ignore[assignment]
            break
        await asyncio.wait_for(
            websocket.send(
                json.dumps(
                    {
                        "type": "conversation.item.create",
                        "event_id": str(uuid.uuid4()),
                        "item": {
                            "type": "message",
                            "role": "user",
                            "content": [{"type": "input_text", "text": user_prompt}],
                        },
                    },
                    ensure_ascii=False,
                    allow_nan=False,
                    separators=(",", ":"),
                )
            ),
            timeout=timeout_seconds,
        )
        await asyncio.wait_for(
            websocket.send(json.dumps({"type": "response.create"})),
            timeout=timeout_seconds,
        )
        while True:
            event = await _recv_event(websocket, timeout_seconds)
            event_type = str(event["type"])
            if event_type == "response.output_audio.delta":
                chunk = decode_base64_audio(event.get("delta"))
                if len(audio) + len(chunk) > MAX_OUTPUT_AUDIO_BYTES:
                    raise AzureVoiceError("Azure realtime audio exceeded the output size limit")
                audio.extend(chunk)
                record(event, audio_bytes=len(chunk))
                if first_audio_ms is None:
                    first_audio_ms = trace[-1]["offset_ms"]  # type: ignore[assignment]
                continue
            record(event)
            if event_type in {
                "response.output_audio_transcript.delta",
                "response.output_text.delta",
            }:
                delta = event.get("delta")
                if not isinstance(delta, str):
                    raise TypeError(f"{event_type} is missing a string delta")
                transcript_chars += len(delta)
                if transcript_chars > MAX_TRANSCRIPT_CHARS:
                    raise AzureVoiceError("Azure realtime transcript exceeded the size limit")
                transcript_parts.append(delta)
                if first_transcript_ms is None:
                    first_transcript_ms = trace[-1]["offset_ms"]  # type: ignore[assignment]
            elif event_type == "response.done":
                response = event.get("response")
                if isinstance(response, dict):
                    status = response.get("status")
                    if isinstance(status, str) and status not in {"completed", "succeeded"}:
                        raise AzureVoiceError(f"Azure realtime response ended with status {status}")
                    usage = numeric_usage(response.get("usage"))
                final = _extract_final_transcript(event)
                transcript = "".join(transcript_parts).strip()
                if final:
                    transcript = final
                if not transcript:
                    raise AzureVoiceError("Azure realtime response contained no transcript")
                if not audio:
                    raise AzureVoiceError("Azure realtime response contained no audio")
                total_ms = round((time.monotonic() - started) * 1000)
                return RealtimeResult(
                    audio_pcm=bytes(audio),
                    transcript=transcript,
                    requested_session=session,
                    effective_session=effective_session or {},
                    event_counts=dict(sorted(counts.items())),
                    event_trace=tuple(trace),
                    timings_ms={
                        "session_created": session_created_ms,
                        "session_updated": session_updated_ms,
                        "first_transcript": first_transcript_ms,
                        "first_audio": first_audio_ms,
                        "total": total_ms,
                    },
                    usage=usage,
                    provider_model=provider_model,
                )
