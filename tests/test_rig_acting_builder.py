from infrastructure.scripts.blender.rig_acting_builder import _has_control


def test_control_side_detection_does_not_match_letters_inside_limb_name():
    assert _has_control(["ik_arm.L"], "ik", "arm", "l") is True
    assert _has_control(["ik_arm.L"], "ik", "arm", "r") is False
    assert _has_control(["ik_leg.R"], "ik", "leg", "r") is True
    assert _has_control(["ik_leg.R"], "ik", "leg", "l") is False


def test_control_detection_supports_rigify_style_names():
    bones = ["upper_arm_ik.L", "upper_arm_fk.R", "thigh_ik.L", "shin_fk.R"]

    assert _has_control(bones, "ik", "arm", "l") is True
    assert _has_control(bones, "fk", "arm", "r") is True
    assert _has_control(bones, "ik", "leg", "l") is True
    assert _has_control(bones, "fk", "leg", "r") is True
