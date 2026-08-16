"""Deterministic visual-edit decisions derived from a semantic storyboard."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class VisualEditBeat:
    """One editorial beat and the reason for every visible treatment."""

    index: int
    start_ms: int
    end_ms: int
    purpose: str
    shot_type: str
    motion_type: str
    transition: str
    pattern_interrupt: str
    explanation_mode: str
    safe_zone: str = "center_subject_caption_clear"

    def __post_init__(self) -> None:
        if self.index < 0 or self.start_ms < 0 or self.end_ms <= self.start_ms:
            raise ValueError("Visual edit beat timing is invalid.")
        if self.transition not in {
            "hard", "push", "match_zoom", "mask_reveal", "impact_flash"
        }:
            raise ValueError("Visual edit beat transition is unsupported.")

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "duration_ms": self.duration_ms,
            "purpose": self.purpose,
            "shot_type": self.shot_type,
            "motion_type": self.motion_type,
            "transition": self.transition,
            "pattern_interrupt": self.pattern_interrupt,
            "explanation_mode": self.explanation_mode,
            "safe_zone": self.safe_zone,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "VisualEditBeat":
        return VisualEditBeat(
            index=int(data["index"]),
            start_ms=int(data["start_ms"]),
            end_ms=int(data["end_ms"]),
            purpose=str(data["purpose"]),
            shot_type=str(data["shot_type"]),
            motion_type=str(data["motion_type"]),
            transition=str(data["transition"]),
            pattern_interrupt=str(data["pattern_interrupt"]),
            explanation_mode=str(data["explanation_mode"]),
            safe_zone=str(data.get("safe_zone") or "center_subject_caption_clear"),
        )


@dataclass(frozen=True)
class VisualEditPlan:
    """Machine-readable edit grammar used by render and quality control."""

    beats: tuple[VisualEditBeat, ...]
    format_name: str
    maximum_visual_hold_ms: int
    maximum_pattern_interrupt_gap_ms: int
    expected_cut_count: int
    non_hard_transition_budget: int

    def __post_init__(self) -> None:
        if not self.beats:
            raise ValueError("Visual edit plan requires at least one beat.")
        if self.maximum_visual_hold_ms <= 0 or self.maximum_pattern_interrupt_gap_ms <= 0:
            raise ValueError("Visual edit plan timing budgets must be positive.")
        if self.expected_cut_count != max(0, len(self.beats) - 1):
            raise ValueError("Visual edit plan cut count must match its beats.")
        if self.non_hard_transition_budget < 0:
            raise ValueError("Visual edit transition budget must not be negative.")

    @property
    def duration_ms(self) -> int:
        return self.beats[-1].end_ms - self.beats[0].start_ms

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "format_name": self.format_name,
            "duration_ms": self.duration_ms,
            "maximum_visual_hold_ms": self.maximum_visual_hold_ms,
            "maximum_pattern_interrupt_gap_ms": self.maximum_pattern_interrupt_gap_ms,
            "expected_cut_count": self.expected_cut_count,
            "non_hard_transition_budget": self.non_hard_transition_budget,
            "beats": [beat.to_dict() for beat in self.beats],
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "VisualEditPlan":
        return VisualEditPlan(
            beats=tuple(
                VisualEditBeat.from_dict(dict(item))
                for item in data.get("beats", [])
            ),
            format_name=str(data.get("format_name") or "shorts"),
            maximum_visual_hold_ms=int(data.get("maximum_visual_hold_ms", 2_800)),
            maximum_pattern_interrupt_gap_ms=int(
                data.get("maximum_pattern_interrupt_gap_ms", 8_000)
            ),
            expected_cut_count=int(data.get("expected_cut_count", 0)),
            non_hard_transition_budget=int(
                data.get("non_hard_transition_budget", 0)
            ),
        )
