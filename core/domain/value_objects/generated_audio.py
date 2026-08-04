"""
GeneratedAudio — the raw output of a VoiceGeneratorPort adapter call.

Deliberately distinct from the VoiceTrack entity: this object carries only
what a TTS provider itself produces (audio bytes + provider-reported
metadata). It knows nothing about persistence. VoiceService is responsible
for saving the bytes via StoragePort and building the final VoiceTrack
entity, which adds the identity and file_path fields. Keeping this
separation means a provider adapter never needs to know how or where audio
gets stored.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from core.domain.value_objects.speech_segment import SpeechSegment


@dataclass(frozen=True)
class GeneratedAudio:
    audio_bytes: bytes
    duration_seconds: float
    sample_rate: int
    provider: str
    voice_name: str
    # Optional speech timing (Sprint 2.1). Empty when the provider adapter
    # doesn't supply timing data — this is a valid, expected state, not an
    # error. See ElevenLabsVoiceProvider's docstring for how a
    # timing-capable adapter would populate this.
    segments: list[SpeechSegment] = field(default_factory=list)
