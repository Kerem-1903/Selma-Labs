"""24 FPS editorial animatic that must be watched and human-approved."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from core.domain.exceptions import AnimaticApprovalError


class AnimaticStatus(str, Enum):
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    LOCKED = "LOCKED"


@dataclass(frozen=True)
class AnimaticClip:
    shot_id: str
    start_frame: int
    duration_frames: int
    image_storage_key: str
    dialogue: str = ""
    dialogue_audio_storage_key: str = ""

    def __post_init__(self) -> None:
        if (
            not self.shot_id.strip()
            or self.start_frame < 0
            or self.duration_frames < 1
            or not self.image_storage_key.strip()
        ):
            raise AnimaticApprovalError("Animatic clip is incomplete.")
        if self.dialogue.strip() and not self.dialogue_audio_storage_key.strip():
            raise AnimaticApprovalError("Dialogue clips require locked scratch audio.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "shot_id": self.shot_id,
            "start_frame": self.start_frame,
            "duration_frames": self.duration_frames,
            "image_storage_key": self.image_storage_key,
            "dialogue": self.dialogue,
            "dialogue_audio_storage_key": self.dialogue_audio_storage_key,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AnimaticClip:
        return cls(
            shot_id=str(data["shot_id"]),
            start_frame=int(data["start_frame"]),
            duration_frames=int(data["duration_frames"]),
            image_storage_key=str(data["image_storage_key"]),
            dialogue=str(data.get("dialogue", "")),
            dialogue_audio_storage_key=str(data.get("dialogue_audio_storage_key", "")),
        )


@dataclass(frozen=True)
class AnimaticProject:
    id: str
    production_plan_id: str
    fps: int
    width: int
    height: int
    clips: tuple[AnimaticClip, ...]
    status: AnimaticStatus
    created_at: datetime
    approved_by: str | None = None
    approved_at: datetime | None = None

    @classmethod
    def create(
        cls,
        *,
        production_plan_id: str,
        clips: tuple[AnimaticClip, ...],
        fps: int = 24,
        width: int = 1920,
        height: int = 1080,
    ) -> AnimaticProject:
        if not production_plan_id.strip() or not clips or fps != 24:
            raise AnimaticApprovalError(
                "Animatic requires a plan, clips, and locked 24 FPS."
            )
        if width <= 0 or height <= 0:
            raise AnimaticApprovalError("Animatic dimensions must be positive.")
        expected_start = 0
        for clip in clips:
            if clip.start_frame != expected_start:
                raise AnimaticApprovalError(
                    "Animatic clips must form a contiguous timeline."
                )
            expected_start += clip.duration_frames
        return cls(
            str(uuid.uuid4()),
            production_plan_id,
            fps,
            width,
            height,
            tuple(clips),
            AnimaticStatus.READY_FOR_REVIEW,
            datetime.now(timezone.utc),
        )

    @property
    def duration_in_frames(self) -> int:
        return sum(clip.duration_frames for clip in self.clips)

    def lock(self, approved_by: str) -> AnimaticProject:
        if not approved_by.strip():
            raise AnimaticApprovalError("Animatic approver must not be empty.")
        return replace(
            self,
            status=AnimaticStatus.LOCKED,
            approved_by=approved_by.strip(),
            approved_at=datetime.now(timezone.utc),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "production_plan_id": self.production_plan_id,
            "fps": self.fps,
            "width": self.width,
            "height": self.height,
            "duration_in_frames": self.duration_in_frames,
            "clips": [clip.to_dict() for clip in self.clips],
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "approved_by": self.approved_by,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AnimaticProject:
        return cls(
            id=str(data["id"]),
            production_plan_id=str(data["production_plan_id"]),
            fps=int(data["fps"]),
            width=int(data["width"]),
            height=int(data["height"]),
            clips=tuple(AnimaticClip.from_dict(dict(item)) for item in data["clips"]),
            status=AnimaticStatus(str(data["status"])),
            created_at=datetime.fromisoformat(str(data["created_at"])),
            approved_by=str(data["approved_by"]) if data.get("approved_by") else None,
            approved_at=(
                datetime.fromisoformat(str(data["approved_at"]))
                if data.get("approved_at")
                else None
            ),
        )
