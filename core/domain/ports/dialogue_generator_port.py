from __future__ import annotations

from abc import ABC, abstractmethod

from core.domain.entities.character_bible import CharacterBible
from core.domain.entities.episode_script import EpisodeScript


class DialogueGeneratorPort(ABC):
    @abstractmethod
    async def refine_dialogue(
        self, script: EpisodeScript, character_bibles: tuple[CharacterBible, ...]
    ) -> EpisodeScript:
        raise NotImplementedError
