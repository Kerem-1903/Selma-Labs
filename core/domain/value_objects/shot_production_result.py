from __future__ import annotations

from dataclasses import dataclass

from core.domain.entities.shot_motion_clip import ShotMotionClip
from core.domain.value_objects.shot_production_attempt import ShotProductionAttempt


@dataclass(frozen=True)
class ShotProductionResult:
    clip: ShotMotionClip
    attempts: tuple[ShotProductionAttempt, ...]

    @property
    def total_estimated_cost_usd(self) -> float:
        return round(sum(item.estimated_cost_usd for item in self.attempts), 6)
