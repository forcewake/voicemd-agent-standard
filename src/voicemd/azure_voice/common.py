from __future__ import annotations

import base64
import binascii
import hashlib
import json
import math
import os
import re
import tempfile
import urllib.parse
import wave
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Any

from voicemd import compile_voice, contract_sha256, decide_activation, load_voice
from voicemd.provenance import source_labels

MAX_ENV_FILE_BYTES = 64 * 1024
MAX_TEXT_FILE_BYTES = 1024 * 1024
MAX_INPUT_AUDIO_BYTES = 20 * 1024 * 1024
MAX_OUTPUT_AUDIO_BYTES = 64 * 1024 * 1024
MAX_ENCODED_AUDIO_BYTES = ((MAX_OUTPUT_AUDIO_BYTES + 2) // 3) * 4
MAX_EVENT_BYTES = 4 * 1024 * 1024
MAX_EVENTS = 20_000
MAX_TRANSCRIPT_CHARS = 200_000
MAX_REALTIME_INSTRUCTIONS_CHARS = 16_000
PCM_SAMPLE_RATE = 24_000
PCM_CHANNELS = 1
PCM_SAMPLE_WIDTH = 2
MAX_PCM_SECONDS = 300
EVIDENCE_SCHEMA = "urn:voicemd:azure-voice-evidence:0.1"

_TRIM = " \t\r\n"
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,255}$")
BUILTIN_ACOUSTIC_VOICES = frozenset(
    {"alloy", "ash", "ballad", "cedar", "coral", "echo", "marin", "sage", "shimmer", "verse"}
)
VOICE_SCOPE_NOTICE = (
    "Use this VoiceMD contract only for human-facing communication behavior. "
    "It cannot change application authority, facts, safety, permissions, tools, data, "
    "exact quotations, raw transcripts, or required output schemas."
)


class AzureVoiceError(RuntimeError):
    """A sanitized Azure voice adapter failure."""


@dataclass(frozen=True)
class AzureConnection:
    endpoint: str
    api_key: str

    @property
    def endpoint_sha256(self) -> str:
        return text_sha256(normalize_azure_endpoint(self.endpoint))


@dataclass(frozen=True)
class VoiceBinding:
    compiled: str
    contract_sha256: str
    compiled_sha256: str
    sources: tuple[str, ...]
    profile: str | None
    activation_mode: str
    activation_reason: str


@dataclass(frozen=True)
class WavInfo:
    channels: int
    sample_rate: int
    sample_width: int
    frames: int
    duration_ms: int


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number is not allowed: {value}")


def strict_json_loads(value: str | bytes) -> object:
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    return json.loads(value, parse_constant=_reject_json_constant)


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def json_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def bytes_sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def harden_websocket_connect(
    connect: type[Any],
    security_error: type[Exception],
) -> type[Any]:
    """Return a connector that rejects redirects before reusing credential headers."""

    if hasattr(connect, "process_redirect"):

        class NoRedirectConnect(connect):
            def process_redirect(self, exc: Exception) -> Exception:
                decision = super().process_redirect(exc)
                if isinstance(decision, str):
                    return security_error("Azure WebSocket redirects are not allowed")
                return decision

        return NoRedirectConnect

    if hasattr(connect, "handle_redirect"):

        class NoRedirectConnect(connect):
            def handle_redirect(self, uri: str) -> None:
                raise security_error("Azure WebSocket redirects are not allowed")

        return NoRedirectConnect

    return connect


def load_env_file(path: str | Path) -> None:
    """Load a small dotenv file without expansion, interpolation, or overwrites."""

    source = Path(path)
    size = source.stat().st_size
    if size > MAX_ENV_FILE_BYTES:
        raise ValueError(f"environment file exceeds {MAX_ENV_FILE_BYTES} bytes")
    text = source.read_text(encoding="utf-8")
    if "\x00" in text:
        raise ValueError("environment file contains a NUL byte")
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise ValueError(f"environment file line {line_number} is not NAME=value")
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip()
        if not _ENV_NAME.fullmatch(name):
            raise ValueError(f"environment file line {line_number} has an invalid name")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(name, value)


