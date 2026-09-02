from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any

from core.domain.entities.character_state import CharacterState

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _validate_storage_key(value: str, field_name: str, *, optional: bool = False) -> None:
    if optional and not value:
        return
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if not normalized.strip() or path.is_absolute() or ".." in path.parts or ":" in value:
        raise ValueError(f"{field_name} must be a portable relative storage key.")


@dataclass(frozen=True)
class AnimationShotPlan:
    """One executable anime shot produced from a script line.

    This is intentionally separate from the existing aggregate ShotPlan, which
    groups typed ShotContracts for the A4 planning workflow.
    """

    id: str
    script_id: str
    scene_plan_id: str
    prompt: str
    duration_seconds: float
    character_state: CharacterState
    dialogue: str = ""
    source_image_storage_key: str = ""
    keyframe_approved: bool = False
    negative_prompt: str = ""
    start_keyframe_key: str | None = None
    end_keyframe_key: str | None = None
    pose_reference_key: str | None = None
    controlnet_type: str | None = "openpose"
    metadata: dict[str, Any] = field(default_factory=dict)
    prompt_end: str | None = None

    def __post_init__(self) -> None:
        for field_name, value in (
            ("id", self.id),
            ("script_id", self.script_id),
            ("scene_plan_id", self.scene_plan_id),
        ):
            if not _SAFE_ID.fullmatch(value):
                raise ValueError(f"{field_name} must be a storage-safe identifier.")
        if not self.prompt.strip():
            raise ValueError("Animation shot prompt must not be empty.")
        if not 0.25 <= self.duration_seconds <= 30.0:
            raise ValueError("Animation shot duration must be between 0.25 and 30 seconds.")
        if self.character_state.character_id.strip() == "":
            raise ValueError("Animation shot requires a character state.")
        _validate_storage_key(
            self.source_image_storage_key,
            "source_image_storage_key",
            optional=not self.keyframe_approved,
        )
        if self.keyframe_approved and not self.source_image_storage_key:
            raise ValueError("An approved animation shot requires a source image storage key.")

    def approve_keyframe(self, storage_key: str) -> AnimationShotPlan:
        _validate_storage_key(storage_key, "source_image_storage_key")
        return AnimationShotPlan(
            id=self.id,
            script_id=self.script_id,
            scene_plan_id=self.scene_plan_id,
            prompt=self.prompt,
            duration_seconds=self.duration_seconds,
            character_state=self.character_state,
            dialogue=self.dialogue,
            source_image_storage_key=storage_key,
            keyframe_approved=True,
            negative_prompt=self.negative_prompt,
            metadata=dict(self.metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "script_id": self.script_id,
            "scene_plan_id": self.scene_plan_id,
            "prompt": self.prompt,
            "prompt_end": self.prompt_end,
            "duration_seconds": self.duration_seconds,
            "character_state": self.character_state.to_dict(),
            "dialogue": self.dialogue,
            "source_image_storage_key": self.source_image_storage_key,
            "keyframe_approved": self.keyframe_approved,
            "negative_prompt": self.negative_prompt,
            "start_keyframe_key": self.start_keyframe_key,
            "end_keyframe_key": self.end_keyframe_key,
            "pose_reference_key": self.pose_reference_key,
            "controlnet_type": self.controlnet_type,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AnimationShotPlan:
        return cls(
            id=str(data["id"]),
            script_id=str(data["script_id"]),
            scene_plan_id=str(data["scene_plan_id"]),
            prompt=str(data["prompt"]),
            prompt_end=data.get("prompt_end"),
            duration_seconds=float(data["duration_seconds"]),
            character_state=CharacterState.from_dict(dict(data["character_state"])),
            dialogue=str(data.get("dialogue", "")),
            source_image_storage_key=str(data.get("source_image_storage_key", "")),
            keyframe_approved=bool(data.get("keyframe_approved", False)),
            negative_prompt=str(data.get("negative_prompt", "")),
            start_keyframe_key=data.get("start_keyframe_key"),
            end_keyframe_key=data.get("end_keyframe_key"),
            pose_reference_key=data.get("pose_reference_key"),
            controlnet_type=data.get("controlnet_type", "openpose"),
            metadata=dict(data.get("metadata", {})),
        )


# Compatibility name for this bounded context; the existing aggregate remains
# available from core.domain.entities.shot_plan.
ShotPlan = AnimationShotPlan


@dataclass(frozen=True)
class ShotMotionClip:
    """Portable result of the two-pass motion generator."""

    video_path: str
    hash: str
    seed: int
    cached: bool
    provider_asset_id: str = ""
    pass_prompt_ids: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        _validate_storage_key(self.video_path, "video_path")
        if not re.fullmatch(r"[0-9a-f]{64}", self.hash):
            raise ValueError("ShotMotionClip hash must be a SHA-256 digest.")
        if self.seed < 0:
            raise ValueError("ShotMotionClip seed must not be negative.")

    @property
    def storage_key(self) -> str:
        return self.video_path

    @property
    def content_hash(self) -> str:
        return self.hash
