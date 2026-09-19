"""Reproducible Wan2.2 I2V request package metadata."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from core.domain.exceptions import PreProductionValidationError

_SHA = re.compile(r"^[0-9a-fA-F]{64}$")


def _digest(value: str, name: str, *, allow_pending: bool = False) -> str:
    if allow_pending and value in {"PENDING", "NOT_INSTALLED"}:
        return value
    if not _SHA.fullmatch(value):
        raise PreProductionValidationError(f"{name} must be a SHA-256 digest.")
    return value.lower()


@dataclass(frozen=True)
class Wan22AnimationPackage:
    shot_id: str
    source_image_key: str
    source_image_hash: str
    motion_prompt: str
    negative_prompt: str
    seed: int
    frame_count: int
    fps: int
    width: int
    height: int
    workflow_hash: str
    model_revision: str
    generation_attempt: int = 1
    output_video_key: str = ""

    def __post_init__(self) -> None:
        if not self.shot_id.strip() or not self.source_image_key.strip() or not self.motion_prompt.strip():
            raise PreProductionValidationError("Wan package identity, source, and motion prompt are required.")
        _digest(self.source_image_hash, "source_image_hash")
        _digest(self.workflow_hash, "workflow_hash", allow_pending=True)
        if not self.model_revision.strip() or self.frame_count < 1 or self.fps < 1:
            raise PreProductionValidationError("Wan package requires positive frames and FPS.")
        if self.width <= 0 or self.height <= 0 or self.seed < 0 or self.generation_attempt < 1:
            raise PreProductionValidationError("Wan package numeric fields are invalid.")
        if self.output_video_key and (self.output_video_key.startswith("/") or ".." in self.output_video_key.replace("\\", "/").split("/")):
            raise PreProductionValidationError("output_video_key must be a portable relative key.")

    @property
    def duration_frames(self) -> int:
        return self.frame_count

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "shot_id": self.shot_id,
            "source_image_key": self.source_image_key,
            "source_image_hash": self.source_image_hash,
            "motion_prompt": self.motion_prompt,
            "negative_prompt": self.negative_prompt,
            "seed": self.seed,
            "frame_count": self.frame_count,
            "fps": self.fps,
            "width": self.width,
            "height": self.height,
            "workflow_hash": self.workflow_hash,
            "model_revision": self.model_revision,
            "generation_attempt": self.generation_attempt,
            "output_video_key": self.output_video_key,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Wan22AnimationPackage:
        return cls(
            shot_id=str(data.get("shot_id", "")),
            source_image_key=str(data.get("source_image_key", "")),
            source_image_hash=str(data.get("source_image_hash", "")),
            motion_prompt=str(data.get("motion_prompt", "")),
            negative_prompt=str(data.get("negative_prompt", "")),
            seed=int(data.get("seed", -1)),
            frame_count=int(data.get("frame_count", 0)),
            fps=int(data.get("fps", 0)),
            width=int(data.get("width", 0)),
            height=int(data.get("height", 0)),
            workflow_hash=str(data.get("workflow_hash", "")),
            model_revision=str(data.get("model_revision", "")),
            generation_attempt=int(data.get("generation_attempt", 0)),
            output_video_key=str(data.get("output_video_key", "")),
        )
