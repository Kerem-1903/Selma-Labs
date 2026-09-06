"""PoseContract value object — spec §8.1.

A pose contract pins one action pose to its mandatory OpenPose skeleton
reference, its conditioning view, framing and accessory rules. Actions
without a contract (or without a skeleton reference) must fail closed:
prompt-only fallback is forbidden (spec principle 6 / §8.2).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ACTION_VIEW_PREFIX = "ACTION_"


@dataclass(frozen=True)
class PoseContract:
    pose_id: str
    pose_skeleton_ref: str  # storage key / path of the OpenPose PNG — mandatory
    facing_direction: str
    character_orientation: str
    conditioning_reference: str  # approved view key, e.g. "views/profile-left.png"
    framing_type: str
    allowed_accessories: tuple[str, ...] = ()
    forbidden_accessories: tuple[str, ...] = ()
    openpose_strength: float = 0.85
    seed: int | None = None

    def __post_init__(self) -> None:
        missing = [
            name
            for name in (
                "pose_id",
                "pose_skeleton_ref",
                "facing_direction",
                "character_orientation",
                "conditioning_reference",
                "framing_type",
            )
            if not getattr(self, name)
        ]
        if missing:
            raise ValueError(f"PoseContract missing required fields: {missing}")
        if not 0.0 <= self.openpose_strength <= 1.0:
            raise ValueError("openpose_strength must be within [0.0, 1.0]")

    def to_dict(self) -> dict[str, Any]:
        return {
            "pose_id": self.pose_id,
            "pose_skeleton_ref": self.pose_skeleton_ref,
            "facing_direction": self.facing_direction,
            "character_orientation": self.character_orientation,
            "conditioning_reference": self.conditioning_reference,
            "framing_type": self.framing_type,
            "allowed_accessories": list(self.allowed_accessories),
            "forbidden_accessories": list(self.forbidden_accessories),
            "openpose_strength": self.openpose_strength,
            "seed": self.seed,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PoseContract:
        return cls(
            pose_id=data["pose_id"],
            pose_skeleton_ref=data["pose_skeleton_ref"],
            facing_direction=data["facing_direction"],
            character_orientation=data["character_orientation"],
            conditioning_reference=data["conditioning_reference"],
            framing_type=data["framing_type"],
            allowed_accessories=tuple(data.get("allowed_accessories", ())),
            forbidden_accessories=tuple(data.get("forbidden_accessories", ())),
            openpose_strength=float(data.get("openpose_strength", 0.85)),
            seed=data.get("seed"),
        )


@dataclass(frozen=True)
class PoseContractCatalog:
    contracts: tuple[PoseContract, ...] = field(default=())

    def by_pose_id(self, pose_id: str) -> PoseContract | None:
        return next((c for c in self.contracts if c.pose_id == pose_id), None)

    def by_action_view(self, action_view: str) -> PoseContract | None:
        expected = _action_view_key(action_view)
        return next(
            (contract for contract in self.contracts if _action_view_key(contract.pose_id) == expected),
            None,
        )

    def to_dict(self) -> dict[str, Any]:
        return {"contracts": [c.to_dict() for c in self.contracts]}


def is_action_view(view: str) -> bool:
    return view.upper().startswith(ACTION_VIEW_PREFIX)


def _action_view_key(value: str) -> str:
    """Normalize ACTION_SPRINT and act_01_sprint to the same catalog key."""
    normalized = re.sub(r"[^A-Z0-9]+", "_", value.strip().upper()).strip("_")
    normalized = re.sub(r"^ACT_\d+_", "", normalized)
    normalized = normalized.removeprefix(ACTION_VIEW_PREFIX)
    return f"{ACTION_VIEW_PREFIX}{normalized}"


def validate_catalog(
    catalog: PoseContractCatalog,
    action_views: list[str],
    resolve_ref: Callable[[str], Path | None] | None = None,
) -> list[str]:
    """Fail-closed validation for a planned action set.

    Returns a list of human-readable errors; an empty list means the catalog
    satisfies the spec: every ACTION_* view has a contract whose skeleton
    reference exists on disk (when a resolver is supplied) and whose
    conditioning reference is not a forbidden prompt-only stub.
    """
    errors: list[str] = []
    for view in action_views:
        if not is_action_view(view):
            continue
        contract = catalog.by_action_view(view)
        if contract is None:
            errors.append(
                f"{view}: no PoseContract — prompt-only fallback is forbidden "
                "(spec principle 6)"
            )
            continue
        if not contract.pose_skeleton_ref:
            errors.append(f"{view}: PoseContract has an empty pose_skeleton_ref")
        elif resolve_ref is not None and resolve_ref(contract.pose_skeleton_ref) is None:
            errors.append(
                f"{view}: pose skeleton reference not found: "
                f"{contract.pose_skeleton_ref}"
            )
        if not contract.conditioning_reference:
            errors.append(f"{view}: PoseContract has an empty conditioning_reference")
    return errors


def load_catalog(path: str | Path) -> PoseContractCatalog:
    import json

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        raw = data.get("contracts", [])
    else:
        raw = data
    return PoseContractCatalog(
        contracts=tuple(PoseContract.from_dict(item) for item in raw)
    )
