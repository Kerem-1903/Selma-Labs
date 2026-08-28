from abc import ABC, abstractmethod
from typing import List
from core.domain.entities.continuity_state import ContinuityState
from core.domain.events.continuity_event import ContinuityEvent

class ContinuityRepositoryPort(ABC):
    @abstractmethod
    async def save(self, state: ContinuityState) -> None:
        pass

    @abstractmethod
    async def load(self, id: str) -> ContinuityState:
        pass

    @abstractmethod
    async def append_event(self, timeline_id: str, event: ContinuityEvent) -> None:
        pass

    @abstractmethod
    async def load_events(self, timeline_id: str) -> List[ContinuityEvent]:
        pass
