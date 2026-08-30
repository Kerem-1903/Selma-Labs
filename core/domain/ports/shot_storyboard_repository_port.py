from __future__ import annotations

from abc import ABC, abstractmethod

from core.domain.entities.shot_storyboard import ShotStoryboard


class ShotStoryboardRepositoryPort(ABC):
    @abstractmethod
    async def save(self, storyboard: ShotStoryboard) -> None:
        raise NotImplementedError
    @abstractmethod
    async def load(self, storyboard_id: str) -> ShotStoryboard:
        raise NotImplementedError
