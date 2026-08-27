from dataclasses import dataclass
from typing import List, Dict, Any

@dataclass
class CharacterState:
    character_id: str
    active_outfit_id: str
    injuries: List[str]
    held_objects: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "character_id": self.character_id,
            "active_outfit_id": self.active_outfit_id,
            "injuries": self.injuries,
            "held_objects": self.held_objects,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CharacterState":
        return cls(
            character_id=data["character_id"],
            active_outfit_id=data["active_outfit_id"],
            injuries=data.get("injuries", []),
            held_objects=data.get("held_objects", []),
        )
