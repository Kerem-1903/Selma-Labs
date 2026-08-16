"""Mobile caption safe-zone policy and deterministic QA artifacts."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CaptionSafeZoneProfile:
    name: str = "youtube_shorts"
    canvas_width: int = 1080
    canvas_height: int = 1920
    margin_left: int = 120
    margin_right: int = 120
    caption_baseline_y: int = 1420
    unsafe_top: int = 180
    unsafe_bottom: int = 360
    font_size: int = 68
    outline_width: int = 6
    active_scale_percent: int = 106
    minimum_scaled_emphasis_ms: int = 160

    def __post_init__(self) -> None:
        if self.canvas_width <= 0 or self.canvas_height <= 0:
            raise ValueError("Caption canvas dimensions must be positive.")
        if self.margin_left < 0 or self.margin_right < 0 or self.safe_width <= 0:
            raise ValueError("Caption horizontal safe-zone margins are invalid.")
        if not 104 <= self.active_scale_percent <= 106:
            raise ValueError("Caption active scale must be between 104 and 106 percent.")
        if self.minimum_scaled_emphasis_ms <= 0:
            raise ValueError("Caption emphasis duration must be positive.")

    @property
    def safe_width(self) -> int:
        return self.canvas_width - self.margin_left - self.margin_right


@dataclass(frozen=True)
class CaptionPreviewSample:
    kind: str
    cue_index: int
    timestamp_ms: int
    text: str
    styled_width: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "cue_index": self.cue_index,
            "timestamp_ms": self.timestamp_ms,
            "text": self.text,
            "styled_width": round(self.styled_width, 2),
        }


@dataclass(frozen=True)
class CaptionUxReport:
    profile_name: str
    safe_width: int
    maximum_styled_width: float
    hard_boundary_violations: tuple[int, ...]
    horizontal_overflow_cues: tuple[int, ...]
    vertical_overflow_cues: tuple[int, ...]
    short_words_without_scale: tuple[str, ...]
    preview_samples: tuple[CaptionPreviewSample, ...]
    score: float

    @property
    def passed(self) -> bool:
        return not (
            self.hard_boundary_violations
            or self.horizontal_overflow_cues
            or self.vertical_overflow_cues
        ) and self.score >= 9.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_name": self.profile_name,
            "safe_width": self.safe_width,
            "maximum_styled_width": round(self.maximum_styled_width, 2),
            "hard_boundary_violations": list(self.hard_boundary_violations),
            "horizontal_overflow_cues": list(self.horizontal_overflow_cues),
            "vertical_overflow_cues": list(self.vertical_overflow_cues),
            "short_words_without_scale": list(self.short_words_without_scale),
            "preview_samples": [sample.to_dict() for sample in self.preview_samples],
            "score": self.score,
            "passed": self.passed,
        }
