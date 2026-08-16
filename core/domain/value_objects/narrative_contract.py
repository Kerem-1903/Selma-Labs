"""Narrative promise and beat metadata for one short-form script."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class NarrativeContract:
    """The promise a script must keep before paid production begins."""

    topic: str
    language: str
    target_audience: str
    promise: str
    question_to_answer: str | None
    answer_requirement: str
    hook_type: str
    payoff_requirement: str
    target_duration_seconds: int
    duration_override_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "language": self.language,
            "target_audience": self.target_audience,
            "promise": self.promise,
            "question_to_answer": self.question_to_answer,
            "answer_requirement": self.answer_requirement,
            "hook_type": self.hook_type,
            "payoff_requirement": self.payoff_requirement,
            "target_duration_seconds": self.target_duration_seconds,
            "duration_override_reason": self.duration_override_reason,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "NarrativeContract":
        return NarrativeContract(
            topic=str(data["topic"]),
            language=str(data.get("language") or "und"),
            target_audience=str(data.get("target_audience") or "curious general audience"),
            promise=str(data["promise"]),
            question_to_answer=(
                str(data["question_to_answer"])
                if data.get("question_to_answer")
                else None
            ),
            answer_requirement=str(data["answer_requirement"]),
            hook_type=str(data.get("hook_type") or "curiosity"),
            payoff_requirement=str(data["payoff_requirement"]),
            target_duration_seconds=int(data["target_duration_seconds"]),
            duration_override_reason=(
                str(data["duration_override_reason"])
                if data.get("duration_override_reason")
                else None
            ),
        )


@dataclass(frozen=True)
class NarrativeBeat:
    """One sentence-level narrative unit with an explicit editorial role."""

    index: int
    role: str
    text: str
    information_contribution: str
    contains_answer: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "role": self.role,
            "text": self.text,
            "information_contribution": self.information_contribution,
            "contains_answer": self.contains_answer,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "NarrativeBeat":
        return NarrativeBeat(
            index=int(data["index"]),
            role=str(data["role"]),
            text=str(data["text"]),
            information_contribution=str(data["information_contribution"]),
            contains_answer=bool(data.get("contains_answer", False)),
        )

