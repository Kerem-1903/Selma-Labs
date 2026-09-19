from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CameraConstraints:
    angle: str
    lens: str
    movement: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "angle": self.angle,
            "lens": self.lens,
            "movement": self.movement
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CameraConstraints":
        return cls(
            angle=data.get("angle", ""),
            lens=data.get("lens", ""),
            movement=data.get("movement", "")
        )

@dataclass(frozen=True)
class ActionConstraints:
    primary_action: str
    secondary_actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "primary_action": self.primary_action,
            "secondary_actions": self.secondary_actions
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ActionConstraints":
        return cls(
            primary_action=data.get("primary_action", ""),
            secondary_actions=data.get("secondary_actions", [])
        )

@dataclass(frozen=True)
class VisualConstraints:
    lighting: str
    environment_style: str
    weather: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "lighting": self.lighting,
            "environment_style": self.environment_style,
            "weather": self.weather
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VisualConstraints":
        return cls(
            lighting=data.get("lighting", ""),
            environment_style=data.get("environment_style", ""),
            weather=data.get("weather", "")
        )
