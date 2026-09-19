from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class QCDecision(str, Enum):
    PASS = "PASS"
    REPAIR_SEGMENT = "REPAIR_SEGMENT"
    REGENERATE_SHOT = "REGENERATE_SHOT"
    MANUAL_REVIEW = "MANUAL_REVIEW"

@dataclass(frozen=True)
class QCMetric:
    name: str
    score: float
    threshold: float
    passed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "score": self.score,
            "threshold": self.threshold,
            "passed": self.passed
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QCMetric":
        return cls(
            name=data["name"],
            score=data["score"],
            threshold=data["threshold"],
            passed=data["passed"]
        )

@dataclass(frozen=True)
class DetectedDefect:
    description: str
    frame_range: list[int]
    severity: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "description": self.description,
            "frame_range": self.frame_range,
            "severity": self.severity
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DetectedDefect":
        return cls(
            description=data["description"],
            frame_range=data.get("frame_range", []),
            severity=data.get("severity", "medium")
        )


@dataclass(frozen=True)
class QCReport:
    decision: QCDecision
    metrics: list[QCMetric] = field(default_factory=list)
    defects: list[DetectedDefect] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "metrics": [m.to_dict() for m in self.metrics],
            "defects": [d.to_dict() for d in self.defects],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QCReport":
        return cls(
            decision=QCDecision(data["decision"]),
            metrics=[QCMetric.from_dict(m) for m in data.get("metrics", [])],
            defects=[DetectedDefect.from_dict(d) for d in data.get("defects", [])],
        )
