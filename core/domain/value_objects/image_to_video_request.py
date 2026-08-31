from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from core.domain.value_objects.render_profile import RenderProfile


@dataclass(frozen=True)
class ImageToVideoRequest:
    shot_contract_id: str
    storyboard_id: str
    storyboard_frame_id: str
    source_image_storage_key: str
    target_duration_seconds: float
    motion_prompt: str
    camera_motion: str = "static"
    width: int = 1024
    height: int = 576
    fps: float = 24.0
    seed: int | None = None
    sampling_steps: int = 12
    guidance_scale: float = 4.5
    render_profile: RenderProfile = RenderProfile.BALANCED

    def __post_init__(self) -> None:
        for name, value in (
            ("shot_contract_id", self.shot_contract_id),
            ("storyboard_id", self.storyboard_id),
            ("storyboard_frame_id", self.storyboard_frame_id),
            ("source_image_storage_key", self.source_image_storage_key),
            ("motion_prompt", self.motion_prompt),
        ):
            if not value.strip():
                raise ValueError(f"{name} must not be empty.")
        if not 0.25 <= self.target_duration_seconds <= 30.0:
            raise ValueError("target_duration_seconds must be between 0.25 and 30.")
        storage_path = PurePosixPath(self.source_image_storage_key.replace("\\", "/"))
        if storage_path.is_absolute() or ".." in storage_path.parts or ":" in self.source_image_storage_key:
            raise ValueError("source_image_storage_key must be a portable relative key.")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("Video dimensions must be greater than zero.")
        if not 1.0 <= self.fps <= 120.0:
            raise ValueError("fps must be between 1 and 120.")
        if not 1 <= self.sampling_steps <= 150:
            raise ValueError("sampling_steps must be between 1 and 150.")
        if not 0.0 < self.guidance_scale <= 30.0:
            raise ValueError("guidance_scale must be between 0 and 30.")
