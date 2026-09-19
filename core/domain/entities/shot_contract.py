from dataclasses import dataclass, field
from typing import Any

from core.domain.value_objects.shot_constraints import (
    ActionConstraints,
    CameraConstraints,
    VisualConstraints,
)

from .character_state import CharacterState


@dataclass
class ShotContract:
    id: str
    camera_constraints: CameraConstraints
    action_constraints: ActionConstraints
    visual_constraints: VisualConstraints
    required_character_states: list[CharacterState] = field(default_factory=list)
    required_object_states: dict[str, str] = field(default_factory=dict)
    script_id: str | None = None
    scene_index: int | None = None
    continuity_snapshot_id: str | None = None
    continuity_through_sequence: int = 0
    narrative_evidence: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "camera_constraints": self.camera_constraints.to_dict(),
            "action_constraints": self.action_constraints.to_dict(),
            "visual_constraints": self.visual_constraints.to_dict(),
            "required_character_states": [
                state.to_dict() for state in self.required_character_states
            ],
            "required_object_states": dict(self.required_object_states),
            "script_id": self.script_id,
            "scene_index": self.scene_index,
            "continuity_snapshot_id": self.continuity_snapshot_id,
            "continuity_through_sequence": self.continuity_through_sequence,
            "narrative_evidence": self.narrative_evidence,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ShotContract":
        states = [
            CharacterState.from_dict(state_data)
            for state_data in data.get("required_character_states", [])
        ]
        return cls(
            id=data["id"],
            camera_constraints=CameraConstraints.from_dict(data.get("camera_constraints", {})),
            action_constraints=ActionConstraints.from_dict(data.get("action_constraints", {})),
            visual_constraints=VisualConstraints.from_dict(data.get("visual_constraints", {})),
            required_character_states=states,
            required_object_states=dict(data.get("required_object_states", {})),
            script_id=data.get("script_id"),
            scene_index=data.get("scene_index"),
            continuity_snapshot_id=data.get("continuity_snapshot_id"),
            continuity_through_sequence=int(data.get("continuity_through_sequence", 0)),
            narrative_evidence=str(data.get("narrative_evidence", "")),
        )
