from __future__ import annotations

from core.application.services.script_breakdown_service import ScriptBreakdownService
from core.domain.entities.episode_production_plan import (
    DirectedShot,
    EpisodeProductionPlan,
    ProductionScene,
    ProductionSequence,
)
from core.domain.entities.episode_script import EpisodeScript, EpisodeScriptStatus
from core.domain.exceptions import StoryApprovalError


class HierarchicalShotPlanningService:
    def __init__(self, breakdown: ScriptBreakdownService | None = None) -> None:
        self._breakdown = breakdown or ScriptBreakdownService()

    def plan(self, script: EpisodeScript) -> EpisodeProductionPlan:
        if script.status is not EpisodeScriptStatus.LOCKED:
            raise StoryApprovalError(
                "Hierarchical planning requires a locked episode script."
            )
        flat = self._breakdown.parse_episode(script)
        cursor = 0
        sequences: list[ProductionSequence] = []
        for sequence in script.sequences:
            scenes: list[ProductionScene] = []
            for scene in sequence.scenes:
                count = 1 + len(scene.dialogue)
                scene_shots = flat[cursor : cursor + count]
                cursor += count
                directed = tuple(
                    self._direct(shot, is_dialogue=index > 0)
                    for index, shot in enumerate(scene_shots)
                )
                scenes.append(
                    ProductionScene(scene.id, scene.title, scene.location, directed)
                )
            sequences.append(
                ProductionSequence(sequence.id, sequence.title, tuple(scenes))
            )
        if cursor != len(flat):
            raise RuntimeError(
                "Script breakdown and hierarchy produced different shot counts."
            )
        return EpisodeProductionPlan.create(
            episode_script_id=script.id,
            episode_revision=script.revision,
            sequences=tuple(sequences),
        )

    @staticmethod
    def _direct(shot, *, is_dialogue: bool) -> DirectedShot:
        text = f"{shot.prompt} {shot.dialogue}".casefold()
        effects = tuple(
            effect
            for keyword, effect in (
                ("rain", "rain"),
                ("wind", "wind"),
                ("katana", "katana_glint"),
                ("signal", "memory_signal"),
            )
            if keyword in text
        )
        if is_dialogue:
            return DirectedShot(
                shot,
                "close_up",
                "locked_off",
                "speaker settles before the line",
                "hold reaction for editorial cut",
                effects,
            )
        return DirectedShot(
            shot,
            "wide",
            "slow_push_in",
            "establish readable silhouettes and geography",
            "land on the scene's dramatic subject",
            effects,
        )