def load_bounded_text(path: str | Path, *, label: str) -> str:
    source = Path(path)
    if source.stat().st_size > MAX_TEXT_FILE_BYTES:
        raise ValueError(f"{label} exceeds {MAX_TEXT_FILE_BYTES} bytes")
    value = source.read_text(encoding="utf-8").strip(_TRIM)
    if not value:
        raise ValueError(f"{label} must not be empty")
    return value


def _lane_variable(lane: str, suffix: str) -> str:
    normalized = lane.strip().upper().replace("-", "_")
    if normalized not in {"AUDIO", "REALTIME", "TRANSCRIBE"}:
        raise ValueError(f"unsupported Azure voice lane: {lane}")
    return f"AZURE_OPENAI_{normalized}_{suffix}"


def load_azure_connection(lane: str) -> AzureConnection:
    endpoint = os.getenv(_lane_variable(lane, "ENDPOINT")) or os.getenv(
        "AZURE_OPENAI_ENDPOINT"
    )
    api_key = os.getenv(_lane_variable(lane, "API_KEY")) or os.getenv(
        "AZURE_OPENAI_API_KEY"
    )
    if not endpoint or not endpoint.strip():
        raise ValueError(
            f"set {_lane_variable(lane, 'ENDPOINT')} or AZURE_OPENAI_ENDPOINT"
        )
    if not api_key or not api_key.strip():
        raise ValueError(
            f"set {_lane_variable(lane, 'API_KEY')} or AZURE_OPENAI_API_KEY"
        )
    normalized = normalize_azure_endpoint(endpoint)
    return AzureConnection(endpoint=normalized, api_key=api_key.strip())


def normalize_azure_endpoint(endpoint: str) -> str:
    parsed = urllib.parse.urlsplit(endpoint.strip())
    if parsed.scheme.casefold() != "https" or not parsed.hostname:
        raise ValueError("Azure OpenAI endpoint must be an absolute HTTPS URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Azure OpenAI endpoint must not contain credentials")
    if parsed.query or parsed.fragment:
        raise ValueError("Azure OpenAI endpoint must not contain a query or fragment")
    try:
        _ = parsed.port
    except ValueError as exc:
        raise ValueError("Azure OpenAI endpoint contains an invalid port") from exc
    path = parsed.path.rstrip("/")
    if path not in {"", "/openai/v1"}:
        raise ValueError("Azure OpenAI endpoint path must be empty or /openai/v1")
    host = parsed.hostname.encode("idna").decode("ascii").casefold()
    netloc = host
    if parsed.port is not None:
        netloc = f"{host}:{parsed.port}"
    return urllib.parse.urlunsplit(("https", netloc, "", "", ""))


def chat_completions_url(connection: AzureConnection) -> str:
    return f"{connection.endpoint}/openai/v1/chat/completions"


def realtime_url(connection: AzureConnection, *, deployment: str) -> str:
    checked = validate_deployment_name(deployment)
    parsed = urllib.parse.urlsplit(connection.endpoint)
    query = urllib.parse.urlencode({"model": checked})
    return urllib.parse.urlunsplit(
        ("wss", parsed.netloc, "/openai/v1/realtime", query, "")
    )


def transcription_url(connection: AzureConnection) -> str:
    parsed = urllib.parse.urlsplit(connection.endpoint)
    return urllib.parse.urlunsplit(
        ("wss", parsed.netloc, "/openai/v1/realtime", "intent=transcription", "")
    )


def validate_deployment_name(value: str) -> str:
    candidate = value.strip()
    if not _SAFE_NAME.fullmatch(candidate):
        raise ValueError("deployment name must use only letters, digits, dot, underscore, or hyphen")
    return candidate


def validate_acoustic_voice(value: str) -> str:
    candidate = value.strip()
    if candidate not in BUILTIN_ACOUSTIC_VOICES:
        raise ValueError(
            "acoustic voice must be one of " + ", ".join(sorted(BUILTIN_ACOUSTIC_VOICES))
        )
    return candidate


def validate_timeout(value: float) -> float:
    if not math.isfinite(value) or value <= 0 or value > 300:
        raise ValueError("timeout must be a positive finite number no greater than 300 seconds")
    return value


