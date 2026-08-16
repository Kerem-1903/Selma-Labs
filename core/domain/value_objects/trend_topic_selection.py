from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.domain.value_objects.trend_video import TrendVideo


@dataclass(frozen=True)
class TrendTopicSelection:
    topic: str
    angle: str
    rationale: str
    source_video_ids: list[str]
    candidates: list[TrendVideo]
    provider_used: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "angle": self.angle,
            "rationale": self.rationale,
            "source_video_ids": list(self.source_video_ids),
            "provider_used": self.provider_used,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
        }
