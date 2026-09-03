from __future__ import annotations

from abc import ABC, abstractmethod

from core.domain.value_objects.character_lora_training import (
    CharacterLoraTrainingRequest,
    CharacterLoraTrainingResult,
)


class CharacterLoraTrainerPort(ABC):
    @abstractmethod
    async def train(
        self, request: CharacterLoraTrainingRequest
    ) -> CharacterLoraTrainingResult:
        raise NotImplementedError
