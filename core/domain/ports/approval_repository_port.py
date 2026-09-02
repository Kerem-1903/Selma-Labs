from __future__ import annotations

from abc import ABC, abstractmethod

from core.domain.entities.episode_script import EpisodeScript


class ApprovalRepositoryPort(ABC):
    @abstractmethod
    async def record_story_approval(self, script: EpisodeScript) -> None:
        raise NotImplementedError
