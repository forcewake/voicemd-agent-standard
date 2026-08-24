from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from .common import (
    MAX_ENCODED_AUDIO_BYTES,
    MAX_EVENT_BYTES,
    AzureConnection,
    AzureVoiceError,
    VoiceBinding,
    WavInfo,
    audio_chat_messages,
    canonical_json_bytes,
    chat_completions_url,
    decode_base64_audio,
    inspect_wav_bytes,
    normalize_streaming_wav,
    numeric_usage,
    strict_json_loads,
    validate_acoustic_voice,
    validate_deployment_name,
    validate_timeout,
)


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(_NoRedirectHandler())


@dataclass(frozen=True)
class AudioCompletionResult:
    audio: bytes
    transcript: str
    wav_info: WavInfo
    total_ms: int
    usage: object | None
    request_body: dict[str, Any]
    provider_model: str | None


def _bounded_read(response: object, limit: int) -> bytes:
    raw = response.read(limit + 1)
    if len(raw) > limit:
        raise AzureVoiceError("Azure audio response exceeded the configured size limit")
    return raw


def _response_message(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise TypeError("Azure audio response must be a JSON object")
    choices = payload.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        raise TypeError("Azure audio response must contain exactly one choice")
    choice = choices[0]
    if not isinstance(choice, dict) or not isinstance(choice.get("message"), dict):
        raise TypeError("Azure audio response is missing choices[0].message")
    return choice["message"]


def create_audio_completion(
    connection: AzureConnection,
    *,
    deployment: str,
    base_instructions: str,
    binding: VoiceBinding,
    prompt: str,
    acoustic_voice: str = "alloy",
    input_audio: tuple[str, bytes] | None = None,
    timeout_seconds: float = 90.0,
) -> AudioCompletionResult:
    deployment = validate_deployment_name(deployment)
    acoustic_voice = validate_acoustic_voice(acoustic_voice)
    timeout_seconds = validate_timeout(timeout_seconds)
    messages = audio_chat_messages(
        base_instructions=base_instructions,
        binding=binding,
        prompt=prompt,
        input_audio=input_audio,
    )
    body: dict[str, Any] = {
        "model": deployment,
        "modalities": ["text", "audio"],
        "audio": {"voice": acoustic_voice, "format": "wav"},
        "messages": messages,
    }
    raw_body = canonical_json_bytes(body)
    if len(raw_body) > 32 * 1024 * 1024:
        raise ValueError("Azure audio request exceeds 32 MiB")
    request = urllib.request.Request(
        chat_completions_url(connection),
        data=raw_body,
        method="POST",
        headers={
            "api-key": connection.api_key,
            "content-type": "application/json",
            "accept": "application/json",
        },
    )
    started = time.monotonic()
    try:
        with _OPENER.open(request, timeout=timeout_seconds) as response:
            raw_response = _bounded_read(response, MAX_ENCODED_AUDIO_BYTES + MAX_EVENT_BYTES)
    except urllib.error.HTTPError as exc:
        try:
            detail_raw = exc.read(MAX_EVENT_BYTES + 1)
            detail_payload = strict_json_loads(detail_raw) if len(detail_raw) <= MAX_EVENT_BYTES else None
            detail = ""
            if isinstance(detail_payload, dict):
                error = detail_payload.get("error")
                if isinstance(error, dict) and isinstance(error.get("message"), str):
                    detail = f": {error['message'][:500]}"
        except (OSError, TypeError, UnicodeError, ValueError, json.JSONDecodeError):
            detail = ""
        raise AzureVoiceError(f"Azure audio request failed with HTTP {exc.code}{detail}") from None
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", None)
        reason_name = type(reason).__name__ if reason is not None else "transport error"
        raise AzureVoiceError(f"Azure audio transport failed: {reason_name}") from None
    total_ms = round((time.monotonic() - started) * 1000)
    payload = strict_json_loads(raw_response)
    message = _response_message(payload)
    audio = message.get("audio")
    if not isinstance(audio, dict):
        raise TypeError("Azure audio response is missing message.audio")
    transcript = audio.get("transcript")
    if not isinstance(transcript, str) or not transcript.strip():
        raise TypeError("Azure audio response is missing a transcript")
    decoded = normalize_streaming_wav(decode_base64_audio(audio.get("data")))
    wav_info = inspect_wav_bytes(decoded)
    usage = numeric_usage(payload.get("usage")) if isinstance(payload, dict) else None
    provider_model = payload.get("model") if isinstance(payload, dict) else None
    if not isinstance(provider_model, str):
        provider_model = None
    return AudioCompletionResult(
        audio=decoded,
        transcript=transcript,
        wav_info=wav_info,
        total_ms=total_ms,
        usage=usage,
        request_body=body,
        provider_model=provider_model,
    )
