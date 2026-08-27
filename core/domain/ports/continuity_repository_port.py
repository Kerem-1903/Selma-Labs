from abc import ABC, abstractmethod
from core.domain.entities.continuity_state import ContinuityState

class ContinuityRepositoryPort(ABC):
    @abstractmethod
    async def save(self, state: ContinuityState) -> None:
        pass

    @abstractmethod
    async def load(self, id: str) -> ContinuityState:
        pass
