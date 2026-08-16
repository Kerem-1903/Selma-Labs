"""A dedicated 100-point release gate for the completed visual edit."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class VisualQualityCheck:
    name: str
    category: str
    earned_points: int
    maximum_points: int
    passed: bool
    blocking: bool
    evidence: str
    remediation: str | None = None

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
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "VisualQualityCheck":
        return VisualQualityCheck(
            name=str(data["name"]),
            category=str(data["category"]),
            earned_points=int(data["earned_points"]),
            maximum_points=int(data["maximum_points"]),
            passed=bool(data["passed"]),
            blocking=bool(data["blocking"]),
            evidence=str(data["evidence"]),
            remediation=str(data["remediation"]) if data.get("remediation") else None,
        )


@dataclass(frozen=True)
class VisualQualityReport:
    score: int
    threshold: int
    passed: bool
    checks: tuple[VisualQualityCheck, ...]
    human_taste_score: int | None = None

    def __post_init__(self) -> None:
        if sum(check.maximum_points for check in self.checks) != 90:
            raise ValueError("Automatic visual quality checks must add up to 90 points.")
        automatic_score = sum(check.earned_points for check in self.checks)
        human_score = self.human_taste_score or 0
        if self.human_taste_score is not None and not 0 <= self.human_taste_score <= 10:
            raise ValueError("Human visual taste score must be between 0 and 10.")
        if self.score != automatic_score + human_score:
            raise ValueError("Visual quality score must equal automatic and human points.")
        expected_pass = automatic_score >= self.threshold and not any(
            check.blocking and not check.passed for check in self.checks
        )
        if self.passed != expected_pass:
            raise ValueError("Visual quality pass state does not match score and blockers.")

    @property
    def automatic_score(self) -> int:
        return sum(check.earned_points for check in self.checks)

    @property
    def score_out_of_ten(self) -> float:
        return round(self.score / 10, 1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "automatic_score": self.automatic_score,
            "human_taste_score": self.human_taste_score,
            "maximum_score": 100,
            "score_out_of_ten": self.score_out_of_ten,
            "threshold": self.threshold,
            "passed": self.passed,
            "studio_approved": self.passed and (self.human_taste_score or 0) >= 8,
            "blocking_failures": [
                check.name for check in self.checks if check.blocking and not check.passed
            ],
            "checks": [check.to_dict() for check in self.checks],
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "VisualQualityReport":
        return VisualQualityReport(
            score=int(data["score"]),
            threshold=int(data.get("threshold", 90)),
            passed=bool(data["passed"]),
            checks=tuple(
                VisualQualityCheck.from_dict(dict(item))
                for item in data.get("checks", [])
            ),
            human_taste_score=(
                int(data["human_taste_score"])
                if data.get("human_taste_score") is not None
                else None
            ),
        )
