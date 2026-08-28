from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from .character_state import CharacterState
from core.domain.value_objects.shot_constraints import CameraConstraints, ActionConstraints, VisualConstraints

@dataclass
class ShotContract:
    id: str
    camera_constraints: CameraConstraints
    action_constraints: ActionConstraints
    visual_constraints: VisualConstraints
    required_character_states: List[CharacterState] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "camera_constraints": self.camera_constraints.to_dict(),
            "action_constraints": self.action_constraints.to_dict(),
            "visual_constraints": self.visual_constraints.to_dict(),
            "required_character_states": [
                state.to_dict() for state in self.required_character_states
            ]
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ShotContract":
        states = [
            CharacterState.from_dict(state_data)
            for state_data in data.get("required_character_states", [])
        ]
        return cls(
            id=data["id"],
            camera_constraints=CameraConstraints.from_dict(data.get("camera_constraints", {})),
            action_constraints=ActionConstraints.from_dict(data.get("action_constraints", {})),
            visual_constraints=VisualConstraints.from_dict(data.get("visual_constraints", {})),
            required_character_states=states
        )
