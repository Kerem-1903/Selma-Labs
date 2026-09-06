"""Versioned visual-quality target for character model comparisons."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from core.domain.exceptions import PreProductionValidationError


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PreProductionValidationError(f"{field_name} must not be empty.")
    return value.strip()


def _items(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise PreProductionValidationError(f"{field_name} must be a list.")
    return tuple(_text(item, field_name) for item in value)


@dataclass(frozen=True)
class CharacterBenchmarkCriterion:
    id: str
    label: str
    weight: float

    def __post_init__(self) -> None:
        identifier = _text(self.id, "benchmark criterion id")
        if any(character.isspace() or character in "/\\." for character in identifier):
            raise PreProductionValidationError(
                "benchmark criterion id must be one portable segment."
            )
        object.__setattr__(self, "id", identifier)
        object.__setattr__(self, "label", _text(self.label, "benchmark criterion label"))
        if not math.isfinite(self.weight) or not 0.0 < self.weight <= 1.0:
            raise PreProductionValidationError(
                "benchmark criterion weight must be between 0 and 1."
            )

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "label": self.label, "weight": self.weight}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CharacterBenchmarkCriterion:
        return cls(
            id=str(data.get("id", "")),
            label=str(data.get("label", "")),
            weight=float(data.get("weight", 0.0)),
        )


@dataclass(frozen=True)
class CharacterQualityBenchmark:
    schema_version: int
    benchmark_id: str
    reference_asset: str
    reference_sha256: str
    width: int
    height: int
    usage: str
    visual_targets: tuple[str, ...]
    human_criteria: tuple[CharacterBenchmarkCriterion, ...]
    prohibited_transfer: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise PreProductionValidationError(
                "Character quality benchmark schema_version must be 1."
            )
        object.__setattr__(self, "benchmark_id", _text(self.benchmark_id, "benchmark_id"))
        asset = PurePosixPath(_text(self.reference_asset, "reference_asset"))
        if asset.is_absolute() or ".." in asset.parts:
            raise PreProductionValidationError(
                "reference_asset must stay inside the workspace."
            )
        digest = _text(self.reference_sha256, "reference_sha256").casefold()
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise PreProductionValidationError(
                "reference_sha256 must be a SHA-256 digest."
            )
        object.__setattr__(self, "reference_sha256", digest)
        if self.width <= 0 or self.height <= 0:
            raise PreProductionValidationError(
                "benchmark image dimensions must be positive."
            )
        object.__setattr__(self, "usage", _text(self.usage, "usage"))
        if not self.visual_targets or not self.human_criteria:
            raise PreProductionValidationError(
                "benchmark requires visual targets and human criteria."
            )
        ids = [criterion.id for criterion in self.human_criteria]
        if len(ids) != len(set(ids)):
            raise PreProductionValidationError(
                "benchmark criterion ids must be unique."
            )
        if not math.isclose(
            sum(criterion.weight for criterion in self.human_criteria),
            1.0,
            abs_tol=1e-6,
        ):
            raise PreProductionValidationError(
                "benchmark criterion weights must total 1.0."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "benchmark_id": self.benchmark_id,
            "reference_asset": self.reference_asset,
            "reference_sha256": self.reference_sha256,
            "width": self.width,
            "height": self.height,
            "usage": self.usage,
            "visual_targets": list(self.visual_targets),
            "human_criteria": [criterion.to_dict() for criterion in self.human_criteria],
            "prohibited_transfer": list(self.prohibited_transfer),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CharacterQualityBenchmark:
        raw_criteria = data.get("human_criteria", ())
        if not isinstance(raw_criteria, (list, tuple)) or not all(
            isinstance(item, Mapping) for item in raw_criteria
        ):
            raise PreProductionValidationError("human_criteria must be a list of objects.")
        return cls(
            schema_version=int(data.get("schema_version", 0)),
            benchmark_id=str(data.get("benchmark_id", "")),
            reference_asset=str(data.get("reference_asset", "")),
            reference_sha256=str(data.get("reference_sha256", "")),
            width=int(data.get("width", 0)),
            height=int(data.get("height", 0)),
            usage=str(data.get("usage", "")),
            visual_targets=_items(data.get("visual_targets", ()), "visual_targets"),
            human_criteria=tuple(
                CharacterBenchmarkCriterion.from_dict(item) for item in raw_criteria
            ),
            prohibited_transfer=_items(
                data.get("prohibited_transfer", ()), "prohibited_transfer"
            ),
        )
