import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from core.domain.value_objects.subtitle_cue import SubtitleCue


@dataclass(frozen=True)
class TranslatedSubtitleTrack:
    id: str
    source_subtitle_track_id: str
    target_language: str
    cues: list[SubtitleCue]
    total_duration_seconds: float
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source_subtitle_track_id": self.source_subtitle_track_id,
            "target_language": self.target_language,
            "cues": [
                {
                    "index": cue.index,
                    "scene_index": cue.scene_index,
                    "start_time": cue.start_time,
                    "end_time": cue.end_time,
                    "text": cue.text,
                }
                for cue in self.cues
            ],
            "total_duration_seconds": self.total_duration_seconds,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def create(
        cls,
        source_subtitle_track_id: str,
        target_language: str,
        cues: list[SubtitleCue],
        total_duration_seconds: float,
    ) -> "TranslatedSubtitleTrack":
        return cls(
            id=str(uuid.uuid4()),
            source_subtitle_track_id=source_subtitle_track_id,
            target_language=target_language,
            cues=cues,
            total_duration_seconds=total_duration_seconds,
        )
