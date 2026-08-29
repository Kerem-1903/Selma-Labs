from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any

from core.domain.value_objects.storyboard_frame import StoryboardFrame


@dataclass(frozen=True)
class ShotStoryboard:
    id: str
    shot_contract_id: str
    frames: tuple[StoryboardFrame, ...]
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.shot_contract_id.strip():
            raise ValueError("Storyboard and shot contract IDs must not be empty.")
        sequence_indexes: set[int] = set()
        for frame in self.frames:
            if frame.shot_contract_id != self.shot_contract_id:
                raise ValueError("Storyboard frame belongs to another shot contract.")
            if frame.sequence_index in sequence_indexes:
                raise ValueError(
                    f"Storyboard contains duplicate sequence index {frame.sequence_index}."
                )
            sequence_indexes.add(frame.sequence_index)

    @staticmethod
    def create(shot_contract_id: str) -> "ShotStoryboard":
        if not shot_contract_id.strip():
            raise ValueError("shot_contract_id must not be empty.")
        now = datetime.now(timezone.utc)
        return ShotStoryboard(
            id=str(uuid.uuid4()),
            shot_contract_id=shot_contract_id,
            frames=(),
            created_at=now,
            updated_at=now,
        )

    def with_frame(self, frame: StoryboardFrame) -> "ShotStoryboard":
        if frame.shot_contract_id != self.shot_contract_id:
            raise ValueError("Storyboard frame belongs to another shot contract.")
        if any(existing.sequence_index == frame.sequence_index for existing in self.frames):
            raise ValueError(
                f"Storyboard already contains sequence index {frame.sequence_index}."
            )
        return replace(
            self,
            frames=tuple(sorted((*self.frames, frame), key=lambda item: item.sequence_index)),
            updated_at=datetime.now(timezone.utc),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "shot_contract_id": self.shot_contract_id,
            "frames": [frame.to_dict() for frame in self.frames],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ShotStoryboard":
        storyboard = cls(
            id=str(data["id"]),
            shot_contract_id=str(data["shot_contract_id"]),
            frames=tuple(
                StoryboardFrame.from_dict(frame) for frame in data.get("frames", [])
            ),
            created_at=datetime.fromisoformat(str(data["created_at"])),
            updated_at=datetime.fromisoformat(str(data["updated_at"])),
        )
        if tuple(sorted(storyboard.frames, key=lambda item: item.sequence_index)) != storyboard.frames:
            raise ValueError("Storyboard frames are not stored in sequence order.")
        return storyboard