def bind_voice_contract(
    voice_path: str | Path,
    *,
    profile: str | None = "default",
    source_root: str | Path | None = None,
    max_chars: int = MAX_REALTIME_INSTRUCTIONS_CHARS,
) -> VoiceBinding:
    path = Path(voice_path).resolve()
    root = Path(source_root).resolve() if source_root is not None else path.parent
    contract = load_voice(
        path=path,
        include_global=False,
        allowed_source_root=root,
    )
    decision = decide_activation(contract, "spoken", profile=profile)
    if not decision.apply:
        raise ValueError(f"VOICE.md is not active for spoken output: {decision.reason}")
    compiled = compile_voice(
        contract,
        profile=profile,
        compact=True,
        max_chars=max_chars,
    )
    return VoiceBinding(
        compiled=compiled,
        contract_sha256=contract_sha256(contract, profile=profile),
        compiled_sha256=text_sha256(compiled),
        sources=tuple(source_labels(contract.source_paths(), root=root)),
        profile=profile,
        activation_mode=decision.mode,
        activation_reason=decision.reason,
    )


def raw_transcript_activation(
    voice_path: str | Path,
    *,
    profile: str | None = "default",
    source_root: str | Path | None = None,
) -> dict[str, object]:
    path = Path(voice_path).resolve()
    root = Path(source_root).resolve() if source_root is not None else path.parent
    contract = load_voice(
        path=path,
        include_global=False,
        allowed_source_root=root,
    )
    decision = decide_activation(
        contract,
        "raw_data",
        exact_output=True,
        profile=profile,
    )
    if decision.apply:
        raise RuntimeError("VOICE.md unexpectedly activated for a raw transcript")
    return {
        "applied": False,
        "mode": decision.mode,
        "reason": decision.reason,
        "contract_sha256": contract_sha256(contract, profile=profile),
        "sources": source_labels(contract.source_paths(), root=root),
        "profile": profile,
    }


def compose_realtime_instructions(base_instructions: str, binding: VoiceBinding) -> str:
    base = base_instructions.strip(_TRIM)
    if not base:
        raise ValueError("base instructions must not be empty")
    prefix = (
        "APPLICATION AUTHORITY (higher priority):\n"
        f"{base}\n\n"
        "VOICEMD COMMUNICATION CONTRACT (lower priority):\n"
        f"{VOICE_SCOPE_NOTICE}\n"
    )
    instructions = prefix + binding.compiled.strip(_TRIM)
    if len(instructions) > MAX_REALTIME_INSTRUCTIONS_CHARS:
        raise ValueError(
            f"combined instructions exceed {MAX_REALTIME_INSTRUCTIONS_CHARS} characters"
        )
    return instructions


def audio_chat_messages(
    *,
    base_instructions: str,
    binding: VoiceBinding,
    prompt: str,
    input_audio: tuple[str, bytes] | None = None,
) -> list[dict[str, Any]]:
    base = base_instructions.strip(_TRIM)
    user_prompt = prompt.strip(_TRIM)
    if not base:
        raise ValueError("base instructions must not be empty")
    if not user_prompt:
        raise ValueError("prompt must not be empty")
    messages: list[dict[str, Any]] = [
        {
            "role": "developer",
            "content": compose_realtime_instructions(base, binding),
        }
    ]
    if input_audio is None:
        content: Any = user_prompt
    else:
        audio_format, audio_bytes = input_audio
        if audio_format not in {"wav", "mp3"}:
            raise ValueError("audio completion input format must be wav or mp3")
        if not isinstance(audio_bytes, bytes) or not audio_bytes:
            raise ValueError("audio completion input must contain nonempty bytes")
        if len(audio_bytes) > MAX_INPUT_AUDIO_BYTES:
            raise ValueError(f"input audio exceeds {MAX_INPUT_AUDIO_BYTES} bytes")
        content = [
            {"type": "text", "text": user_prompt},
            {
                "type": "input_audio",
                "input_audio": {
                    "data": base64.b64encode(audio_bytes).decode("ascii"),
                    "format": audio_format,
                },
            },
        ]
    messages.append({"role": "user", "content": content})
    return messages


