from dataclasses import dataclass, field
from typing import List, Dict, Any
from enum import Enum

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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "score": self.score,
            "threshold": self.threshold,
            "passed": self.passed
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QCMetric":
        return cls(
            name=data["name"],
            score=data["score"],
            threshold=data["threshold"],
            passed=data["passed"]
        )

@dataclass(frozen=True)
class DetectedDefect:
    description: str
    frame_range: List[int]
    severity: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "description": self.description,
            "frame_range": self.frame_range,
            "severity": self.severity
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DetectedDefect":
        return cls(
            description=data["description"],
            frame_range=data.get("frame_range", []),
            severity=data.get("severity", "medium")
        )


@dataclass(frozen=True)
class QCReport:
    decision: QCDecision
    metrics: List[QCMetric] = field(default_factory=list)
    defects: List[DetectedDefect] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision": self.decision.value,
            "metrics": [m.to_dict() for m in self.metrics],
            "defects": [d.to_dict() for d in self.defects],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QCReport":
        return cls(
            decision=QCDecision(data["decision"]),
            metrics=[QCMetric.from_dict(m) for m in data.get("metrics", [])],
            defects=[DetectedDefect.from_dict(d) for d in data.get("defects", [])],
        )
