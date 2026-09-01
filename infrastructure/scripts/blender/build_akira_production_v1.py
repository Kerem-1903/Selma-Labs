"""Build the reproducible Akira A9.1 production-model candidate in Blender."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

SHAPE_KEYS = (
    "MOUTH_CLOSED",
    "MOUTH_A",
    "MOUTH_E",
    "MOUTH_I",
    "MOUTH_O",
    "MOUTH_U",
    "MOUTH_SLIGHT_OPEN",
    "MOUTH_WIDE_OPEN",
    "MOUTH_TEETH_CONTACT",
    "EYE_BLINK_L",
    "EYE_BLINK_R",
    "EYE_SQUINT",
    "BROW_ANGRY",
    "BROW_SURPRISED",
    "BROW_DETERMINED",
    "SMILE_L",
    "SMILE_R",
)

ACTIONS = (
    "IDLE_BREATHING",
    "WALK_2STEP",
    "HEAD_TURN",
    "LOOK_AT_CAMERA",
    "ARM_RAISE",
    "SPEAKING",
    "SHOCK",
    "ANGER",
)

PALETTE = {
    "outline": (0.012, 0.010, 0.014, 1.0),
    "hair": (0.026, 0.022, 0.030, 1.0),
    "hair_highlight": (0.12, 0.085, 0.105, 1.0),
    "red": (0.48, 0.018, 0.028, 1.0),
    "red_bright": (0.85, 0.035, 0.045, 1.0),
    "amber": (0.95, 0.29, 0.025, 1.0),
    "skin": (0.96, 0.66, 0.55, 1.0),
    "skin_shadow": (0.70, 0.32, 0.29, 1.0),
    "jacket": (0.055, 0.065, 0.085, 1.0),
    "jacket_light": (0.105, 0.12, 0.15, 1.0),
    "shirt": (0.018, 0.018, 0.022, 1.0),
    "pants": (0.18, 0.17, 0.17, 1.0),
    "metal": (0.21, 0.22, 0.24, 1.0),
    "white": (0.96, 0.94, 0.92, 1.0),
}


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-output", required=True)
    parser.add_argument("--render-output", required=True)
    parser.add_argument("--skip-render", action="store_true")
    separator = sys.argv.index("--") if "--" in sys.argv else -1
    return parser.parse_args(sys.argv[separator + 1 :])


def _material(name: str, color: tuple[float, float, float, float], metallic=0.0):
    material = bpy.data.materials.new(name)
    material.diffuse_color = color
    material.use_nodes = True
    principled = material.node_tree.nodes.get("Principled BSDF")
    principled.inputs["Base Color"].default_value = color
    principled.inputs["Roughness"].default_value = 0.82
    principled.inputs["Metallic"].default_value = metallic
    if "Specular IOR Level" in principled.inputs:
        principled.inputs["Specular IOR Level"].default_value = 0.25
    return material


def _assign(object_, material):
    object_.data.materials.append(material)
    return object_


def _smooth(object_):
    if object_.type == "MESH":
        for polygon in object_.data.polygons:
            polygon.use_smooth = True
    return object_


def _apply_scale(object_):
    bpy.context.view_layer.objects.active = object_
    object_.select_set(True)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    object_.select_set(False)


def _sphere(name, location, scale, material, *, segments=24, rings=12):
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=segments, ring_count=rings, location=location
    )
    object_ = bpy.context.object
    object_.name = name
    object_.scale = scale
    _apply_scale(object_)
    return _assign(_smooth(object_), material)


def _cube(name, location, scale, material, *, bevel=0.04, rotation=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(location=location, rotation=rotation)
    object_ = bpy.context.object
    object_.name = name
    object_.scale = scale
    _apply_scale(object_)
    if bevel:
        modifier = object_.modifiers.new(name="AnimeBevel", type="BEVEL")
        modifier.width = bevel
        modifier.segments = 2
    return _assign(object_, material)


def _cylinder(name, location, radius, depth, material, *, rotation=(0, 0, 0)):
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=16,
        radius=radius,
        depth=depth,
        location=location,
        rotation=rotation,
    )
    object_ = bpy.context.object
    object_.name = name
    bevel = object_.modifiers.new(name="AnimeBevel", type="BEVEL")
    bevel.width = min(radius * 0.2, 0.025)
    bevel.segments = 2
    return _assign(_smooth(object_), material)


def _curve(name, points, material, *, bevel_depth=0.012):
    curve_data = bpy.data.curves.new(name=f"{name}_Curve", type="CURVE")
    curve_data.dimensions = "3D"
    curve_data.resolution_u = 2
    curve_data.bevel_depth = bevel_depth
    curve_data.bevel_resolution = 2
    spline = curve_data.splines.new("BEZIER")
    spline.bezier_points.add(len(points) - 1)
    for point, coordinate in zip(spline.bezier_points, points):
        point.co = coordinate
        point.handle_left_type = "AUTO"
        point.handle_right_type = "AUTO"
    object_ = bpy.data.objects.new(name, curve_data)
    bpy.context.collection.objects.link(object_)
    curve_data.materials.append(material)
    return object_


def _create_materials():
    return {name: _material(f"Akira_{name}", color) for name, color in PALETTE.items()}


def _create_character(materials):
    grouped: dict[str, list] = {}

    def remember(bone, *objects):
        grouped.setdefault(bone, []).extend(objects)
        return objects

    # Head, face and iconic hair silhouette.
    head = _sphere(
        "Akira_Head", (0, -0.01, 1.94), (0.215, 0.18, 0.265), materials["skin"]
    )
    remember("head", head)
    hair_cap = _sphere(
        "Akira_HairCap", (0, 0.055, 2.02), (0.245, 0.195, 0.295), materials["hair"]
    )
    back_hair = _sphere(
        "Akira_BackHair", (0, 0.095, 1.80), (0.255, 0.13, 0.43), materials["hair"]
    )
    remember("secondary_hair", hair_cap, back_hair)

    hair_strands = []
    for index, x in enumerate((-0.19, -0.13, -0.07, 0.0, 0.07, 0.14, 0.20)):
        z_end = 1.63 + 0.06 * (index % 3)
        strand = _curve(
            f"Akira_HairStrand_{index:02d}",
            [(x, -0.115, 2.18), (x * 1.12, -0.18, 1.96), (x * 1.2, -0.13, z_end)],
            materials["hair"],
            bevel_depth=0.034 if abs(x) > 0.12 else 0.026,
        )
        hair_strands.append(strand)
    red_strand = _curve(
        "Akira_RedSignatureStrand",
        [(-0.115, -0.16, 2.17), (-0.16, -0.205, 1.98), (-0.15, -0.18, 1.68)],
        materials["red_bright"],
        bevel_depth=0.022,
    )
    remember("secondary_hair", *hair_strands, red_strand)

    # Eyes are intentionally oversized and flat for anime readability.
    facial = []
    for side, x in (("L", -0.077), ("R", 0.077)):
        eye_white = _sphere(
            f"Akira_EyeWhite_{side}",
            (x, -0.177, 1.985),
            (0.065, 0.012, 0.034),
            materials["white"],
            segments=20,
            rings=10,
        )
        iris = _sphere(
            f"Akira_Iris_{side}",
            (x, -0.189, 1.983),
            (0.022, 0.008, 0.026),
            materials["amber"],
            segments=16,
            rings=8,
        )
        pupil = _sphere(
            f"Akira_Pupil_{side}",
            (x, -0.196, 1.982),
            (0.008, 0.004, 0.014),
            materials["outline"],
            segments=12,
            rings=6,
        )
        upper_lid = _curve(
            f"Akira_UpperLid_{side}",
            [
                (x - 0.064, -0.202, 1.995),
                (x, -0.211, 2.021),
                (x + 0.067, -0.202, 1.992),
            ],
            materials["outline"],
            bevel_depth=0.008,
        )
        brow = _curve(
            f"Akira_Brow_{side}",
            [
                (x - 0.055, -0.196, 2.055),
                (x, -0.205, 2.07),
                (x + 0.055, -0.196, 2.058),
            ],
            materials["hair"],
            bevel_depth=0.009,
        )
        facial.extend((eye_white, iris, pupil, upper_lid, brow))
        remember(f"face_eye.{side}", eye_white, iris, pupil, upper_lid)
        remember(f"face_brow.{side}", brow)

    nose = _curve(
        "Akira_Nose",
        [(0.0, -0.195, 1.975), (-0.012, -0.205, 1.935), (0.006, -0.205, 1.925)],
        materials["skin_shadow"],
        bevel_depth=0.005,
    )
    mouth = _curve(
        "Akira_Mouth",
        [(-0.038, -0.202, 1.875), (0.0, -0.209, 1.868), (0.038, -0.202, 1.875)],
        materials["red"],
        bevel_depth=0.007,
    )
    remember("head", nose)
    remember("face_mouth", mouth)

    # Torso, cropped jacket and red inner collar.
    shirt = _sphere(
        "Akira_Shirt", (0, 0, 1.55), (0.255, 0.16, 0.34), materials["shirt"]
    )
    waist = _sphere("Akira_Waist", (0, 0, 1.34), (0.19, 0.14, 0.20), materials["shirt"])
    hips = _sphere("Akira_Hips", (0, 0, 1.20), (0.265, 0.17, 0.19), materials["pants"])
    remember("chest", shirt)
    remember("spine", waist)
    remember("pelvis", hips)

    jacket_left = _cube(
        "Akira_Jacket_Left",
        (-0.205, 0.005, 1.60),
        (0.13, 0.18, 0.26),
        materials["jacket"],
        bevel=0.055,
        rotation=(0, -0.05, -0.04),
    )
    jacket_right = _cube(
        "Akira_Jacket_Right",
        (0.205, 0.005, 1.60),
        (0.13, 0.18, 0.26),
        materials["jacket"],
        bevel=0.055,
        rotation=(0, 0.05, 0.04),
    )
    collar_left = _cube(
        "Akira_Collar_Left",
        (-0.12, -0.15, 1.78),
        (0.07, 0.025, 0.13),
        materials["red"],
        bevel=0.018,
        rotation=(0.2, -0.15, -0.35),
    )
    collar_right = _cube(
        "Akira_Collar_Right",
        (0.12, -0.15, 1.78),
        (0.07, 0.025, 0.13),
        materials["red"],
        bevel=0.018,
        rotation=(0.2, 0.15, 0.35),
    )
    jacket_trim = _curve(
        "Akira_Jacket_RedTrim",
        [
            (-0.31, -0.18, 1.74),
            (-0.24, -0.19, 1.40),
            (0.0, -0.19, 1.34),
            (0.24, -0.19, 1.40),
            (0.31, -0.18, 1.74),
        ],
        materials["red_bright"],
        bevel_depth=0.009,
    )
    remember("chest", jacket_left, jacket_right, collar_left, collar_right, jacket_trim)

    belt = _cylinder("Akira_Belt", (0, 0, 1.20), 0.27, 0.055, materials["outline"])
    belt.rotation_euler = (math.pi / 2, 0, 0)
    buckle = _cube(
        "Akira_BeltBuckle",
        (0, -0.183, 1.20),
        (0.06, 0.018, 0.045),
        materials["metal"],
        bevel=0.012,
    )
    remember("pelvis", belt, buckle)

    # Arms and tactical gloves.
    for side, sign in (("L", -1), ("R", 1)):
        upper = _sphere(
            f"Akira_UpperArm_{side}",
            (sign * 0.37, 0, 1.55),
            (0.115, 0.12, 0.25),
            materials["jacket"],
        )
        forearm = _sphere(
            f"Akira_Forearm_{side}",
            (sign * 0.43, 0, 1.25),
            (0.09, 0.095, 0.22),
            materials["jacket_light"],
        )
        glove = _sphere(
            f"Akira_Glove_{side}",
            (sign * 0.44, -0.005, 1.04),
            (0.075, 0.08, 0.105),
            materials["outline"],
        )
        cuff = _cylinder(
            f"Akira_Cuff_{side}",
            (sign * 0.43, 0, 1.14),
            0.105,
            0.06,
            materials["jacket"],
        )
        red_cuff = _cylinder(
            f"Akira_CuffTrim_{side}",
            (sign * 0.43, -0.001, 1.16),
            0.108,
            0.018,
            materials["red"],
        )
        remember(f"upper_arm.{side}", upper)
        remember(f"forearm.{side}", forearm, cuff, red_cuff)
        remember(f"hand.{side}", glove)

    # Legs, holsters, knee pads and tall boots.
    for side, sign in (("L", -1), ("R", 1)):
        thigh = _sphere(
            f"Akira_Thigh_{side}",
            (sign * 0.145, 0, 0.98),
            (0.145, 0.15, 0.30),
            materials["pants"],
        )
        shin = _sphere(
            f"Akira_Shin_{side}",
            (sign * 0.15, 0, 0.58),
            (0.115, 0.12, 0.25),
            materials["pants"],
        )
        knee = _sphere(
            f"Akira_KneePad_{side}",
            (sign * 0.15, -0.125, 0.75),
            (0.105, 0.045, 0.115),
            materials["jacket"],
        )
        boot = _cube(
            f"Akira_Boot_{side}",
            (sign * 0.15, -0.01, 0.31),
            (0.12, 0.14, 0.25),
            materials["outline"],
            bevel=0.05,
        )
        foot = _cube(
            f"Akira_Foot_{side}",
            (sign * 0.15, -0.095, 0.105),
            (0.13, 0.22, 0.09),
            materials["outline"],
            bevel=0.045,
        )
        holster = _cube(
            f"Akira_Holster_{side}",
            (sign * 0.29, 0.0, 0.99),
            (0.055, 0.10, 0.17),
            materials["jacket"],
            bevel=0.025,
        )
        thigh_strap = _cylinder(
            f"Akira_ThighStrap_{side}",
            (sign * 0.145, 0, 1.02),
            0.155,
            0.035,
            materials["outline"],
        )
        thigh_strap.rotation_euler = (math.pi / 2, 0, 0)
        remember(f"thigh.{side}", thigh, holster, thigh_strap)
        remember(f"shin.{side}", shin, knee, boot)
        remember(f"foot.{side}", foot)

    return grouped, head


def _edit_bone(edit_bones, name, head, tail, parent=None, *, deform=False):
    bone = edit_bones.new(name)
    bone.head = head
    bone.tail = tail
    bone.use_deform = deform
    if parent is not None:
        bone.parent = parent
    return bone


def _create_rig():
    bpy.ops.object.armature_add(enter_editmode=True, location=(0, 0, 0))
    armature = bpy.context.object
    armature.name = "Akira_Production_Rig_v1"
    armature.data.name = "Akira_Production_Armature_v1"
    armature["selma_main_rig"] = True
    armature["character_id"] = "akira"
    armature["rig_schema"] = "A9.1"
    edit_bones = armature.data.edit_bones
    edit_bones.remove(edit_bones[0])

    root = _edit_bone(edit_bones, "root", (0, 0, 0.02), (0, 0, 0.20))
    pelvis = _edit_bone(edit_bones, "pelvis", (0, 0, 1.10), (0, 0, 1.30), root)
    spine = _edit_bone(edit_bones, "spine", (0, 0, 1.30), (0, 0, 1.53), pelvis)
    chest = _edit_bone(edit_bones, "chest", (0, 0, 1.53), (0, 0, 1.76), spine)
    neck = _edit_bone(edit_bones, "neck", (0, 0, 1.76), (0, 0, 1.84), chest)
    head = _edit_bone(edit_bones, "head", (0, 0, 1.84), (0, 0, 2.14), neck)

    for side, sign in (("L", -1), ("R", 1)):
        upper_arm = _edit_bone(
            edit_bones,
            f"upper_arm.{side}",
            (sign * 0.18, 0, 1.70),
            (sign * 0.39, 0, 1.48),
            chest,
        )
        forearm = _edit_bone(
            edit_bones,
            f"forearm.{side}",
            (sign * 0.39, 0, 1.48),
            (sign * 0.44, 0, 1.18),
            upper_arm,
        )
        _edit_bone(
            edit_bones,
            f"hand.{side}",
            (sign * 0.44, 0, 1.18),
            (sign * 0.44, -0.01, 1.00),
            forearm,
        )
        thigh = _edit_bone(
            edit_bones,
            f"thigh.{side}",
            (sign * 0.14, 0, 1.17),
            (sign * 0.15, 0, 0.78),
            pelvis,
        )
        shin = _edit_bone(
            edit_bones,
            f"shin.{side}",
            (sign * 0.15, 0, 0.78),
            (sign * 0.15, 0, 0.36),
            thigh,
        )
        _edit_bone(
            edit_bones,
            f"foot.{side}",
            (sign * 0.15, 0, 0.36),
            (sign * 0.15, -0.22, 0.10),
            shin,
        )

        for control in ("ik", "fk"):
            _edit_bone(
                edit_bones,
                f"{control}_arm.{side}",
                (sign * 0.54, 0.04, 1.27),
                (sign * 0.54, 0.04, 1.47),
                root,
            )
            _edit_bone(
                edit_bones,
                f"{control}_leg.{side}",
                (sign * 0.24, -0.05, 0.16),
                (sign * 0.24, -0.05, 0.36),
                root,
            )

    _edit_bone(edit_bones, "secondary_hair", (0, 0.07, 1.90), (0, 0.10, 1.55), head)
    _edit_bone(edit_bones, "secondary_jacket", (0, 0.08, 1.66), (0, 0.10, 1.35), chest)
    _edit_bone(edit_bones, "face_mouth", (0, -0.18, 1.88), (0, -0.26, 1.88), head)
    for side, sign in (("L", -1), ("R", 1)):
        _edit_bone(
            edit_bones,
            f"face_eye.{side}",
            (sign * 0.075, -0.17, 1.99),
            (sign * 0.075, -0.24, 1.99),
            head,
        )
        _edit_bone(
            edit_bones,
            f"face_brow.{side}",
            (sign * 0.075, -0.17, 2.06),
            (sign * 0.075, -0.24, 2.06),
            head,
        )

    bpy.ops.object.mode_set(mode="OBJECT")
    armature.show_in_front = True
    return armature


def _parent_to_bones(armature, grouped):
    for bone_name, objects in grouped.items():
        for object_ in objects:
            world_matrix = object_.matrix_world.copy()
            object_.parent = armature
            object_.parent_type = "BONE"
            object_.parent_bone = bone_name
            object_.matrix_world = world_matrix


def _add_shape_keys(head):
    head.shape_key_add(name="Basis")
    for name in SHAPE_KEYS:
        # Blender 5.x may create a new key from the current mixed result. Building
        # every target from Basis prevents cumulative/exponential deformation.
        key = head.shape_key_add(name=name, from_mix=False)
        key.value = 0.0
        for point in key.data:
            coordinate = point.co
            front = coordinate.y < -0.08
            if not front:
                continue
            if name.startswith("MOUTH_") and coordinate.z < -0.04:
                amount = {
                    "MOUTH_CLOSED": 0.0,
                    "MOUTH_A": -0.025,
                    "MOUTH_E": -0.010,
                    "MOUTH_I": -0.006,
                    "MOUTH_O": -0.020,
                    "MOUTH_U": -0.012,
                    "MOUTH_SLIGHT_OPEN": -0.007,
                    "MOUTH_WIDE_OPEN": -0.032,
                    "MOUTH_TEETH_CONTACT": -0.003,
                }.get(name, 0.0)
                coordinate.z += amount
            elif name.startswith("EYE_") and 0.01 < coordinate.z < 0.12:
                coordinate.z -= 0.009
            elif name.startswith("BROW_") and coordinate.z > 0.10:
                coordinate.z += 0.008 if name == "BROW_SURPRISED" else -0.005
            elif name.startswith("SMILE_") and coordinate.z < -0.02:
                coordinate.z += 0.007


def _reset_pose(armature):
    for pose_bone in armature.pose.bones:
        pose_bone.rotation_mode = "XYZ"
        pose_bone.location = (0, 0, 0)
        pose_bone.rotation_euler = (0, 0, 0)
        pose_bone.scale = (1, 1, 1)


def _keyframe_pose(armature, frame):
    for pose_bone in armature.pose.bones:
        pose_bone.keyframe_insert(data_path="location", frame=frame)
        pose_bone.keyframe_insert(data_path="rotation_euler", frame=frame)
        pose_bone.keyframe_insert(data_path="scale", frame=frame)


def _pose(armature, name):
    return armature.pose.bones[name]


def _action_fcurves(action, animated_id):
    """Return curves from legacy and Blender 4.4+ slotted actions."""
    if hasattr(action, "fcurves"):
        return action.fcurves

    animation_data = animated_id.animation_data
    slot = animation_data.action_slot if animation_data else None
    if slot is None:
        return ()

    from bpy_extras import anim_utils

    channelbag = anim_utils.action_get_channelbag_for_slot(action, slot)
    return channelbag.fcurves if channelbag else ()


def _create_action(armature, name, apply_frame):
    armature.animation_data.action = None
    for frame in (1, 8, 16, 24):
        _reset_pose(armature)
        apply_frame(frame)
        _keyframe_pose(armature, frame)
    action = armature.animation_data.action
    action.name = name
    for fcurve in _action_fcurves(action, armature):
        for keyframe in fcurve.keyframe_points:
            keyframe.interpolation = "BEZIER"
    track = armature.animation_data.nla_tracks.new()
    track.name = f"A9::{name}"
    track.strips.new(name, 1, action)
    track.mute = True
    armature.animation_data.action = None


def _create_actions(armature):
    armature.animation_data_create()

    def idle(frame):
        phase = math.sin((frame - 1) / 23 * math.tau)
        _pose(armature, "chest").scale.z = 1.0 + 0.018 * phase
        _pose(armature, "head").rotation_euler.z = 0.015 * phase
        _pose(armature, "secondary_hair").rotation_euler.x = 0.025 * phase

    def walk(frame):
        phase = math.sin((frame - 1) / 23 * math.tau * 2)
        _pose(armature, "pelvis").location.z = 0.025 * abs(phase)
        _pose(armature, "thigh.L").rotation_euler.x = 0.42 * phase
        _pose(armature, "thigh.R").rotation_euler.x = -0.42 * phase
        _pose(armature, "shin.L").rotation_euler.x = -0.25 * max(0, -phase)
        _pose(armature, "shin.R").rotation_euler.x = -0.25 * max(0, phase)
        _pose(armature, "upper_arm.L").rotation_euler.x = -0.24 * phase
        _pose(armature, "upper_arm.R").rotation_euler.x = 0.24 * phase

    def head_turn(frame):
        amount = math.sin((frame - 1) / 23 * math.pi)
        _pose(armature, "head").rotation_euler.z = 0.48 * amount
        _pose(armature, "secondary_hair").rotation_euler.z = -0.16 * amount

    def look(frame):
        amount = math.sin((frame - 1) / 23 * math.pi)
        _pose(armature, "head").rotation_euler.x = -0.08 * amount
        blink = 0.86 if frame in (8, 16) else 1.0
        _pose(armature, "face_eye.L").scale.z = blink
        _pose(armature, "face_eye.R").scale.z = blink

    def arm_raise(frame):
        amount = math.sin((frame - 1) / 23 * math.pi)
        _pose(armature, "upper_arm.R").rotation_euler.y = -1.15 * amount
        _pose(armature, "forearm.R").rotation_euler.y = -0.35 * amount
        _pose(armature, "hand.R").rotation_euler.z = 0.18 * amount

    def speaking(frame):
        amount = 1.0 if frame in (8, 24) else 0.35
        _pose(armature, "face_mouth").scale.z = 1.0 + amount
        _pose(armature, "head").rotation_euler.z = 0.035 if frame == 8 else -0.025
        _pose(armature, "face_brow.L").rotation_euler.y = -0.08 * amount
        _pose(armature, "face_brow.R").rotation_euler.y = 0.08 * amount

    def shock(frame):
        amount = math.sin((frame - 1) / 23 * math.pi)
        _pose(armature, "head").rotation_euler.x = -0.15 * amount
        _pose(armature, "upper_arm.L").rotation_euler.y = 0.65 * amount
        _pose(armature, "upper_arm.R").rotation_euler.y = -0.65 * amount
        _pose(armature, "face_brow.L").location.z = 0.025 * amount
        _pose(armature, "face_brow.R").location.z = 0.025 * amount
        _pose(armature, "face_mouth").scale.z = 1.0 + 1.4 * amount

    def anger(frame):
        amount = math.sin((frame - 1) / 23 * math.pi)
        _pose(armature, "chest").rotation_euler.x = 0.08 * amount
        _pose(armature, "head").rotation_euler.x = 0.09 * amount
        _pose(armature, "face_brow.L").rotation_euler.y = 0.30 * amount
        _pose(armature, "face_brow.R").rotation_euler.y = -0.30 * amount
        _pose(armature, "hand.L").scale = (1.08, 1.08, 1.08)
        _pose(armature, "hand.R").scale = (1.08, 1.08, 1.08)

    builders = {
        "IDLE_BREATHING": idle,
        "WALK_2STEP": walk,
        "HEAD_TURN": head_turn,
        "LOOK_AT_CAMERA": look,
        "ARM_RAISE": arm_raise,
        "SPEAKING": speaking,
        "SHOCK": shock,
        "ANGER": anger,
    }
    for name in ACTIONS:
        _create_action(armature, name, builders[name])
    _reset_pose(armature)


def _point_at(object_, target):
    object_.rotation_euler = (
        (Vector(target) - object_.location).to_track_quat("-Z", "Y").to_euler()
    )


def _configure_scene(materials):
    scene = bpy.context.scene
    available_engines = {
        item.identifier for item in scene.render.bl_rna.properties["engine"].enum_items
    }
    scene.render.engine = (
        "BLENDER_EEVEE_NEXT"
        if "BLENDER_EEVEE_NEXT" in available_engines
        else "BLENDER_EEVEE"
    )
    scene.render.resolution_x = 512
    scene.render.resolution_y = 768
    scene.render.resolution_percentage = 100
    scene.render.fps = 24
    scene.render.film_transparent = False
    if hasattr(scene.render, "use_freestyle"):
        scene.render.use_freestyle = True
        line_set = scene.view_layers[0].freestyle_settings.linesets[0]
        line_style = line_set.linestyle
        if line_style is None:
            line_style = bpy.data.linestyles.new("Akira_Anime_Outline")
            line_set.linestyle = line_style
        line_style.color = (0.008, 0.006, 0.01)
        line_style.thickness = 1.25

    if scene.world is None:
        scene.world = bpy.data.worlds.new("Akira_World")
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (0.018, 0.022, 0.034, 1.0)
    background.inputs["Strength"].default_value = 0.35

    bpy.ops.mesh.primitive_cylinder_add(
        vertices=64, radius=1.35, depth=0.05, location=(0, 0, -0.015)
    )
    stage = bpy.context.object
    stage.name = "Akira_Stage"
    _assign(stage, materials["jacket"])
    bevel = stage.modifiers.new(name="StageBevel", type="BEVEL")
    bevel.width = 0.05
    bevel.segments = 2

    bpy.ops.object.light_add(type="AREA", location=(-2.8, -3.8, 4.1))
    key = bpy.context.object
    key.name = "Akira_Key_Light"
    key.data.energy = 820
    key.data.shape = "DISK"
    key.data.size = 3.2
    _point_at(key, (0, 0, 1.2))

    bpy.ops.object.light_add(type="AREA", location=(2.6, -1.6, 2.8))
    fill = bpy.context.object
    fill.name = "Akira_Red_Rim"
    fill.data.energy = 560
    fill.data.color = (1.0, 0.035, 0.02)
    fill.data.size = 2.0
    _point_at(fill, (0, 0, 1.45))

    bpy.ops.object.light_add(type="AREA", location=(0, 2.8, 3.4))
    rim = bpy.context.object
    rim.name = "Akira_Back_Rim"
    rim.data.energy = 680
    rim.data.color = (0.18, 0.26, 0.60)
    rim.data.size = 2.5
    _point_at(rim, (0, 0, 1.45))

    bpy.ops.object.camera_add(location=(0, -5.4, 1.35))
    camera = bpy.context.object
    camera.name = "Akira_Preview_Camera"
    camera.data.lens = 62
    _point_at(camera, (0, 0, 1.12))
    scene.camera = camera
    return camera


def _set_image_output(scene, path):
    image_settings = scene.render.image_settings
    if hasattr(image_settings, "media_type"):
        image_settings.media_type = "IMAGE"
    image_settings.file_format = "PNG"
    scene.render.filepath = str(path)


def _set_video_output(scene, path):
    image_settings = scene.render.image_settings
    if hasattr(image_settings, "media_type"):
        image_settings.media_type = "VIDEO"
    image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    scene.render.ffmpeg.constant_rate_factor = "MEDIUM"
    scene.render.filepath = str(path)
    scene.render.use_file_extension = True


def _render_outputs(camera, render_directory):
    scene = bpy.context.scene
    render_directory.mkdir(parents=True, exist_ok=True)
    target = (0, 0, 1.12)
    views = {
        "front": (0, -5.4, 1.35),
        "three-quarter": (-3.5, -4.0, 1.42),
        "profile": (-5.4, 0, 1.35),
        "back": (0, 5.4, 1.35),
    }
    stills = []
    for name, location in views.items():
        camera.location = location
        _point_at(camera, target)
        output = render_directory / f"akira-production-v1-{name}.png"
        _set_image_output(scene, output)
        bpy.ops.render.render(write_still=True)
        stills.append(str(output))

    scene.frame_start = 1
    scene.frame_end = 96
    camera.animation_data_clear()
    for frame, angle in (
        (1, 0),
        (25, math.pi / 2),
        (49, math.pi),
        (73, math.pi * 1.5),
        (96, math.tau),
    ):
        camera.location = (5.4 * math.sin(angle), -5.4 * math.cos(angle), 1.38)
        _point_at(camera, target)
        camera.keyframe_insert(data_path="location", frame=frame)
        camera.keyframe_insert(data_path="rotation_euler", frame=frame)
    if camera.animation_data and camera.animation_data.action:
        for fcurve in _action_fcurves(camera.animation_data.action, camera):
            for keyframe in fcurve.keyframe_points:
                keyframe.interpolation = "LINEAR"

    turntable = render_directory / "akira-production-v1-turntable.mp4"
    _set_video_output(scene, turntable)
    bpy.ops.render.render(animation=True)
    return stills, str(turntable)


def main():
    arguments = _arguments()
    model_output = Path(arguments.model_output).expanduser().resolve()
    render_output = Path(arguments.render_output).expanduser().resolve()
    model_output.parent.mkdir(parents=True, exist_ok=True)
    render_output.mkdir(parents=True, exist_ok=True)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    materials = _create_materials()
    grouped, head = _create_character(materials)
    armature = _create_rig()
    _parent_to_bones(armature, grouped)
    _add_shape_keys(head)
    _create_actions(armature)
    camera = _configure_scene(materials)
    bpy.context.scene.frame_start = 1
    bpy.context.scene.frame_end = 24
    bpy.ops.wm.save_as_mainfile(filepath=str(model_output))

    stills = []
    turntable = None
    if not arguments.skip_render:
        stills, turntable = _render_outputs(camera, render_output)

    manifest = {
        "schema_version": 1,
        "character_id": "akira",
        "milestone": "A9.1",
        "model_path": str(model_output),
        "shape_keys": list(SHAPE_KEYS),
        "actions": list(ACTIONS),
        "stills": stills,
        "turntable": turntable,
        "production_status": "PROTOTYPE_CANDIDATE",
    }
    manifest_path = render_output / "akira-production-v1-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("###AKIRA_MANIFEST_START###")
    print(json.dumps(manifest))
    print("###AKIRA_MANIFEST_END###")


if __name__ == "__main__":
    main()
