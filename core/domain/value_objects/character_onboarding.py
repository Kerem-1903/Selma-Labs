"""Deterministic contracts for turning a Character Bible into training assets."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from core.domain.value_objects.preproduction_image_quality import (
    PreproductionImageQuality,
)

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


@dataclass(frozen=True)
class CharacterReferenceRecipe:
    filename: str
    view: str
    split: str
    prompt: str
    seed: int

    def __post_init__(self) -> None:
        if (
            not self.filename.endswith(".png")
            or "/" in self.filename
            or "\\" in self.filename
        ):
            raise ValueError(
                "Reference recipe filename must be a portable PNG filename."
            )
        if self.split not in {"train", "holdout"}:
            raise ValueError("Reference recipe split must be train or holdout.")
        if not self.view.strip() or not self.prompt.strip() or self.seed < 0:
            raise ValueError("Reference recipe is incomplete.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "filename": self.filename,
            "view": self.view,
            "split": self.split,
            "prompt": self.prompt,
            "seed": self.seed,
        }


@dataclass(frozen=True)
class CharacterOnboardingPlan:
    schema_version: int
    character_id: str
    trigger_token: str
    anchor_prompt: str
    anchor_seed: int
    negative_prompts: tuple[str, ...]
    recipes: tuple[CharacterReferenceRecipe, ...]

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("Unsupported character-onboarding schema version.")
        if not _SAFE_ID.fullmatch(self.character_id):
            raise ValueError("Character onboarding requires a portable character ID.")
        if not self.trigger_token.strip() or not self.anchor_prompt.strip():
            raise ValueError("Character onboarding identity is incomplete.")
        filenames = [recipe.filename for recipe in self.recipes]
        if len(filenames) != len(set(filenames)):
            raise ValueError("Character onboarding recipe filenames must be unique.")
        if self.training_count < 20 or self.holdout_count < 3:
            raise ValueError(
                "Character onboarding requires 20 train and 3 holdout recipes."
            )

    @property
    def training_count(self) -> int:
        return sum(recipe.split == "train" for recipe in self.recipes)

    @property
    def holdout_count(self) -> int:
        return sum(recipe.split == "holdout" for recipe in self.recipes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "character_id": self.character_id,
            "trigger_token": self.trigger_token,
            "anchor_prompt": self.anchor_prompt,
            "anchor_seed": self.anchor_seed,
            "negative_prompts": list(self.negative_prompts),
            "training_count": self.training_count,
            "holdout_count": self.holdout_count,
            "recipes": [recipe.to_dict() for recipe in self.recipes],
        }


@dataclass(frozen=True)
class CharacterCandidateAsset:
    filename: str
    storage_key: str
    provider_asset_id: str
    width: int
    height: int
    attempt: int = 1
    quality: PreproductionImageQuality | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "filename": self.filename,
            "storage_key": self.storage_key,
            "provider_asset_id": self.provider_asset_id,
            "width": self.width,
            "height": self.height,
            "attempt": self.attempt,
            "quality": self.quality.to_dict() if self.quality else None,
        }


@dataclass(frozen=True)
class CharacterCandidatePack:
    schema_version: int
    character_id: str
    anchor_storage_key: str
    candidates: tuple[CharacterCandidateAsset, ...]
    quarantined: tuple[CharacterCandidateAsset, ...] = ()
    human_approved: bool = False

    @property
    def source_prefix(self) -> str:
        if not self.candidates:
            return ""
        return PurePosixPath(self.candidates[0].storage_key).parent.as_posix()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "character_id": self.character_id,
            "anchor_storage_key": self.anchor_storage_key,
            "human_approved": self.human_approved,
            "candidate_count": len(self.candidates),
            "quarantined_count": len(self.quarantined),
            "source_prefix": self.source_prefix,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "quarantined": [candidate.to_dict() for candidate in self.quarantined],
        }
