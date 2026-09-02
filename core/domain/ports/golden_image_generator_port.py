from __future__ import annotations

from abc import ABC, abstractmethod

from core.domain.entities.character_bible import CharacterBible
from core.domain.entities.character_golden_set import GoldenTestCase
from core.domain.entities.direction_bible import VisualStyleBible


class GoldenImageGeneratorPort(ABC):
    @abstractmethod
    async def generate(
        self,
        *,
        character: CharacterBible,
        style: VisualStyleBible,
        test_case: GoldenTestCase,
    ) -> str:
        """Return the portable storage key of one generated test image."""
        raise NotImplementedError
