"""Creative script-quality evidence produced before narration generation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.domain.value_objects.narrative_contract import NarrativeBeat, NarrativeContract


@dataclass(frozen=True)
class NarrativeQualityIssue:
    code: str
    message: str
    blocking: bool
    beat_index: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "blocking": self.blocking,
            "beat_index": self.beat_index,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "NarrativeQualityIssue":
        return NarrativeQualityIssue(
            code=str(data["code"]),
            message=str(data["message"]),
            blocking=bool(data["blocking"]),
            beat_index=(int(data["beat_index"]) if data.get("beat_index") is not None else None),
        )


@dataclass(frozen=True)
class NarrativeQualityReport:
    contract: NarrativeContract
    beats: tuple[NarrativeBeat, ...]
    score: int
    maximum_score: int
    passed: bool
    hook_text: str
    payoff_text: str
    answer_evidence: str | None
    issues: tuple[NarrativeQualityIssue, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract.to_dict(),
            "beats": [beat.to_dict() for beat in self.beats],
            "score": self.score,
            "maximum_score": self.maximum_score,
            "passed": self.passed,
            "hook_text": self.hook_text,
            "payoff_text": self.payoff_text,
            "answer_evidence": self.answer_evidence,
            "issues": [issue.to_dict() for issue in self.issues],
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "NarrativeQualityReport":
        return NarrativeQualityReport(
            contract=NarrativeContract.from_dict(dict(data["contract"])),
            beats=tuple(
                NarrativeBeat.from_dict(dict(item)) for item in data.get("beats", [])
            ),
            score=int(data["score"]),
            maximum_score=int(data.get("maximum_score", 15)),
            passed=bool(data["passed"]),
            hook_text=str(data.get("hook_text") or ""),
            payoff_text=str(data.get("payoff_text") or ""),
            answer_evidence=(
                str(data["answer_evidence"]) if data.get("answer_evidence") else None
            ),
            issues=tuple(
                NarrativeQualityIssue.from_dict(dict(item))
                for item in data.get("issues", [])
            ),
        )

