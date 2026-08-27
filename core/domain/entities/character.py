from dataclasses import dataclass, field
from typing import List, Dict, Any

@dataclass
class Character:
    id: str
    name: str
    face_identity_notes: str
    body_proportions: str
    hair: str = ""
    eye_color: str = ""
    silhouette: str = ""
    style_constraints: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "face_identity_notes": self.face_identity_notes,
            "body_proportions": self.body_proportions,
            "hair": self.hair,
            "eye_color": self.eye_color,
            "silhouette": self.silhouette,
            "style_constraints": self.style_constraints,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Character":
        return cls(
            id=data["id"],
            name=data["name"],
            face_identity_notes=data.get("face_identity_notes", ""),
            body_proportions=data.get("body_proportions", ""),
            hair=data.get("hair", ""),
            eye_color=data.get("eye_color", ""),
            silhouette=data.get("silhouette", ""),
            style_constraints=data.get("style_constraints", []),
        )
