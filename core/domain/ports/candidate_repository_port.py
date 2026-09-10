from typing import Protocol, List, Optional
from core.domain.entities.script_candidate import ScriptCandidate, CandidateGroup, CandidateStatus

class CandidateRepositoryPort(Protocol):
    def save(self, candidate: ScriptCandidate) -> None:
        """Saves a new or updated script candidate to the repository."""
        ...

    def get_by_id(self, candidate_id: str) -> Optional[ScriptCandidate]:
        """Retrieves a script candidate by its ID."""
        ...

    def list_by_status(self, status: CandidateStatus, limit: int = 100, offset: int = 0) -> List[ScriptCandidate]:
        """Lists candidates filtered by their current evaluation status."""
        ...

    def get_exportable_training_data(self) -> List[ScriptCandidate]:
        """
        Retrieves candidates suitable for training.
        MUST NOT return candidates in the HOLDOUT group to prevent data leakage.
        """
        ...
