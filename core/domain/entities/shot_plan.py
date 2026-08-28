from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from core.domain.entities.shot_contract import ShotContract


@dataclass(frozen=True)
class ShotPlan:
    id: str
    script_id: str
    scene_plan_id: str
    continuity_timeline_id: str
    continuity_through_sequence: int
    contracts: tuple[ShotContract, ...]
    created_at: datetime

    @staticmethod
    def create(
        *,
        script_id: str,
        scene_plan_id: str,
        continuity_timeline_id: str,
        continuity_through_sequence: int,
        contracts: tuple[ShotContract, ...],
    ) -> "ShotPlan":
        return ShotPlan(
            id=str(uuid.uuid4()),
            script_id=script_id,
            scene_plan_id=scene_plan_id,
            continuity_timeline_id=continuity_timeline_id,
            continuity_through_sequence=continuity_through_sequence,
            contracts=contracts,
            created_at=datetime.now(timezone.utc),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "script_id": self.script_id,
            "scene_plan_id": self.scene_plan_id,
            "continuity_timeline_id": self.continuity_timeline_id,
            "continuity_through_sequence": self.continuity_through_sequence,
            "contracts": [contract.to_dict() for contract in self.contracts],
            "created_at": self.created_at.isoformat(),
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "ShotPlan":
        return ShotPlan(
            id=str(data["id"]),
            script_id=str(data["script_id"]),
            scene_plan_id=str(data["scene_plan_id"]),
            continuity_timeline_id=str(data["continuity_timeline_id"]),
            continuity_through_sequence=int(data["continuity_through_sequence"]),
            contracts=tuple(
                ShotContract.from_dict(contract) for contract in data.get("contracts", [])
            ),
            created_at=datetime.fromisoformat(str(data["created_at"])),
        )
