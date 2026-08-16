from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PremiumQualityCheck:
    name: str
    passed: bool
    details: str

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "details": self.details}


@dataclass(frozen=True)
class PremiumQualityReport:
    passed: bool
    checks: list[PremiumQualityCheck]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "checks": [check.to_dict() for check in self.checks],
        }
