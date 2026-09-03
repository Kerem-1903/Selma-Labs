"""Provider-neutral quality evidence for generated pre-production images."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PreproductionImageQuality:
    score: float
    threshold: float
    passed: bool
    identity_or_geometry_score: float
    composition_score: float
    subject_policy_score: float
    confidence: float
    issues: tuple[str, ...] = ()
    provider: str = ""

    def __post_init__(self) -> None:
        values = (
            self.score,
            self.threshold,
            self.identity_or_geometry_score,
            self.composition_score,
            self.subject_policy_score,
            self.confidence,
        )
        if any(not 0.0 <= value <= 1.0 for value in values):
            raise ValueError("Pre-production quality scores must be between 0 and 1.")
        if self.passed != (self.score >= self.threshold and not self.issues):
            raise ValueError("Quality pass state does not match score and issues.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": round(self.score, 4),
            "threshold": self.threshold,
            "passed": self.passed,
            "identity_or_geometry_score": round(self.identity_or_geometry_score, 4),
            "composition_score": round(self.composition_score, 4),
            "subject_policy_score": round(self.subject_policy_score, 4),
            "confidence": round(self.confidence, 4),
            "issues": list(self.issues),
            "provider": self.provider,
        }
