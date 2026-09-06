from __future__ import annotations

from typing import get_type_hints

from core.domain.value_objects.pose_contract import (
    PoseContract,
    PoseContractCatalog,
    validate_catalog,
)


def _contract() -> PoseContract:
    return PoseContract(
        pose_id="act_01_sprint",
        pose_skeleton_ref="poses/sprint.png",
        facing_direction="camera_right",
        character_orientation="profile_left",
        conditioning_reference="views/profile-left.png",
        framing_type="full_body",
    )


def test_validate_catalog_type_hints_are_runtime_resolvable():
    hints = get_type_hints(validate_catalog)

    assert "resolve_ref" in hints


def test_validate_catalog_matches_action_view_to_numbered_pose_id(tmp_path):
    pose = tmp_path / "poses" / "sprint.png"
    pose.parent.mkdir(parents=True)
    pose.write_bytes(b"openpose")

    errors = validate_catalog(
        PoseContractCatalog((_contract(),)),
        ["ACTION_SPRINT"],
        resolve_ref=lambda key: pose if key == "poses/sprint.png" else None,
    )

    assert errors == []


def test_validate_catalog_reports_missing_pose_asset():
    errors = validate_catalog(
        PoseContractCatalog((_contract(),)),
        ["ACTION_SPRINT"],
        resolve_ref=lambda _key: None,
    )

    assert errors == ["ACTION_SPRINT: pose skeleton reference not found: poses/sprint.png"]
