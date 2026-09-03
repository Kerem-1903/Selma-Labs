from __future__ import annotations

from abc import ABC, abstractmethod

from core.domain.entities.character_bible import CharacterBible
from core.domain.entities.direction_bible import (
    CreativeDirectionBible,
    VisualStyleBible,
    WorldBible,
)


class CanonRepositoryPort(ABC):
    @abstractmethod
    async def get_creative_direction(self) -> CreativeDirectionBible:
        raise NotImplementedError

    @abstractmethod
    async def get_world_bible(self) -> WorldBible:
        raise NotImplementedError

    async def get_visual_style(self) -> VisualStyleBible:
        """Return visual canon; optional for older story-only repository adapters."""
        raise NotImplementedError

    @abstractmethod
    async def get_character_bibles(self) -> tuple[CharacterBible, ...]:
        raise NotImplementedError
