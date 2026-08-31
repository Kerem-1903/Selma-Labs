from abc import ABC, abstractmethod
from core.domain.entities.candidate.keyframe_candidate import KeyframeCandidate

class KeyframeCandidateRepositoryPort(ABC):
    @abstractmethod
    async def save(self, candidate: KeyframeCandidate) -> None:
        """Saves a keyframe candidate."""
        pass

    @abstractmethod
    async def get_by_id(self, candidate_id: str) -> KeyframeCandidate | None:
        """Retrieves a candidate by its ID."""
        pass

    @abstractmethod
    async def get_by_shot_contract_id(self, shot_contract_id: str) -> list[KeyframeCandidate]:
        """Retrieves all candidates for a specific shot."""
        pass

    @abstractmethod
    async def list_pending(self, limit: int = 100) -> list[KeyframeCandidate]:
        """Retrieves pending candidates."""
        pass