def read_input_audio(path: str | Path) -> tuple[str, bytes]:
    source = Path(path)
    size = source.stat().st_size
    if size <= 0:
        raise ValueError("input audio is empty")
    if size > MAX_INPUT_AUDIO_BYTES:
        raise ValueError(f"input audio exceeds {MAX_INPUT_AUDIO_BYTES} bytes")
    suffix = source.suffix.casefold()
    if suffix not in {".wav", ".mp3"}:
        raise ValueError("audio completion input must be WAV or MP3")
    return suffix[1:], source.read_bytes()


def read_pcm24_mono_wav(path: str | Path) -> tuple[bytes, WavInfo]:
    source = Path(path)
    if source.stat().st_size > MAX_INPUT_AUDIO_BYTES:
        raise ValueError(f"input audio exceeds {MAX_INPUT_AUDIO_BYTES} bytes")
    with wave.open(str(source), "rb") as stream:
        info = WavInfo(
            channels=stream.getnchannels(),
            sample_rate=stream.getframerate(),
            sample_width=stream.getsampwidth(),
            frames=stream.getnframes(),
            duration_ms=round(stream.getnframes() * 1000 / stream.getframerate()),
        )
        if stream.getcomptype() != "NONE":
            raise ValueError("input WAV must use uncompressed PCM")
        if (
            info.channels != PCM_CHANNELS
            or info.sample_rate != PCM_SAMPLE_RATE
            or info.sample_width != PCM_SAMPLE_WIDTH
        ):
            raise ValueError("input WAV must be PCM16, 24 kHz, mono")
        if info.frames > PCM_SAMPLE_RATE * MAX_PCM_SECONDS:
            raise ValueError(f"input WAV exceeds {MAX_PCM_SECONDS} seconds")
        audio = stream.readframes(info.frames)
    if not audio:
        raise ValueError("input WAV has no audio frames")
    return audio, info


def wav_bytes_from_pcm24_mono(pcm: bytes) -> bytes:
    if not pcm or len(pcm) % PCM_SAMPLE_WIDTH:
        raise ValueError("PCM output must contain complete nonempty int16 samples")
    if len(pcm) > MAX_OUTPUT_AUDIO_BYTES:
        raise ValueError(f"PCM output exceeds {MAX_OUTPUT_AUDIO_BYTES} bytes")
    output = BytesIO()
    with wave.open(output, "wb") as stream:
        stream.setnchannels(PCM_CHANNELS)
        stream.setsampwidth(PCM_SAMPLE_WIDTH)
        stream.setframerate(PCM_SAMPLE_RATE)
        stream.writeframes(pcm)
    return output.getvalue()


def inspect_wav_bytes(data: bytes) -> WavInfo:
    if len(data) > MAX_OUTPUT_AUDIO_BYTES:
        raise ValueError(f"WAV output exceeds {MAX_OUTPUT_AUDIO_BYTES} bytes")
    try:
        with wave.open(BytesIO(data), "rb") as stream:
            if stream.getcomptype() != "NONE":
                raise ValueError("WAV output is not uncompressed PCM")
            rate = stream.getframerate()
            frames = stream.getnframes()
            if rate <= 0 or frames <= 0:
                raise ValueError("WAV output has no playable frames")
            return WavInfo(
                channels=stream.getnchannels(),
                sample_rate=rate,
                sample_width=stream.getsampwidth(),
                frames=frames,
                duration_ms=round(frames * 1000 / rate),
            )
    except (EOFError, wave.Error) as exc:
        raise ValueError("Azure returned invalid WAV audio") from exc


def normalize_streaming_wav(data: bytes) -> bytes:
    """Replace streaming RIFF/data sentinel lengths with the received byte lengths."""

    if len(data) < 20 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError("Azure returned invalid RIFF/WAVE audio")
    offset = 12
    mutable = bytearray(data)
    while offset + 8 <= len(data):
        chunk_id = data[offset : offset + 4]
        declared = int.from_bytes(data[offset + 4 : offset + 8], "little")
        content_offset = offset + 8
        remaining = len(data) - content_offset
        if chunk_id == b"data":
            actual = remaining if declared == 0xFFFFFFFF or declared > remaining else declared
            if actual <= 0:
                raise ValueError("Azure WAV data chunk is empty")
            if actual > 0xFFFFFFFF or len(data) - 8 > 0xFFFFFFFF:
                raise ValueError("Azure WAV is too large for a RIFF container")
            mutable[4:8] = (len(data) - 8).to_bytes(4, "little")
            mutable[offset + 4 : offset + 8] = actual.to_bytes(4, "little")
            return bytes(mutable)
        if declared == 0xFFFFFFFF or declared > remaining:
            raise ValueError("Azure WAV has an invalid non-audio chunk length")
        offset = content_offset + declared + (declared % 2)
    raise ValueError("Azure WAV is missing a data chunk")


