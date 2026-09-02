from __future__ import annotations

from abc import ABC, abstractmethod

from core.domain.entities.character_bible import CharacterBible
from core.domain.entities.character_golden_set import (
    GoldenCandidateResult,
    GoldenTestCase,
)
from core.domain.entities.direction_bible import VisualStyleBible


class GoldenSetEvaluatorPort(ABC):
    @abstractmethod
    async def evaluate(
        self,
        *,
        character: CharacterBible,
        style: VisualStyleBible,
        test_case: GoldenTestCase,
        storage_key: str,
    ) -> GoldenCandidateResult:
        raise NotImplementedError
