from dataclasses import dataclass, field
from enum import Enum
from typing import Any


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
    trigger_prompt: str = ""
    immutable_marks: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "eye_color": self.eye_color,
            "hair": self.hair,
            "facial_geometry": self.facial_geometry,
            "body_proportions": self.body_proportions,
            "silhouette": self.silhouette,
            "trigger_prompt": self.trigger_prompt,
            "immutable_marks": self.immutable_marks
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IdentityConstraints":
        return cls(
            eye_color=data.get("eye_color", ""),
            hair=data.get("hair", ""),
            facial_geometry=data.get("facial_geometry", ""),
            body_proportions=data.get("body_proportions", ""),
            silhouette=data.get("silhouette", ""),
            trigger_prompt=data.get("trigger_prompt", ""),
            immutable_marks=data.get("immutable_marks", [])
        )
