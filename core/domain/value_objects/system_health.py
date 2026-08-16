"""Safe, secret-free production preflight evidence."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SystemHealthCheck:
    name: str
    status: str
    required: bool
    details: str
    remediation: str | None = None

    def __post_init__(self) -> None:
        if self.status not in {"PASS", "WARN", "FAIL"}:
            raise ValueError("System health status must be PASS, WARN, or FAIL.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "required": self.required,
            "details": self.details,
            "remediation": self.remediation,
        }


@dataclass(frozen=True)
class SystemHealthReport:
    profile: str
    ready: bool
    checks: tuple[SystemHealthCheck, ...]

    @property
    def failures(self) -> tuple[SystemHealthCheck, ...]:
        return tuple(
            check for check in self.checks
            if check.required and check.status == "FAIL"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "ready": self.ready,
            "summary": {
                "passed": sum(check.status == "PASS" for check in self.checks),
                "warnings": sum(check.status == "WARN" for check in self.checks),
                "failures": len(self.failures),
            },
            "checks": [check.to_dict() for check in self.checks],
        }
