"""Provider-neutral evidence emitted by the character view quality gate."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CharacterViewObservation:
    person_count: int
    face_count: int
    head_inside_frame: bool
    feet_inside_frame: bool
    orientation: str
    confidence: float
    provider: str
    face_bbox: tuple[float, float, float, float] | None = None


@dataclass(frozen=True)
class CharacterViewQcReport:
    view: str
    seed: int
    passed: bool
    reasons: tuple[str, ...]
    observation: CharacterViewObservation
    framing_metrics: dict[str, float | int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "view": self.view,
            "seed": self.seed,
            "passed": self.passed,
            "reasons": list(self.reasons),
            "person_count": self.observation.person_count,
            "face_count": self.observation.face_count,
            "head_inside_frame": self.observation.head_inside_frame,
            "feet_inside_frame": self.observation.feet_inside_frame,
            "orientation": self.observation.orientation,
            "confidence": round(self.observation.confidence, 4),
            "provider": self.observation.provider,
            "face_bbox": (
                list(self.observation.face_bbox)
                if self.observation.face_bbox is not None
                else None
            ),
            "framing_metrics": dict(self.framing_metrics),
        }
