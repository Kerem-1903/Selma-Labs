from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

class CandidateStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    NEEDS_REVISION = "NEEDS_REVISION"
    COMMITTED = "COMMITTED"

@dataclass
class KeyframeCandidate:
    id: str
    shot_contract_id: str
    storage_key: str
    generation_metadata: dict[str, Any]
    status: CandidateStatus = CandidateStatus.PENDING
    score: int | None = None
    rejection_reason: str | None = None
    created_at: datetime.datetime = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    reviewed_at: datetime.datetime | None = None

    def approve(self) -> None:
        if self.status == CandidateStatus.COMMITTED:
            raise ValueError("A committed candidate cannot be reviewed again.")
        self.status = CandidateStatus.APPROVED
        self.reviewed_at = datetime.datetime.now(datetime.timezone.utc)
        self.rejection_reason = None

    def reject(self, reason: str, score: int | None = None) -> None:
        if self.status == CandidateStatus.COMMITTED:
            raise ValueError("A committed candidate cannot be reviewed again.")
        if score is not None and not (1 <= score <= 5):
            raise ValueError("Score must be between 1 and 5.")
        self.status = CandidateStatus.REJECTED
        self.reviewed_at = datetime.datetime.now(datetime.timezone.utc)
        self.rejection_reason = reason
        if score is not None:
            self.score = score

    def flag_for_revision(self, reason: str) -> None:
        if self.status == CandidateStatus.COMMITTED:
            raise ValueError("A committed candidate cannot be reviewed again.")
        self.status = CandidateStatus.NEEDS_REVISION
        self.reviewed_at = datetime.datetime.now(datetime.timezone.utc)
        self.rejection_reason = reason

    def rate(self, score: int) -> None:
        if not (1 <= score <= 5):
            raise ValueError("Score must be between 1 and 5.")
        self.score = score

    def mark_committed(self) -> None:
        if self.status != CandidateStatus.APPROVED:
            raise ValueError("Only an approved candidate can be committed.")
        self.status = CandidateStatus.COMMITTED

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "shot_contract_id": self.shot_contract_id,
            "storage_key": self.storage_key,
            "generation_metadata": self.generation_metadata,
            "status": self.status.value,
            "score": self.score,
            "rejection_reason": self.rejection_reason,
            "created_at": self.created_at.isoformat(),
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "KeyframeCandidate":
        return cls(
            id=str(data["id"]),
            shot_contract_id=str(data["shot_contract_id"]),
            storage_key=str(data["storage_key"]),
            generation_metadata=data.get("generation_metadata", {}),
            status=CandidateStatus(data.get("status", "PENDING")),
            score=data.get("score"),
            rejection_reason=data.get("rejection_reason"),
            created_at=datetime.datetime.fromisoformat(data["created_at"]),
            reviewed_at=(
                datetime.datetime.fromisoformat(data["reviewed_at"])
                if data.get("reviewed_at")
                else None
            ),
        )
