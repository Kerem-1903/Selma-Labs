from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CanonViolationCode(str, Enum):
    CHARACTER_VOICE_MISMATCH = "CHARACTER_VOICE_MISMATCH"
    WORLD_RULE_VIOLATION = "WORLD_RULE_VIOLATION"
    UNKNOWN_LOCATION = "UNKNOWN_LOCATION"
    UNKNOWN_CHARACTER = "UNKNOWN_CHARACTER"
    UNAUTHORIZED_POWER = "UNAUTHORIZED_POWER"
    CHARACTER_MOTIVATION_CONFLICT = "CHARACTER_MOTIVATION_CONFLICT"
    STYLE_IMITATION_RISK = "STYLE_IMITATION_RISK"


@dataclass(frozen=True)
class CanonViolation:
    code: CanonViolationCode
    message: str
    scene_id: str | None = None
    evidence: str | None = None


@dataclass(frozen=True)
class CanonValidationReport:
    violations: tuple[CanonViolation, ...] = ()

    @property
    def passed(self) -> bool:
        return not self.violations
