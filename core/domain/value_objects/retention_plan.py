"""Source-grounded viewer-retention plan produced before voice generation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.domain.value_objects.hook_variant import HookExperiment
from core.domain.value_objects.youtube_performance import PerformanceGuidance


@dataclass(frozen=True)
class RetentionSecond:
    """The editorial job assigned to one second of the opening."""

    second: int
    beat_index: int
    narrative_role: str
    purpose: str
    visual_change: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "second": self.second,
            "beat_index": self.beat_index,
            "narrative_role": self.narrative_role,
            "purpose": self.purpose,
            "visual_change": self.visual_change,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "RetentionSecond":
        return RetentionSecond(
            second=int(data["second"]),
            beat_index=int(data["beat_index"]),
            narrative_role=str(data["narrative_role"]),
            purpose=str(data["purpose"]),
            visual_change=str(data["visual_change"]),
        )


@dataclass(frozen=True)
class PatternInterrupt:
    """A purposeful visual or narrative reset in longer videos."""

    timestamp_seconds: int
    change_type: str
    purpose: str
    mascot_action: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp_seconds": self.timestamp_seconds,
            "change_type": self.change_type,
            "purpose": self.purpose,
            "mascot_action": self.mascot_action,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "PatternInterrupt":
        return PatternInterrupt(
            timestamp_seconds=int(data["timestamp_seconds"]),
            change_type=str(data["change_type"]),
            purpose=str(data["purpose"]),
            mascot_action=(
                str(data["mascot_action"]) if data.get("mascot_action") else None
            ),
        )


@dataclass(frozen=True)
class RetentionPlan:
    """Complete pre-production retention contract for one script."""

    content_format: str
    target_duration_seconds: int
    hook_experiment: HookExperiment
    production_hook: str
    first_30_seconds: tuple[RetentionSecond, ...]
    pattern_interrupts: tuple[PatternInterrupt, ...]
    comment_question: str
    passed: bool
    performance_guidance: PerformanceGuidance | None = None
    issues: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.content_format not in {"short", "long"}:
            raise ValueError("content_format must be short or long.")
        if self.target_duration_seconds <= 0:
            raise ValueError("target_duration_seconds must be positive.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "content_format": self.content_format,
            "target_duration_seconds": self.target_duration_seconds,
            "hook_experiment": self.hook_experiment.to_dict(),
            "production_hook": self.production_hook,
            "first_30_seconds": [item.to_dict() for item in self.first_30_seconds],
            "pattern_interrupts": [item.to_dict() for item in self.pattern_interrupts],
            "comment_question": self.comment_question,
            "passed": self.passed,
            "performance_guidance": (
                self.performance_guidance.to_dict()
                if self.performance_guidance is not None
                else None
            ),
            "issues": list(self.issues),
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "RetentionPlan":
        return RetentionPlan(
            content_format=str(data["content_format"]),
            target_duration_seconds=int(data["target_duration_seconds"]),
            hook_experiment=HookExperiment.from_dict(dict(data["hook_experiment"])),
            production_hook=str(data["production_hook"]),
            first_30_seconds=tuple(
                RetentionSecond.from_dict(dict(item))
                for item in data.get("first_30_seconds", [])
            ),
            pattern_interrupts=tuple(
                PatternInterrupt.from_dict(dict(item))
                for item in data.get("pattern_interrupts", [])
            ),
            comment_question=str(data["comment_question"]),
            passed=bool(data["passed"]),
            performance_guidance=(
                PerformanceGuidance.from_dict(dict(data["performance_guidance"]))
                if data.get("performance_guidance")
                else None
            ),
            issues=tuple(str(item) for item in data.get("issues", [])),
        )
