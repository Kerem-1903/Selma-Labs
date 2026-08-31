from __future__ import annotations

from abc import ABC, abstractmethod

from core.domain.entities.shot_motion_clip import ShotMotionClip


class ShotMotionClipRepositoryPort(ABC):
    @abstractmethod
    async def save(self, clip: ShotMotionClip) -> None:
        raise NotImplementedError
    @abstractmethod
    async def load(self, clip_id: str) -> ShotMotionClip:
        raise NotImplementedError
