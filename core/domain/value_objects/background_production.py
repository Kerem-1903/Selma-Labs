from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from core.domain.value_objects.preproduction_image_quality import (
    PreproductionImageQuality,
)

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


@dataclass(frozen=True)
class BackgroundRecipe:
    recipe_id: str
    shot_scale: str
    camera_angle: str
    weather: str
    prompt: str
    seed: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "recipe_id": self.recipe_id,
            "shot_scale": self.shot_scale,
            "camera_angle": self.camera_angle,
            "weather": self.weather,
            "prompt": self.prompt,
            "seed": self.seed,
        }


@dataclass(frozen=True)
class BackgroundProductionPlan:
    schema_version: int
    location_id: str
    negative_prompts: tuple[str, ...]
    recipes: tuple[BackgroundRecipe, ...]
    layer_order: tuple[str, ...] = ("background", "midground", "foreground")
    depth_map_required: bool = True

    def __post_init__(self) -> None:
        if self.schema_version != 1 or not _SAFE_ID.fullmatch(self.location_id):
            raise ValueError("Invalid background-production plan identity.")
        if len(self.recipes) < 9:
            raise ValueError("A location requires at least nine coverage recipes.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "location_id": self.location_id,
            "negative_prompts": list(self.negative_prompts),
            "layer_order": list(self.layer_order),
            "depth_map_required": self.depth_map_required,
            "recipes": [recipe.to_dict() for recipe in self.recipes],
        }


@dataclass(frozen=True)
class BackgroundCandidate:
    recipe_id: str
    storage_key: str
    width: int
    height: int
    attempt: int
    quality: PreproductionImageQuality | None = None
    depth_map_storage_key: str | None = None

    @property
    def parallax_ready(self) -> bool:
        return self.depth_map_storage_key is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "recipe_id": self.recipe_id,
            "storage_key": self.storage_key,
            "width": self.width,
            "height": self.height,
            "attempt": self.attempt,
            "quality": self.quality.to_dict() if self.quality else None,
            "depth_map_storage_key": self.depth_map_storage_key,
            "parallax_ready": self.parallax_ready,
            "human_approved": False,
        }


@dataclass(frozen=True)
class BackgroundCandidatePack:
    location_id: str
    candidates: tuple[BackgroundCandidate, ...]
    quarantined: tuple[BackgroundCandidate, ...] = ()
    human_approved: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "location_id": self.location_id,
            "candidate_count": len(self.candidates),
            "quarantined_count": len(self.quarantined),
            "human_approved": self.human_approved,
            "candidates": [item.to_dict() for item in self.candidates],
            "quarantined": [item.to_dict() for item in self.quarantined],
            "next_gate": "HUMAN_BACKGROUND_APPROVAL",
        }
