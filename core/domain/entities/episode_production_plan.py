"""Episode -> sequence -> scene -> shot hierarchy for anime pre-production."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from core.domain.entities.shot_animation import AnimationShotPlan
from core.domain.exceptions import PreProductionValidationError


@dataclass(frozen=True)
class DirectedShot:
    plan: AnimationShotPlan
    shot_size: str
    camera_movement: str
    start_keyframe_intent: str
    end_keyframe_intent: str
    effects: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if any(
            not value.strip()
            for value in (
                self.shot_size,
                self.camera_movement,
                self.start_keyframe_intent,
                self.end_keyframe_intent,
            )
        ):
            raise PreProductionValidationError(
                "Directed shot fields must not be empty."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan": self.plan.to_dict(),
            "shot_size": self.shot_size,
            "camera_movement": self.camera_movement,
            "start_keyframe_intent": self.start_keyframe_intent,
            "end_keyframe_intent": self.end_keyframe_intent,
            "effects": list(self.effects),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DirectedShot:
        return cls(
            plan=AnimationShotPlan.from_dict(dict(data["plan"])),
            shot_size=str(data["shot_size"]),
            camera_movement=str(data["camera_movement"]),
            start_keyframe_intent=str(data["start_keyframe_intent"]),
            end_keyframe_intent=str(data["end_keyframe_intent"]),
            effects=tuple(str(value) for value in data.get("effects", [])),
        )


@dataclass(frozen=True)
class ProductionScene:
    id: str
    title: str
    location: str
    shots: tuple[DirectedShot, ...]

    def __post_init__(self) -> None:
        if not self.shots:
            raise PreProductionValidationError(
                "Production scene requires at least one shot."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "location": self.location,
            "shots": [shot.to_dict() for shot in self.shots],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProductionScene:
        return cls(
            id=str(data["id"]),
            title=str(data["title"]),
            location=str(data["location"]),
            shots=tuple(DirectedShot.from_dict(dict(item)) for item in data["shots"]),
        )


@dataclass(frozen=True)
class ProductionSequence:
    id: str
    title: str
    scenes: tuple[ProductionScene, ...]

    def __post_init__(self) -> None:
        if not self.scenes:
            raise PreProductionValidationError(
                "Production sequence requires at least one scene."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "scenes": [scene.to_dict() for scene in self.scenes],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProductionSequence:
        return cls(
            id=str(data["id"]),
            title=str(data["title"]),
            scenes=tuple(
                ProductionScene.from_dict(dict(item)) for item in data["scenes"]
            ),
        )


@dataclass(frozen=True)
class EpisodeProductionPlan:
    id: str
    episode_script_id: str
    episode_revision: int
    sequences: tuple[ProductionSequence, ...]
    created_at: datetime

    @classmethod
    def create(
        cls,
        *,
        episode_script_id: str,
        episode_revision: int,
        sequences: tuple[ProductionSequence, ...],
    ) -> EpisodeProductionPlan:
        if not episode_script_id.strip() or episode_revision < 1 or not sequences:
            raise PreProductionValidationError("Episode production plan is incomplete.")
        return cls(
            str(uuid.uuid4()),
            episode_script_id,
            episode_revision,
            tuple(sequences),
            datetime.now(timezone.utc),
        )

    @property
    def shots(self) -> tuple[DirectedShot, ...]:
        return tuple(
            shot
            for sequence in self.sequences
            for scene in sequence.scenes
            for shot in scene.shots
        )

    @property
    def duration_seconds(self) -> float:
        return sum(shot.plan.duration_seconds for shot in self.shots)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "episode_script_id": self.episode_script_id,
            "episode_revision": self.episode_revision,
            "sequences": [sequence.to_dict() for sequence in self.sequences],
            "duration_seconds": self.duration_seconds,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EpisodeProductionPlan:
        return cls(
            id=str(data["id"]),
            episode_script_id=str(data["episode_script_id"]),
            episode_revision=int(data["episode_revision"]),
            sequences=tuple(
                ProductionSequence.from_dict(dict(item)) for item in data["sequences"]
            ),
            created_at=datetime.fromisoformat(str(data["created_at"])),
        )
