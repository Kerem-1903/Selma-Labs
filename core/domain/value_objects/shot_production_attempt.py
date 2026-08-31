from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from core.domain.value_objects.render_profile import RenderProfile


class ProductionAttemptStatus(str, Enum):
    SUCCEEDED = "SUCCEEDED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_PERMANENT = "FAILED_PERMANENT"


@dataclass(frozen=True)
class ShotProductionAttempt:
    shot_contract_id: str
    attempt_number: int
    profile: RenderProfile
    provider: str
    seed: int | None
    started_at: datetime
    finished_at: datetime
    elapsed_seconds: float
    estimated_cost_usd: float
    status: ProductionAttemptStatus
    error_type: str | None = None
    error_message: str | None = None

    def __post_init__(self) -> None:
        if not self.shot_contract_id.strip() or not self.provider.strip():
            raise ValueError("Production attempt identifiers must not be empty.")
        if self.attempt_number < 1 or self.elapsed_seconds < 0:
            raise ValueError("Production attempt counters must be valid.")
        if self.estimated_cost_usd < 0:
            raise ValueError("Estimated production cost cannot be negative.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "shot_contract_id": self.shot_contract_id,
            "attempt_number": self.attempt_number,
            "profile": self.profile.value,
            "provider": self.provider,
            "seed": self.seed,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "elapsed_seconds": self.elapsed_seconds,
            "estimated_cost_usd": self.estimated_cost_usd,
            "status": self.status.value,
            "error_type": self.error_type,
            "error_message": self.error_message,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ShotProductionAttempt":
        return cls(
            shot_contract_id=str(data["shot_contract_id"]),
            attempt_number=int(data["attempt_number"]),
            profile=RenderProfile(str(data["profile"])),
            provider=str(data["provider"]),
            seed=None if data.get("seed") is None else int(data["seed"]),
            started_at=datetime.fromisoformat(str(data["started_at"])),
            finished_at=datetime.fromisoformat(str(data["finished_at"])),
            elapsed_seconds=float(data["elapsed_seconds"]),
            estimated_cost_usd=float(data["estimated_cost_usd"]),
            status=ProductionAttemptStatus(str(data["status"])),
            error_type=None if data.get("error_type") is None else str(data["error_type"]),
            error_message=None if data.get("error_message") is None else str(data["error_message"]),
        )
