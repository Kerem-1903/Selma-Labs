from abc import ABC, abstractmethod
from typing import Callable, Any
from core.domain.entities.shot_animation import ShotPlan, ShotMotionClip

class MotionGeneratorPort(ABC):
    @abstractmethod
    async def generate_motion_clip(self, shot_plan: ShotPlan, progress_callback: Callable[[float], None]) -> ShotMotionClip:
        pass
