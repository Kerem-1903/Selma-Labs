from dataclasses import dataclass
from typing import Dict, Any

@dataclass
class Character:
    id: str
    name: str
    face_identity_notes: str
    body_proportions: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "face_identity_notes": self.face_identity_notes,
            "body_proportions": self.body_proportions,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Character":
        return cls(
            id=data["id"],
            name=data["name"],
            face_identity_notes=data.get("face_identity_notes", ""),
            body_proportions=data.get("body_proportions", ""),
        )
