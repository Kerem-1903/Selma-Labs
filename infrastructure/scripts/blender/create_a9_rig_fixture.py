"""Build a tiny A9-compliant .blend file for real Blender integration tests."""

import argparse
import sys

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

BONES = (
    "ik_arm.L",
    "ik_arm.R",
    "ik_leg.L",
    "ik_leg.R",
    "fk_arm.L",
    "fk_arm.R",
    "fk_leg.L",
    "fk_leg.R",
    "secondary_hair",
    "secondary_jacket",
)


def _parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    separator = sys.argv.index("--") if "--" in sys.argv else -1
    return parser.parse_args(sys.argv[separator + 1 :])


def _add_armature():
    bpy.ops.object.armature_add(enter_editmode=True, location=(0, 0, 0))
    armature = bpy.context.object
    armature.name = "Akira_A9_Rig"
    armature["selma_main_rig"] = True
    edit_bones = armature.data.edit_bones
    edit_bones.remove(edit_bones[0])
    for index, name in enumerate(BONES):
        bone = edit_bones.new(name)
        x = -0.8 + (index % 5) * 0.4
        z = 0.4 + (index // 5) * 0.8
        bone.head = (x, 0, z)
        bone.tail = (x, 0, z + 0.35)
    bpy.ops.object.mode_set(mode="OBJECT")
    return armature


def _add_character_mesh(armature):
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=16, ring_count=8, location=(0, 0, 1.2)
    )
    mesh = bpy.context.object
    mesh.name = "Akira_A9_Mesh"
    mesh.scale = (0.65, 0.4, 1.15)
    mesh.parent = armature
    modifier = mesh.modifiers.new(name="AkiraArmature", type="ARMATURE")
    modifier.object = armature
    mesh.shape_key_add(name="Basis")
    for shape_key in SHAPE_KEYS:
        mesh.shape_key_add(name=shape_key)
    return mesh


def _add_actions(armature):
    armature.animation_data_create()
    for index, name in enumerate(ACTIONS):
        armature.animation_data.action = None
        armature.location.x = 0.0
        armature.keyframe_insert(data_path="location", frame=1)
        armature.location.x = 0.02 * (index + 1)
        armature.keyframe_insert(data_path="location", frame=2)
        action = armature.animation_data.action
        action.name = name
        track = armature.animation_data.nla_tracks.new()
        track.name = f"A9::{name}"
        track.strips.new(name, 1, action)
        armature.animation_data.action = None
    armature.location.x = 0.0


def _point_at(obj, target):
    obj.rotation_euler = (
        (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()
    )


def _add_preview_scene():
    bpy.ops.object.camera_add(location=(0, -7, 1.8))
    camera = bpy.context.object
    _point_at(camera, (0, 0, 1.2))
    bpy.context.scene.camera = camera

    bpy.ops.object.light_add(type="AREA", location=(3, -4, 5))
    key_light = bpy.context.object
    key_light.data.energy = 900
    key_light.data.shape = "DISK"
    key_light.data.size = 5
    _point_at(key_light, (0, 0, 1.2))

    scene = bpy.context.scene
    scene.render.resolution_x = 320
    scene.render.resolution_y = 320
    scene.render.resolution_percentage = 100
    available_engines = {
        item.identifier for item in scene.render.bl_rna.properties["engine"].enum_items
    }
    for engine in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        if engine in available_engines:
            scene.render.engine = engine
            break
    else:
        raise RuntimeError("No compatible EEVEE render engine is available.")
    if scene.world is None:
        scene.world = bpy.data.worlds.new("A9_Smoke_World")
    scene.world.color = (0.025, 0.025, 0.025)


def main():
    arguments = _parse_args()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    armature = _add_armature()
    _add_character_mesh(armature)
    _add_actions(armature)
    _add_preview_scene()
    bpy.ops.wm.save_as_mainfile(filepath=arguments.output)


if __name__ == "__main__":
    main()
