from dataclasses import dataclass, field
from typing import List, Dict, Any
from enum import Enum

class ReferenceView(str, Enum):
    FRONT = "FRONT"
    THREE_QUARTER_LEFT = "THREE_QUARTER_LEFT"
    PROFILE_LEFT = "PROFILE_LEFT"
    BACK = "BACK"
    PROFILE_RIGHT = "PROFILE_RIGHT"
    THREE_QUARTER_RIGHT = "THREE_QUARTER_RIGHT"
    FACE_CLOSEUP = "FACE_CLOSEUP"
    FULL_BODY = "FULL_BODY"

@dataclass(frozen=True)
class IdentityConstraints:
    eye_color: str
    hair: str
    facial_geometry: str
    body_proportions: str
    silhouette: str
    immutable_marks: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "eye_color": self.eye_color,
            "hair": self.hair,
            "facial_geometry": self.facial_geometry,
            "body_proportions": self.body_proportions,
            "silhouette": self.silhouette,
            "immutable_marks": self.immutable_marks
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IdentityConstraints":
        return cls(
            eye_color=data.get("eye_color", ""),
            hair=data.get("hair", ""),
            facial_geometry=data.get("facial_geometry", ""),
            body_proportions=data.get("body_proportions", ""),
            silhouette=data.get("silhouette", ""),
            immutable_marks=data.get("immutable_marks", [])
        )
