from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class KeyframeGenerationRequest:
    """Typed, provider-independent input for one storyboard keyframe."""

    shot_contract_id: str
    camera_constraints: dict[str, Any]
    action_constraints: dict[str, Any]
    visual_constraints: dict[str, Any]
    character_conditioning: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    reference_asset_ids: tuple[str, ...] = field(default_factory=tuple)
    reference_storage_keys: tuple[str, ...] = field(default_factory=tuple)
    negative_prompts: tuple[str, ...] = field(default_factory=tuple)
    width: int = 1024
    height: int = 1024
    seed: int | None = None

    def __post_init__(self) -> None:
        if not self.shot_contract_id.strip():
            raise ValueError("shot_contract_id must not be empty.")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("Keyframe dimensions must be greater than zero.")
        if len(self.reference_asset_ids) != len(self.reference_storage_keys):
            raise ValueError("Reference asset IDs and storage keys must stay aligned.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "shot_contract_id": self.shot_contract_id,
            "camera_constraints": dict(self.camera_constraints),
            "action_constraints": dict(self.action_constraints),
            "visual_constraints": dict(self.visual_constraints),
            "character_conditioning": [dict(item) for item in self.character_conditioning],
            "reference_asset_ids": list(self.reference_asset_ids),
            "reference_storage_keys": list(self.reference_storage_keys),
            "negative_prompts": list(self.negative_prompts),
            "width": self.width,
            "height": self.height,
            "seed": self.seed,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "KeyframeGenerationRequest":
        return cls(
            shot_contract_id=str(data["shot_contract_id"]),
            camera_constraints=dict(data.get("camera_constraints", {})),
            action_constraints=dict(data.get("action_constraints", {})),
            visual_constraints=dict(data.get("visual_constraints", {})),
            character_conditioning=tuple(
                dict(item) for item in data.get("character_conditioning", [])
            ),
            reference_asset_ids=tuple(
                str(item) for item in data.get("reference_asset_ids", [])
            ),
            reference_storage_keys=tuple(
                str(item) for item in data.get("reference_storage_keys", [])
            ),
            negative_prompts=tuple(
                str(item) for item in data.get("negative_prompts", [])
            ),
            width=int(data.get("width", 1024)),
            height=int(data.get("height", 1024)),
            seed=None if data.get("seed") is None else int(data["seed"]),
        )
