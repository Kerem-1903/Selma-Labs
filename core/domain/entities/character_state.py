from dataclasses import dataclass, field
from typing import Any


@dataclass
class CharacterState:
    character_id: str
    active_outfit_id: str
    injuries: list[str]
    held_objects: list[str]
    character_version: int = 1
    location: str = ""
    emotion: str = ""
    outfit_damage: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "character_id": self.character_id,
            "active_outfit_id": self.active_outfit_id,
            "injuries": self.injuries,
            "held_objects": self.held_objects,
            "character_version": self.character_version,
            "location": self.location,
            "emotion": self.emotion,
            "outfit_damage": self.outfit_damage,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CharacterState":
        return cls(
            character_id=data["character_id"],
            active_outfit_id=data["active_outfit_id"],
            injuries=data.get("injuries", []),
            held_objects=data.get("held_objects", []),
            character_version=int(data.get("character_version", 1)),
            location=data.get("location", ""),
            emotion=data.get("emotion", ""),
            outfit_damage=data.get("outfit_damage", {}),
        )
