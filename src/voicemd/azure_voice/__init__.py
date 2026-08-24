"""Azure OpenAI audio and realtime proof adapters for VoiceMD."""

from .audio import AudioCompletionResult, create_audio_completion
from .common import (
    AzureConnection,
    VoiceBinding,
    bind_voice_contract,
    load_azure_connection,
    load_env_file,
)
from .realtime import RealtimeResult, run_realtime_text_turn
from .transcribe import TranscriptionResult, transcribe_wav

__all__ = [
    "AudioCompletionResult",
    "AzureConnection",
    "RealtimeResult",
    "TranscriptionResult",
    "VoiceBinding",
    "bind_voice_contract",
    "create_audio_completion",
    "load_azure_connection",
    "load_env_file",
    "run_realtime_text_turn",
    "transcribe_wav",
]
