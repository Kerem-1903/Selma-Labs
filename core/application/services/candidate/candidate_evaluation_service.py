from __future__ import annotations

import uuid
from typing import Any

from core.domain.entities.candidate.keyframe_candidate import KeyframeCandidate
from core.domain.ports.candidate.keyframe_candidate_repository_port import KeyframeCandidateRepositoryPort

class CandidateEvaluationService:
    def __init__(self, repository: KeyframeCandidateRepositoryPort) -> None:
        self._repository = repository

    async def register_candidate(
        self,
        shot_contract_id: str,
        storage_key: str,
        generation_metadata: dict[str, Any],
    ) -> KeyframeCandidate:
        """Registers a newly generated keyframe candidate for evaluation."""
        candidate = KeyframeCandidate(
            id=str(uuid.uuid4()),
            shot_contract_id=shot_contract_id,
            storage_key=storage_key,
            generation_metadata=generation_metadata,
        )
        await self._repository.save(candidate)
        return candidate

    async def get_candidate(self, candidate_id: str) -> KeyframeCandidate | None:
        """Retrieves a candidate by its ID."""
        return await self._repository.get_by_id(candidate_id)

    async def get_candidates_for_shot(self, shot_contract_id: str) -> list[KeyframeCandidate]:
        """Retrieves all candidates for a specific shot."""
        return await self._repository.get_by_shot_contract_id(shot_contract_id)

    async def approve_candidate(self, candidate_id: str) -> KeyframeCandidate:
        candidate = await self._repository.get_by_id(candidate_id)
        if not candidate:
            raise ValueError(f"Candidate {candidate_id} not found.")

        candidate.approve()
        await self._repository.save(candidate)
        return candidate

    async def reject_candidate(self, candidate_id: str, reason: str, score: int | None = None) -> KeyframeCandidate:
        candidate = await self._repository.get_by_id(candidate_id)
        if not candidate:
            raise ValueError(f"Candidate {candidate_id} not found.")

        candidate.reject(reason, score)
        await self._repository.save(candidate)
        return candidate

    async def flag_candidate_for_revision(self, candidate_id: str, reason: str) -> KeyframeCandidate:
        candidate = await self._repository.get_by_id(candidate_id)
        if not candidate:
            raise ValueError(f"Candidate {candidate_id} not found.")

        candidate.flag_for_revision(reason)
        await self._repository.save(candidate)
        return candidate

    async def get_approved_candidate_for_shot(self, shot_contract_id: str) -> KeyframeCandidate | None:
        """Quality Gate: returns the first approved candidate for a shot, if any."""
        candidates = await self.get_candidates_for_shot(shot_contract_id)
        for candidate in candidates:
            if candidate.status == "APPROVED":
                return candidate
        return None
