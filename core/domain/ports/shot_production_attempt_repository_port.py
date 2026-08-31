from __future__ import annotations

from abc import ABC, abstractmethod

from core.domain.value_objects.shot_production_attempt import ShotProductionAttempt


class ShotProductionAttemptRepositoryPort(ABC):
    @abstractmethod
    async def save(self, attempt: ShotProductionAttempt) -> None:
        raise NotImplementedError

    @abstractmethod
    async def list_for_shot(self, shot_contract_id: str) -> list[ShotProductionAttempt]:
        raise NotImplementedError
