from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CharacterLoraSampleReview:
    identity_score: float
    anatomy_score: float
    caption_matches: bool
    human_approved: bool
    reviewer: str
    reviewed_content_hash: str
    content_hash_matches: bool
    notes: str = ""

    def __post_init__(self) -> None:
        if not 0.0 <= self.identity_score <= 1.0:
            raise ValueError("Dataset identity score must be between 0 and 1.")
        if not 0.0 <= self.anatomy_score <= 1.0:
            raise ValueError("Dataset anatomy score must be between 0 and 1.")
        if self.human_approved and not self.reviewer.strip():
            raise ValueError("Approved dataset samples require a reviewer.")

    @property
    def passed(self) -> bool:
        return (
            self.identity_score >= 0.90
            and self.anatomy_score >= 0.85
            and self.caption_matches
            and self.human_approved
            and self.content_hash_matches
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity_score": self.identity_score,
            "anatomy_score": self.anatomy_score,
            "caption_matches": self.caption_matches,
            "human_approved": self.human_approved,
            "reviewer": self.reviewer,
            "reviewed_content_hash": self.reviewed_content_hash,
            "content_hash_matches": self.content_hash_matches,
            "notes": self.notes,
            "passed": self.passed,
        }


@dataclass(frozen=True)
class CharacterLoraDatasetSample:
    sample_id: str
    source_name: str
    view: str
    split: str
    image_path: str
    caption_path: str
    caption: str
    content_hash: str
    width: int
    height: int
    review: CharacterLoraSampleReview | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "source_name": self.source_name,
            "view": self.view,
            "split": self.split,
            "image_path": self.image_path,
            "caption_path": self.caption_path,
            "caption": self.caption,
            "content_hash": self.content_hash,
            "width": self.width,
            "height": self.height,
            "review": self.review.to_dict() if self.review else None,
        }


@dataclass(frozen=True)
class CharacterLoraDatasetReport:
    schema_version: int
    character_id: str
    trigger_token: str
    samples: tuple[CharacterLoraDatasetSample, ...]
    rejected_files: tuple[dict[str, str], ...]
    duplicate_files: tuple[str, ...]
    required_training_images: int
    required_holdout_images: int
    anchor_content_hash: str = ""
    approved_by: str = ""

    @property
    def training_count(self) -> int:
        return sum(sample.split == "train" for sample in self.samples)

    @property
    def holdout_count(self) -> int:
        return sum(sample.split == "holdout" for sample in self.samples)

    @property
    def is_ready(self) -> bool:
        return self.training_approved

    @property
    def dataset_complete(self) -> bool:
        return (
            self.training_count >= self.required_training_images
            and self.holdout_count >= self.required_holdout_images
            and not self.rejected_files
            and not self.duplicate_files
        )

    @property
    def training_approved(self) -> bool:
        return (
            self.schema_version >= 2
            and self.dataset_complete
            and bool(self.anchor_content_hash)
            and bool(self.approved_by)
            and bool(self.samples)
            and all(
                sample.review is not None and sample.review.passed
                for sample in self.samples
            )
        )

    @property
    def blockers(self) -> tuple[str, ...]:
        blockers: list[str] = []
        if self.training_count < self.required_training_images:
            blockers.append("insufficient_training_images")
        if self.holdout_count < self.required_holdout_images:
            blockers.append("insufficient_holdout_images")
        if self.rejected_files:
            blockers.append("rejected_files_present")
        if self.duplicate_files:
            blockers.append("duplicate_files_present")
        if not self.anchor_content_hash:
            blockers.append("canonical_anchor_missing")
        if not self.approved_by:
            blockers.append("dataset_approver_missing")
        if any(sample.review is None for sample in self.samples):
            blockers.append("sample_reviews_missing")
        elif any(not sample.review.passed for sample in self.samples if sample.review):
            blockers.append("sample_reviews_failed")
        return tuple(blockers)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "character_id": self.character_id,
            "trigger_token": self.trigger_token,
            "is_ready": self.is_ready,
            "dataset_complete": self.dataset_complete,
            "training_approved": self.training_approved,
            "blockers": list(self.blockers),
            "anchor_content_hash": self.anchor_content_hash,
            "approved_by": self.approved_by or None,
            "training_count": self.training_count,
            "holdout_count": self.holdout_count,
            "required_training_images": self.required_training_images,
            "required_holdout_images": self.required_holdout_images,
            "samples": [sample.to_dict() for sample in self.samples],
            "rejected_files": list(self.rejected_files),
            "duplicate_files": list(self.duplicate_files),
        }
