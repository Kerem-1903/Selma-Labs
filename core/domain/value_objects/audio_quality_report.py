"""A dedicated 100-point release gate for the completed audio master."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AudioQualityCheck:
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
    def from_dict(data: dict[str, Any]) -> "AudioQualityCheck":
        return AudioQualityCheck(
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
class AudioQualityReport:
    score: int
    threshold: int
    passed: bool
    checks: tuple[AudioQualityCheck, ...]

    def __post_init__(self) -> None:
        if sum(check.maximum_points for check in self.checks) != 100:
            raise ValueError("Audio quality checks must add up to 100 points.")
        if self.score != sum(check.earned_points for check in self.checks):
            raise ValueError("Audio quality score must equal earned check points.")
        expected_pass = self.score >= self.threshold and not any(
            check.blocking and not check.passed for check in self.checks
        )
        if self.passed != expected_pass:
            raise ValueError("Audio quality pass state does not match score and blockers.")

    @property
    def score_out_of_ten(self) -> float:
        return round(self.score / 10, 1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "maximum_score": 100,
            "score_out_of_ten": self.score_out_of_ten,
            "threshold": self.threshold,
            "passed": self.passed,
            "blocking_failures": [
                check.name for check in self.checks if check.blocking and not check.passed
            ],
            "checks": [check.to_dict() for check in self.checks],
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "AudioQualityReport":
        return AudioQualityReport(
            score=int(data["score"]),
            threshold=int(data.get("threshold", 90)),
            passed=bool(data["passed"]),
            checks=tuple(
                AudioQualityCheck.from_dict(dict(item))
                for item in data.get("checks", [])
            ),
        )
