from __future__ import annotations

import copy
import uuid

from core.domain.entities.continuity_state import ContinuityState
from core.domain.entities.script import Script
from core.domain.entities.shot_contract import ShotContract
from core.domain.exceptions import AutonomousShotPlanningError
from core.domain.value_objects.scene import Scene
from core.domain.value_objects.shot_constraints import (
    ActionConstraints,
    CameraConstraints,
    VisualConstraints,
)


class ShotContractBuilderService:
    """Deterministically turn story evidence and continuity into a contract."""

    _CAMERA_GRAMMAR = {
        "high": CameraConstraints("low-angle", "24mm", "tracking"),
        "medium": CameraConstraints("eye-level", "35mm", "controlled-dolly"),
        "low": CameraConstraints("eye-level", "50mm", "static"),
    }

    def build(
        self,
        *,
        script: Script,
        scene: Scene,
        continuity_state: ContinuityState,
        continuity_through_sequence: int,
    ) -> ShotContract:
        narrative_evidence = scene.narration.strip()
        if not narrative_evidence:
            raise AutonomousShotPlanningError("A shot requires narrative evidence.")
        if continuity_through_sequence < 0:
            raise AutonomousShotPlanningError(
                "Continuity sequence cannot be negative."
            )

        character_states = self._required_character_states(scene, continuity_state)
        object_states = self._required_object_states(
            scene,
            continuity_state,
            character_states,
        )
        camera = self._CAMERA_GRAMMAR.get(
            scene.visual_priority.casefold(),
            self._CAMERA_GRAMMAR["medium"],
        )
        actions = tuple(action.strip() for action in scene.required_actions if action.strip())
        primary_action = actions[0] if actions else scene.visual_job.replace("_", " ")

        return ShotContract(
            id=str(uuid.uuid4()),
            camera_constraints=camera,
            action_constraints=ActionConstraints(
                primary_action=primary_action,
                secondary_actions=list(actions[1:]),
            ),
            visual_constraints=VisualConstraints(
                lighting=self._lighting_for(scene.mood),
                environment_style=(scene.location or "unspecified").strip()
                or "unspecified",
                weather="unspecified",
            ),
            required_character_states=character_states,
            required_object_states=object_states,
            script_id=script.id,
            scene_index=scene.index,
            continuity_snapshot_id=continuity_state.id,
            continuity_through_sequence=continuity_through_sequence,
            narrative_evidence=narrative_evidence,
        )

    @staticmethod
    def _required_character_states(
        scene: Scene,
        continuity_state: ContinuityState,
    ) -> list:
        requested = {subject.casefold() for subject in scene.required_subjects}
        matched = [
            state
            for character_id, state in continuity_state.world_snapshot.items()
            if character_id.casefold() in requested
        ]
        if not matched and scene.location:
            matched = [
                state
                for state in continuity_state.world_snapshot.values()
                if state.location.casefold() == scene.location.casefold()
            ]
        return copy.deepcopy(matched)

    @staticmethod
    def _required_object_states(
        scene: Scene,
        continuity_state: ContinuityState,
        character_states: list,
    ) -> dict[str, str]:
        requested = {
            subject.casefold()
            for subject in (*scene.required_subjects, *scene.detected_objects)
        }
        held_objects = {
            object_id
            for character in character_states
            for object_id in character.held_objects
        }
        return {
            object_id: state
            for object_id, state in continuity_state.object_states.items()
            if object_id.casefold() in requested or object_id in held_objects
        }

    @staticmethod
    def _lighting_for(mood: str | None) -> str:
        normalized = (mood or "").casefold()
        if any(token in normalized for token in ("dark", "tense", "fear", "night")):
            return "low-key"
        if any(token in normalized for token in ("hope", "warm", "joy")):
            return "soft-directional"
        return "natural-cinematic"
