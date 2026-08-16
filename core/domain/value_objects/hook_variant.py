"""Ranked hook candidates and one-variable experiment metadata."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class HookVariantScore:
    text: str
    hook_type: str
    score: int
    maximum_score: int
    strengths: tuple[str, ...]
    issues: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "hook_type": self.hook_type,
            "score": self.score,
            "maximum_score": self.maximum_score,
            "strengths": list(self.strengths),
            "issues": list(self.issues),
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "HookVariantScore":
        return HookVariantScore(
            text=str(data["text"]),
            hook_type=str(data["hook_type"]),
            score=int(data["score"]),
            maximum_score=int(data["maximum_score"]),
            strengths=tuple(str(item) for item in data.get("strengths", [])),
            issues=tuple(str(item) for item in data.get("issues", [])),
        )


@dataclass(frozen=True)
class HookExperiment:
    experiment_id: str
    topic: str
    principal_variable: str
    control: HookVariantScore
    selected: HookVariantScore
    ranked_variants: tuple[HookVariantScore, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "topic": self.topic,
            "principal_variable": self.principal_variable,
            "control": self.control.to_dict(),
            "selected": self.selected.to_dict(),
            "ranked_variants": [variant.to_dict() for variant in self.ranked_variants],
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "HookExperiment":
        return HookExperiment(
            experiment_id=str(data["experiment_id"]),
            topic=str(data["topic"]),
            principal_variable=str(data["principal_variable"]),
            control=HookVariantScore.from_dict(dict(data["control"])),
            selected=HookVariantScore.from_dict(dict(data["selected"])),
            ranked_variants=tuple(
                HookVariantScore.from_dict(dict(item))
                for item in data.get("ranked_variants", [])
            ),
        )
