from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum
from typing import Any

from core.domain.value_objects.portable_storage_key import PortableStorageKey


class MotionClipStatus(str, Enum):
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class ShotMotionClip:
    id: str
    shot_contract_id: str
    storyboard_id: str
    storyboard_frame_id: str
    candidate_id: str
    source_image_storage_key: str
    storage_key: str
    content_type: str
    provider: str
    provider_asset_id: str
    width: int
    height: int
    duration_seconds: float
    fps: float
    created_at: datetime
    render_profile: str = "BALANCED"
    status: MotionClipStatus = MotionClipStatus.PENDING_REVIEW

    def __post_init__(self) -> None:
        for value in (
            self.id,
            self.shot_contract_id,
            self.storyboard_id,
            self.storyboard_frame_id,
            self.candidate_id,
            self.provider,
            self.provider_asset_id,
        ):
            if not value.strip():
                raise ValueError("Motion clip identifiers must not be empty.")
        for key in (self.source_image_storage_key, self.storage_key):
            try:
                PortableStorageKey(key)
            except (TypeError, ValueError) as error:
                raise ValueError(
                    "Motion clip storage keys must be canonical portable relative keys."
                ) from error
        if self.content_type not in {"video/mp4", "video/webm"}:
            raise ValueError("Motion clip content type is unsupported.")
        if self.width <= 0 or self.height <= 0 or self.duration_seconds <= 0 or self.fps <= 0:
            raise ValueError("Motion clip media properties must be greater than zero.")
        if self.render_profile not in {"DRAFT", "BALANCED", "FINAL"}:
            raise ValueError("Motion clip render profile is unsupported.")

    def approve(self) -> ShotMotionClip:
        if self.status == MotionClipStatus.REJECTED:
            raise ValueError("A rejected motion clip cannot be approved.")
        return replace(self, status=MotionClipStatus.APPROVED)

    def reject(self) -> ShotMotionClip:
        if self.status == MotionClipStatus.APPROVED:
            raise ValueError("An approved motion clip cannot be rejected.")
        return replace(self, status=MotionClipStatus.REJECTED)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "shot_contract_id": self.shot_contract_id,
            "storyboard_id": self.storyboard_id,
            "storyboard_frame_id": self.storyboard_frame_id,
            "candidate_id": self.candidate_id,
            "source_image_storage_key": self.source_image_storage_key,
            "storage_key": self.storage_key,
            "content_type": self.content_type,
            "provider": self.provider,
            "provider_asset_id": self.provider_asset_id,
            "width": self.width,
            "height": self.height,
            "duration_seconds": self.duration_seconds,
            "fps": self.fps,
            "created_at": self.created_at.isoformat(),
            "render_profile": self.render_profile,
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ShotMotionClip:
        return cls(
            id=str(data["id"]),
            shot_contract_id=str(data["shot_contract_id"]),
            storyboard_id=str(data["storyboard_id"]),
            storyboard_frame_id=str(data["storyboard_frame_id"]),
            candidate_id=str(data["candidate_id"]),
            source_image_storage_key=str(data["source_image_storage_key"]),
            storage_key=str(data["storage_key"]),
            content_type=str(data["content_type"]),
            provider=str(data["provider"]),
            provider_asset_id=str(data["provider_asset_id"]),
            width=int(data["width"]),
            height=int(data["height"]),
            duration_seconds=float(data["duration_seconds"]),
            fps=float(data["fps"]),
            created_at=datetime.fromisoformat(str(data["created_at"])),
            render_profile=str(data.get("render_profile", "BALANCED")),
            status=MotionClipStatus(str(data.get("status", "PENDING_REVIEW"))),
        )
