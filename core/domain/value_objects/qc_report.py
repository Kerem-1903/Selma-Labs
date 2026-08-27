from dataclasses import dataclass
from typing import List, Dict, Any

@dataclass(frozen=True)
class QCReport:
    decision: str  # PASS / REJECT / REPAIR
    metrics: Dict[str, Any]
    defects: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision": self.decision,
            "metrics": self.metrics,
            "defects": self.defects,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QCReport":
        return cls(
            decision=data["decision"],
            metrics=data.get("metrics", {}),
            defects=data.get("defects", []),
        )
