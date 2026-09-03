from __future__ import annotations

from abc import ABC, abstractmethod

from core.domain.entities.character_bible import CharacterBible
from core.domain.entities.direction_bible import CreativeDirectionBible, WorldBible
from core.domain.entities.episode_script import EpisodeScript
from core.domain.value_objects.story_review import StoryReviewReport


class StoryReviewerPort(ABC):
    @abstractmethod
    async def review(
        self,
        script: EpisodeScript,
        creative_direction: CreativeDirectionBible,
        world_bible: WorldBible,
        character_bibles: tuple[CharacterBible, ...],
    ) -> StoryReviewReport:
        raise NotImplementedError
