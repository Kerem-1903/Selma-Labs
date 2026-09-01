from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable

from core.domain.entities.shot_animation import ShotMotionClip, ShotPlan

ProgressCallback = Callable[[float], None]


class MotionGeneratorPort(ABC):
    @property
    def name(self) -> str:
        return self.__class__.__name__

    @abstractmethod
    async def generate_motion_clip(
        self,
        shot_plan: ShotPlan,
        progress_callback: ProgressCallback | None = None,
    ) -> ShotMotionClip:
        raise NotImplementedError
