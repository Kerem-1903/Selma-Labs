from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class RenderSettings:
    width: int
    height: int
    fps: float
    sampling_steps: int
    guidance_scale: float


class RenderProfile(str, Enum):
    """Concrete quality/cost tiers used by local and rented GPU renders."""

    DRAFT = "DRAFT"
    BALANCED = "BALANCED"
    FINAL = "FINAL"

    @property
    def settings(self) -> RenderSettings:
        return {
            RenderProfile.DRAFT: RenderSettings(512, 288, 8.0, 6, 4.0),
            RenderProfile.BALANCED: RenderSettings(768, 432, 12.0, 12, 4.5),
            RenderProfile.FINAL: RenderSettings(1280, 720, 16.0, 20, 5.0),
        }[self]
