"""Evidence-backed creative readiness for a finished Short."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CreativeQualityCheck:
    name: str
    category: str
    earned_points: int
    maximum_points: int
    passed: bool
    blocking: bool
    evidence: str
    remediation: str | None = None
    timestamp_seconds: float | None = None

    def __post_init__(self) -> None:
        if self.maximum_points <= 0:
            raise ValueError("Creative quality checks need a positive point budget.")
        if not 0 <= self.earned_points <= self.maximum_points:
            raise ValueError("Earned points must stay inside the check point budget.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category,
            "earned_points": self.earned_points,
            "maximum_points": self.maximum_points,
            "passed": self.passed,
            "blocking": self.blocking,
            "evidence": self.evidence,
            "remediation": self.remediation,
            "timestamp_seconds": self.timestamp_seconds,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "CreativeQualityCheck":
        return CreativeQualityCheck(
            name=str(data["name"]),
            category=str(data["category"]),
            earned_points=int(data["earned_points"]),
            maximum_points=int(data["maximum_points"]),
            passed=bool(data["passed"]),
            blocking=bool(data["blocking"]),
            evidence=str(data["evidence"]),
            remediation=(str(data["remediation"]) if data.get("remediation") else None),
            timestamp_seconds=(
                float(data["timestamp_seconds"])
                if data.get("timestamp_seconds") is not None
                else None
            ),
        )


@dataclass(frozen=True)
class CreativeQualityReport:
    score: int
    maximum_score: int
    ready_to_upload: bool
    premium_approved: bool
    automatic_threshold: int
    premium_threshold: int
    checks: tuple[CreativeQualityCheck, ...]
    human_creative_approval: bool | None = None
    voice_naturalness_score: int | None = None

    def __post_init__(self) -> None:
        if self.maximum_score != sum(check.maximum_points for check in self.checks):
            raise ValueError("Creative quality point budgets must add up to maximum_score.")
        if self.score != sum(check.earned_points for check in self.checks):
            raise ValueError("Creative quality score must equal the sum of earned points.")
        if self.voice_naturalness_score is not None and not 1 <= self.voice_naturalness_score <= 5:
            raise ValueError("Voice naturalness score must be between 1 and 5.")

    @property
    def blocking_failures(self) -> tuple[CreativeQualityCheck, ...]:
        return tuple(check for check in self.checks if check.blocking and not check.passed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "maximum_score": self.maximum_score,
            "ready_to_upload": self.ready_to_upload,
            "premium_approved": self.premium_approved,
            "automatic_threshold": self.automatic_threshold,
            "premium_threshold": self.premium_threshold,
            "blocking_failures": [check.name for check in self.blocking_failures],
            "human_review": {
                "creative_approval": self.human_creative_approval,
                "voice_naturalness_score": self.voice_naturalness_score,
                "required_for_premium": True,
            },
            "checks": [check.to_dict() for check in self.checks],
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "CreativeQualityReport":
        human_review = dict(data.get("human_review") or {})
        return CreativeQualityReport(
            score=int(data["score"]),
            maximum_score=int(data["maximum_score"]),
            ready_to_upload=bool(data["ready_to_upload"]),
            premium_approved=bool(data["premium_approved"]),
            automatic_threshold=int(data["automatic_threshold"]),
            premium_threshold=int(data["premium_threshold"]),
            checks=tuple(
                CreativeQualityCheck.from_dict(dict(item))
                for item in data.get("checks", [])
            ),
            human_creative_approval=(
                bool(human_review["creative_approval"])
                if human_review.get("creative_approval") is not None
                else None
            ),
            voice_naturalness_score=(
                int(human_review["voice_naturalness_score"])
                if human_review.get("voice_naturalness_score") is not None
                else None
            ),
        )
