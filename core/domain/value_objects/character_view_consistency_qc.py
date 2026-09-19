"""Consistency evidence for a canonical character view pack.

The deterministic part proves that every view is bound to the same identity
contract and reference chain. Visual identity judgments remain explicitly human
until a calibrated embedding/segmentation provider is available.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

HUMAN_REQUIRED_CONSISTENCY_CHECKS = (
    "identity_similarity",
    "face_similarity",
    "hair_consistency",
    "costume_consistency",
    "palette_consistency",
    "style_consistency",
    "background_consistency",
)


@dataclass(frozen=True)
class CharacterViewConsistencyQc:
    contract_hash: str
    view: str
    reference_hashes: tuple[str, ...]
    automatic_checks: dict[str, bool]
    human_required_checks: tuple[str, ...] = HUMAN_REQUIRED_CONSISTENCY_CHECKS
    measurements: dict[str, float | None] | None = None
    status: str = "HUMAN_REVIEW_REQUIRED"

    def __post_init__(self) -> None:
        if not self.contract_hash:
            raise ValueError("Consistency QC requires an identity contract hash.")
        if not self.view:
            raise ValueError("Consistency QC requires a view.")
        if self.status not in {"HUMAN_REVIEW_REQUIRED", "READY_FOR_HUMAN_REVIEW"}:
            raise ValueError("Unsupported consistency QC status.")
        if not self.automatic_checks:
            raise ValueError("Consistency QC requires automatic checks.")

    @property
    def automatic_passed(self) -> bool:
        return all(self.automatic_checks.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_hash": self.contract_hash,
            "view": self.view,
            "reference_hashes": list(self.reference_hashes),
            "automatic_checks": dict(self.automatic_checks),
            "automatic_passed": self.automatic_passed,
            "human_required_checks": list(self.human_required_checks),
            "measurements": dict(self.measurements or {}),
            "status": self.status,
        }
