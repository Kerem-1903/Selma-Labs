"""Provider-neutral evidence emitted by the character view quality gate."""

from __future__ import annotations

from collections.abc import Mapping
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
    person_bboxes: tuple[tuple[float, float, float, float], ...] = ()
    # Torso foreshortening across the shoulders and hips, normalized by torso
    # height. This is the only yaw axis that survives contact with stylised
    # anime art: the face keypoints and the face detector both read a true
    # profile as a three-quarter view, while the body genuinely narrows as the
    # character turns. It is recorded as advisory evidence -- the labelled
    # samples we own do not separate cleanly enough for it to gate approval.
    torso_foreshortening: float | None = None


@dataclass(frozen=True)
class CharacterViewQcReport:
    view: str
    seed: int
    passed: bool
    reasons: tuple[str, ...]
    observation: CharacterViewObservation
    framing_metrics: dict[str, float | int]
    checks: Mapping[str, bool] | None = None

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
            "person_bboxes": [list(box) for box in self.observation.person_bboxes],
            "torso_foreshortening": (
                round(self.observation.torso_foreshortening, 4)
                if self.observation.torso_foreshortening is not None
                else None
            ),
            "framing_metrics": dict(self.framing_metrics),
            "checks": dict(self.checks or {}),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CharacterViewQcReport:
        """Rebuild a report a pack recorded.

        ``to_dict`` flattens the observation into the report, so the inverse has
        to reassemble it. Needed wherever stored evidence is re-filed rather
        than re-measured -- a re-rendered view archives the render it replaced.
        """
        raw_bbox = data.get("face_bbox")
        raw_boxes = data.get("person_bboxes") or ()
        raw_foreshortening = data.get("torso_foreshortening")
        return cls(
            view=str(data.get("view", "")),
            seed=int(data.get("seed", 0)),
            passed=bool(data.get("passed", False)),
            reasons=tuple(str(reason) for reason in data.get("reasons", ())),
            observation=CharacterViewObservation(
                person_count=int(data.get("person_count", 0)),
                face_count=int(data.get("face_count", 0)),
                head_inside_frame=bool(data.get("head_inside_frame", False)),
                feet_inside_frame=bool(data.get("feet_inside_frame", False)),
                orientation=str(data.get("orientation", "")),
                confidence=float(data.get("confidence", 0.0)),
                provider=str(data.get("provider", "")),
                face_bbox=tuple(float(value) for value in raw_bbox) if raw_bbox else None,
                person_bboxes=tuple(
                    tuple(float(value) for value in box) for box in raw_boxes
                ),
                torso_foreshortening=(
                    float(raw_foreshortening)
                    if raw_foreshortening is not None
                    else None
                ),
            ),
            framing_metrics={
                str(name): value
                for name, value in (data.get("framing_metrics") or {}).items()
            },
            checks={
                str(name): bool(value)
                for name, value in (data.get("checks") or {}).items()
            },
        )
