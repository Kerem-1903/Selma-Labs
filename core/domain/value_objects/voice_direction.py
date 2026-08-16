"""Provider-neutral narration direction derived from the approved script."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class VoiceDirection:
    profile: str
    speed: float
    stability: float
    style: float
    maximum_pause_ms: int
    hook_delivery: str
    explanation_delivery: str
    payoff_delivery: str

    def __post_init__(self) -> None:
        if self.profile not in {"mystery", "wonder", "energy", "documentary"}:
            raise ValueError("Unsupported voice direction profile.")
        if not 0.7 <= self.speed <= 1.2:
            raise ValueError("Voice direction speed must be between 0.7 and 1.2.")
        if not 0.0 <= self.stability <= 1.0 or not 0.0 <= self.style <= 1.0:
            raise ValueError("Voice direction stability and style must be between 0 and 1.")
        if self.maximum_pause_ms <= 0:
            raise ValueError("Voice direction pause budget must be positive.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "speed": self.speed,
            "stability": self.stability,
            "style": self.style,
            "maximum_pause_ms": self.maximum_pause_ms,
            "hook_delivery": self.hook_delivery,
            "explanation_delivery": self.explanation_delivery,
            "payoff_delivery": self.payoff_delivery,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "VoiceDirection":
        return VoiceDirection(
            profile=str(data["profile"]),
            speed=float(data["speed"]),
            stability=float(data["stability"]),
            style=float(data["style"]),
            maximum_pause_ms=int(data["maximum_pause_ms"]),
            hook_delivery=str(data["hook_delivery"]),
            explanation_delivery=str(data["explanation_delivery"]),
            payoff_delivery=str(data["payoff_delivery"]),
        )
