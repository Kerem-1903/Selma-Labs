"""Locked creative contract for the EŞİK//80 trailer."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from core.domain.exceptions import PreProductionValidationError


@dataclass(frozen=True)
class TrailerBrief:
    """Creative decisions that the trailer planner must not silently change."""

    trailer_id: str
    title: str = "EŞİK//80"
    fps: int = 24
    duration_seconds: int = 180
    narrator_enabled: bool = False
    system_voice_id: str = "MNEMOS"
    spoiler_policy: str = "PARTIAL_REVEAL"
    music_direction: str = "DARK_ELECTRONIC_ORCHESTRAL"
    title_card: str = "EŞİK//80"
    allowed_reveals: tuple[str, ...] = ("FHD-80", "LIMEN")
    hidden_reveals: tuple[str, ...] = (
        "LIMEN-80 human experimentation",
        "Varga responsibility",
        "Mina post-treatment condition",
        "season finale truth",
    )

    def __post_init__(self) -> None:
        if not self.trailer_id.strip() or not self.title.strip():
            raise PreProductionValidationError("Trailer identity and title are required.")
        if self.fps != 24 or self.duration_seconds != 180:
            raise PreProductionValidationError("Trailer brief requires exactly 180 seconds at 24 FPS.")
        if self.narrator_enabled:
            raise PreProductionValidationError("This trailer brief forbids an external narrator.")
        if self.system_voice_id != "MNEMOS":
            raise PreProductionValidationError("The locked trailer system voice is MNEMOS.")
        if self.spoiler_policy != "PARTIAL_REVEAL":
            raise PreProductionValidationError("Unsupported trailer spoiler policy.")
        if self.music_direction != "DARK_ELECTRONIC_ORCHESTRAL":
            raise PreProductionValidationError("Unsupported locked trailer music direction.")
        if self.title_card != "EŞİK//80":
            raise PreProductionValidationError("The locked trailer title card is EŞİK//80.")
        if not self.allowed_reveals or not self.hidden_reveals:
            raise PreProductionValidationError("Trailer spoiler policy requires reveal and hidden lists.")

    @property
    def duration_frames(self) -> int:
        return self.duration_seconds * self.fps

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "trailer_id": self.trailer_id,
            "title": self.title,
            "fps": self.fps,
            "duration_seconds": self.duration_seconds,
            "duration_frames": self.duration_frames,
            "narrator_enabled": self.narrator_enabled,
            "system_voice_id": self.system_voice_id,
            "spoiler_policy": self.spoiler_policy,
            "music_direction": self.music_direction,
            "title_card": self.title_card,
            "allowed_reveals": list(self.allowed_reveals),
            "hidden_reveals": list(self.hidden_reveals),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> TrailerBrief:
        return cls(
            trailer_id=str(data.get("trailer_id", "")),
            title=str(data.get("title", "EŞİK//80")),
            fps=int(data.get("fps", 24)),
            duration_seconds=int(data.get("duration_seconds", 180)),
            narrator_enabled=bool(data.get("narrator_enabled", False)),
            system_voice_id=str(data.get("system_voice_id", "MNEMOS")),
            spoiler_policy=str(data.get("spoiler_policy", "PARTIAL_REVEAL")),
            music_direction=str(data.get("music_direction", "DARK_ELECTRONIC_ORCHESTRAL")),
            title_card=str(data.get("title_card", "EŞİK//80")),
            allowed_reveals=tuple(str(item) for item in data.get("allowed_reveals", ("FHD-80", "LIMEN"))),
            hidden_reveals=tuple(str(item) for item in data.get("hidden_reveals", (
                "LIMEN-80 human experimentation", "Varga responsibility",
                "Mina post-treatment condition", "season finale truth",
            ))),
        )
