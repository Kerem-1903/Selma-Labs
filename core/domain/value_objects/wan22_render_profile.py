"""Typed generation contracts for Wan2.2 renders."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any


class WanPostprocess(str, Enum):
    NONE = "NONE"
    INTERPOLATE_TO_24 = "INTERPOLATE_TO_24"


@dataclass(frozen=True)
class Wan22RenderProfile:
    """The source render contract, deliberately separate from a 24 FPS timeline."""

    name: str
    frame_count: int
    fps: int
    steps: int
    postprocess: WanPostprocess = WanPostprocess.NONE

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Wan render profile name is required.")
        if self.frame_count < 1 or self.fps < 1 or self.steps < 1:
            raise ValueError("Wan render profile frame_count, fps, and steps must be positive.")
        if self.postprocess == WanPostprocess.INTERPOLATE_TO_24 and self.fps >= 24:
            raise ValueError("Interpolation to 24 FPS is only valid for a source below 24 FPS.")

    @classmethod
    def draft_16fps(cls) -> Wan22RenderProfile:
        return cls("draft_16fps", 81, 16, 4, WanPostprocess.INTERPOLATE_TO_24)

    @classmethod
    def final_24fps(cls) -> Wan22RenderProfile:
        return cls("final_24fps", 121, 24, 40, WanPostprocess.NONE)

    @classmethod
    def named(cls, name: str) -> Wan22RenderProfile:
        profiles = {profile.name: profile for profile in (cls.draft_16fps(), cls.final_24fps())}
        try:
            return profiles[name]
        except KeyError as exc:
            raise ValueError(f"Unknown Wan render profile '{name}'.") from exc

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "frame_count": self.frame_count,
            "fps": self.fps,
            "steps": self.steps,
            "postprocess": self.postprocess.value,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Wan22RenderProfile:
        return cls(
            name=str(data["name"]),
            frame_count=int(data["frame_count"]),
            fps=int(data["fps"]),
            steps=int(data["steps"]),
            postprocess=WanPostprocess(str(data.get("postprocess", "NONE"))),
        )


# The design document uses WanRenderProfile as the contract name; retain the
# Wan2.2-qualified name as the explicit implementation name.
WanRenderProfile = Wan22RenderProfile
