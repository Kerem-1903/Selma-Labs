from __future__ import annotations

from abc import ABC, abstractmethod

from core.domain.entities.character_bible import CharacterBible
from core.domain.entities.direction_bible import CreativeDirectionBible, WorldBible
from core.domain.entities.episode_script import EpisodeScript, StoryBrief


class StoryGeneratorPort(ABC):
    @abstractmethod
    async def generate_episode(
        self,
        brief: StoryBrief,
        creative_direction: CreativeDirectionBible,
        world_bible: WorldBible,
        character_bibles: tuple[CharacterBible, ...],
    ) -> EpisodeScript:
        raise NotImplementedError
