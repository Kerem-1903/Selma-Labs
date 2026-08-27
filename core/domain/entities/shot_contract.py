from dataclasses import dataclass, field
from typing import List, Dict, Any
from .character_state import CharacterState

@dataclass
class ShotContract:
    id: str
    camera_constraints: str
    action_constraints: str
    visual_constraints: str
    required_character_states: List[CharacterState] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "camera_constraints": self.camera_constraints,
            "action_constraints": self.action_constraints,
            "visual_constraints": self.visual_constraints,
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
            camera_constraints=data.get("camera_constraints", ""),
            action_constraints=data.get("action_constraints", ""),
            visual_constraints=data.get("visual_constraints", ""),
            required_character_states=states
        )
