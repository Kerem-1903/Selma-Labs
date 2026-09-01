from core.domain.entities.character_rig import (
    AnimeShapeKeyEnum,
    RigSpecification,
    StandardPoseEnum,
)


def _specification(**overrides: object) -> RigSpecification:
    values = {
        "has_ik_arm_l": True,
        "has_ik_arm_r": True,
        "has_ik_leg_l": True,
        "has_ik_leg_r": True,
        "has_fk_arm_l": True,
        "has_fk_arm_r": True,
        "has_fk_leg_l": True,
        "has_fk_leg_r": True,
        "has_secondary_hair": True,
        "has_secondary_jacket": True,
        "shape_keys": frozenset(item.value for item in AnimeShapeKeyEnum),
        "available_actions": frozenset(item.value for item in StandardPoseEnum),
    }
    values.update(overrides)
    return RigSpecification(**values)


def test_lipsync_ready_with_all_required_phonemes():
    spec = RigSpecification(
        has_ik_arm_l=True,
        has_ik_arm_r=True,
        has_ik_leg_l=True,
        has_ik_leg_r=True,
        has_fk_arm_l=True,
        has_fk_arm_r=True,
        has_fk_leg_l=True,
        has_fk_leg_r=True,
        has_secondary_hair=True,
        has_secondary_jacket=True,
        shape_keys=frozenset(
            [
                AnimeShapeKeyEnum.MOUTH_A.value,
                AnimeShapeKeyEnum.MOUTH_E.value,
                AnimeShapeKeyEnum.MOUTH_I.value,
                AnimeShapeKeyEnum.MOUTH_O.value,
                AnimeShapeKeyEnum.MOUTH_U.value,
                AnimeShapeKeyEnum.MOUTH_CLOSED.value,
                AnimeShapeKeyEnum.EYE_BLINK_L.value,
            ]
        ),
        available_actions=frozenset(["walk"]),
    )
    assert spec.is_lipsync_ready() is True


def test_lipsync_ready_missing_phonemes():
    spec = RigSpecification(
        has_ik_arm_l=True,
        has_ik_arm_r=True,
        has_ik_leg_l=True,
        has_ik_leg_r=True,
        has_fk_arm_l=True,
        has_fk_arm_r=True,
        has_fk_leg_l=True,
        has_fk_leg_r=True,
        has_secondary_hair=True,
        has_secondary_jacket=True,
        shape_keys=frozenset(
            [AnimeShapeKeyEnum.MOUTH_A.value, AnimeShapeKeyEnum.MOUTH_E.value]
        ),
        available_actions=frozenset(["walk"]),
    )
    assert spec.is_lipsync_ready() is False


def test_a9_policy_reports_missing_controls_shape_keys_and_actions():
    spec = _specification(
        has_ik_arm_r=False,
        shape_keys=frozenset({AnimeShapeKeyEnum.MOUTH_CLOSED.value}),
        available_actions=frozenset({StandardPoseEnum.IDLE_BREATHING.value}),
    )

    assert spec.missing_a9_controls() == ("IK_ARM_R",)
    assert AnimeShapeKeyEnum.EYE_BLINK_L.value in spec.missing_a9_shape_keys()
    assert StandardPoseEnum.WALK_2STEP.value in spec.missing_a9_actions()
