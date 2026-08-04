"""
VoiceTrack entity.

The persisted, final result of voice generation for one Script — what the
rest of the pipeline (video assembly, in a later sprint) actually consumes.
Plain dataclass, no framework dependency, same pattern as Script in Sprint 1.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from core.domain.value_objects.speech_segment import SpeechSegment


@dataclass(frozen=True)
class VoiceTrack:
    audio_id: str
    script_id: Optional[str]
    duration_seconds: float
    provider: str
    voice_name: str
    sample_rate: int
    file_path: str
    created_at: datetime
    # Optional speech timing (Sprint 2.1). Empty when the underlying
    # provider didn't supply timing data. See GeneratedAudio's docstring —
    # this field is carried straight through from there.
    segments: list[SpeechSegment] = field(default_factory=list)

    @staticmethod
    def create(
        *,
        script_id: Optional[str],
        duration_seconds: float,
        provider: str,
        voice_name: str,
        sample_rate: int,
        file_path: str,
        segments: Optional[list[SpeechSegment]] = None,
    ) -> "VoiceTrack":
        return VoiceTrack(
            audio_id=str(uuid.uuid4()),
            script_id=script_id,
            duration_seconds=duration_seconds,
            provider=provider,
            voice_name=voice_name,
            sample_rate=sample_rate,
            file_path=file_path,
            created_at=datetime.now(timezone.utc),
            segments=segments or [],
        )

    def to_dict(self) -> dict:
        """Export the shape a downstream consumer (e.g. a future
        SceneSplitterService) would want: audio file, total duration, and
        timed segments if available. Matches the "Speech Timeline" shape
        discussed for Sprint 3's scene planning."""
        return {
            "audio_id": self.audio_id,
            "audio_file": self.file_path,
            "duration": self.duration_seconds,
            "provider": self.provider,
            "voice_name": self.voice_name,
            "sample_rate": self.sample_rate,
            "segments": [
                {"text": s.text, "start": s.start, "end": s.end} for s in self.segments
            ],
        }
