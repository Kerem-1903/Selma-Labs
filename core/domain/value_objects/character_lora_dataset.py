from __future__ import annotations

from dataclasses import dataclass
from typing import Any


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

    @property
    def training_count(self) -> int:
        return sum(sample.split == "train" for sample in self.samples)

    @property
    def holdout_count(self) -> int:
        return sum(sample.split == "holdout" for sample in self.samples)

    @property
    def is_ready(self) -> bool:
        return (
            self.training_count >= self.required_training_images
            and self.holdout_count >= self.required_holdout_images
            and not self.rejected_files
            and not self.duplicate_files
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "character_id": self.character_id,
            "trigger_token": self.trigger_token,
            "is_ready": self.is_ready,
            "training_count": self.training_count,
            "holdout_count": self.holdout_count,
            "required_training_images": self.required_training_images,
            "required_holdout_images": self.required_holdout_images,
            "samples": [sample.to_dict() for sample in self.samples],
            "rejected_files": list(self.rejected_files),
            "duplicate_files": list(self.duplicate_files),
        }