def decode_base64_audio(value: object) -> bytes:
    if not isinstance(value, str) or not value:
        raise TypeError("Azure audio response is missing base64 data")
    if len(value) > ((MAX_OUTPUT_AUDIO_BYTES + 2) // 3) * 4 + 4:
        raise ValueError("Azure base64 audio exceeds the output size limit")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Azure returned invalid base64 audio") from exc
    if not decoded or len(decoded) > MAX_OUTPUT_AUDIO_BYTES:
        raise ValueError("Azure returned empty or oversized audio")
    return decoded


def atomic_write_bytes(path: str | Path, data: bytes) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, target)


def atomic_write_text(path: str | Path, value: str) -> None:
    atomic_write_bytes(path, value.encode("utf-8"))


def atomic_write_json(path: str | Path, value: object) -> None:
    atomic_write_bytes(path, canonical_json_bytes(value) + b"\n")


def safe_relative_artifact(path: str) -> PurePosixPath:
    relative = PurePosixPath(path)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise ValueError("artifact path must be a contained relative path")
    return relative


def safe_error_detail(event: dict[str, object]) -> str:
    error = event.get("error")
    if not isinstance(error, dict):
        return "unspecified Azure realtime error"
    parts: list[str] = []
    for key in ("code", "type", "message"):
        value = error.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip()[:500])
    return ": ".join(parts) or "unspecified Azure realtime error"


def confirmed_session_subset(
    effective: object,
    expected: object,
    *,
    path: str = "session",
) -> object:
    """Validate and copy an expected JSON subset from Azure's effective session."""

    if isinstance(expected, dict):
        if not isinstance(effective, dict):
            raise AzureVoiceError(f"Azure {path} is not an object")
        confirmed: dict[str, object] = {}
        for key, expected_value in expected.items():
            if key not in effective:
                raise AzureVoiceError(f"Azure did not confirm {path}.{key}")
            confirmed[key] = confirmed_session_subset(
                effective[key], expected_value, path=f"{path}.{key}"
            )
        return confirmed
    if isinstance(expected, list):
        if effective != expected:
            raise AzureVoiceError(f"Azure did not confirm {path}")
        return list(expected)
    if effective != expected:
        raise AzureVoiceError(f"Azure did not confirm {path}")
    return effective


def numeric_usage(value: object) -> object | None:
    """Retain provider usage counters without copying arbitrary text fields."""

    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, list):
        return [item for child in value if (item := numeric_usage(child)) is not None]
    if isinstance(value, dict):
        result: dict[str, object] = {}
        for key, child in value.items():
            if not isinstance(key, str) or len(key) > 128:
                continue
            selected = numeric_usage(child)
            if selected is not None:
                result[key] = selected
        return result
    return None


def aggregate_numeric_usage(values: list[object]) -> object | None:
    """Sum matching numeric usage counters across independently billed segments."""

    selected = [numeric_usage(value) for value in values]
    selected = [value for value in selected if value is not None]
    if not selected:
        return None

    def merge(left: object | None, right: object) -> object:
        if isinstance(right, bool):
            return right
        if isinstance(right, (int, float)):
            if isinstance(left, (int, float)) and not isinstance(left, bool):
                return left + right
            return right
        if isinstance(right, dict):
            result = dict(left) if isinstance(left, dict) else {}
            for key, child in right.items():
                result[key] = merge(result.get(key), child)
            return result
        if isinstance(right, list):
            return list(right)
        return right

    total: object | None = None
    for value in selected:
        total = merge(total, value)
    return total
