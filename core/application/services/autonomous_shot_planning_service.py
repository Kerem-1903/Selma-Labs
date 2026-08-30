from __future__ import annotations

from core.domain.entities.scene_plan import ScenePlan
from core.domain.entities.script import Script
from core.domain.entities.shot_plan import ShotPlan
from core.domain.exceptions import AutonomousShotPlanningError
from core.domain.ports.continuity_repository_port import ContinuityRepositoryPort
from core.domain.services.continuity_reducer import ContinuityReducer
from core.domain.services.shot_contract_builder_service import (
    ShotContractBuilderService,
)


class AutonomousShotPlanningService:
    """Build typed shot contracts without changing legacy scene planning."""

    def __init__(
        self,
        continuity_repository: ContinuityRepositoryPort,
        contract_builder: ShotContractBuilderService | None = None,
    ) -> None:
        self._continuity_repository = continuity_repository
        self._contract_builder = contract_builder or ShotContractBuilderService()

    async def plan(
        self,
        *,
        script: Script,
        scene_plan: ScenePlan,
        continuity_timeline_id: str,
    ) -> ShotPlan:
        if scene_plan.script_id != script.id:
            raise AutonomousShotPlanningError(
                "ScenePlan does not belong to the supplied Script."
            )
        if not scene_plan.scenes:
            raise AutonomousShotPlanningError("ScenePlan contains no scenes.")

        initial_state = await self._continuity_repository.load(continuity_timeline_id)
        events = await self._continuity_repository.load_events(continuity_timeline_id)
        sequences = [event.sequence for event in events]
        if len(sequences) != len(set(sequences)):
            raise AutonomousShotPlanningError(
                "Continuity events contain duplicate sequence numbers."
            )
        if any(sequence < 0 for sequence in sequences):
            raise AutonomousShotPlanningError(
                "Continuity events contain a negative sequence number."
            )

        through_sequence = max(sequences, default=0)
        snapshot = ContinuityReducer.replay(initial_state, events)
        contracts = tuple(
            self._contract_builder.build(
                script=script,
                scene=scene,
                continuity_state=snapshot,
                continuity_through_sequence=through_sequence,
            )
            for scene in scene_plan.scenes
        )
        return ShotPlan.create(
            script_id=script.id,
            scene_plan_id=scene_plan.id,
            continuity_timeline_id=continuity_timeline_id,
            continuity_through_sequence=through_sequence,
            contracts=contracts,
        )
