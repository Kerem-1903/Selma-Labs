import argparse
import json
import re
import sys

try:
    import bpy
except ImportError:
    # We might not be in blender yet
    bpy = None


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--command", required=True, choices=["validate", "preview"])
    parser.add_argument("--action", required=False)
    parser.add_argument("--output", required=False)
    parser.add_argument("--fps", type=int, default=24)

    # Ignore everything before '--'
    try:
        idx = sys.argv.index("--")
        args = sys.argv[idx + 1 :]
    except ValueError:
        args = []

    return parser.parse_args(args)


def _bone_tokens(name):
    return frozenset(token for token in re.split(r"[^a-z0-9]+", name.lower()) if token)


def _has_control(bone_names, control, limb, side):
    limb_tokens = {"arm", "upperarm"} if limb == "arm" else {"leg", "thigh", "shin"}
    side_tokens = {"l", "left"} if side == "l" else {"r", "right"}
    for bone_name in bone_names:
        tokens = _bone_tokens(bone_name)
        if (
            control in tokens
            and tokens.intersection(limb_tokens)
            and tokens.intersection(side_tokens)
        ):
            return True
    return False


def _select_main_armature(armatures, errors):
    marked = [
        armature for armature in armatures if armature.get("selma_main_rig") is True
    ]
    if len(marked) == 1:
        return marked[0]
    if len(marked) > 1:
        errors.append("Multiple armatures are marked as selma_main_rig.")
        return None
    if len(armatures) == 1:
        return armatures[0]
    if not armatures:
        errors.append("No armature found in the model.")
    else:
        errors.append("Multiple armatures found; mark exactly one as selma_main_rig.")
    return None


def _meshes_driven_by(meshes, armature):
    if armature is None:
        return []
    driven = []
    for mesh in meshes:
        parented = mesh.parent == armature
        modified = any(
            modifier.type == "ARMATURE" and modifier.object == armature
            for modifier in mesh.modifiers
        )
        if parented or modified:
            driven.append(mesh)
    return driven


def _linked_actions(armature):
    if armature is None or armature.animation_data is None:
        return {}
    animation_data = armature.animation_data
    actions = {}
    if animation_data.action is not None:
        actions[animation_data.action.name] = animation_data.action
    for track in animation_data.nla_tracks:
        for strip in track.strips:
            if strip.action is not None:
                actions[strip.action.name] = strip.action
    return actions


def validate_rig(model_path):
    bpy.ops.wm.open_mainfile(filepath=model_path)

    # We look for a main armature
    armatures = [obj for obj in bpy.data.objects if obj.type == "ARMATURE"]
    meshes = [obj for obj in bpy.data.objects if obj.type == "MESH"]

    errors = []
    armature = _select_main_armature(armatures, errors)

    has_ik_arm_l = False
    has_ik_arm_r = False
    has_ik_leg_l = False
    has_ik_leg_r = False
    has_fk_arm_l = False
    has_fk_arm_r = False
    has_fk_leg_l = False
    has_fk_leg_r = False
    has_secondary_hair = False
    has_secondary_jacket = False

    shape_keys = set()
    linked_actions = _linked_actions(armature)
    available_actions = sorted(linked_actions)

    if armature is not None:
        bone_names = [bone.name for bone in armature.data.bones]

        has_ik_arm_l = _has_control(bone_names, "ik", "arm", "l")
        has_ik_arm_r = _has_control(bone_names, "ik", "arm", "r")
        has_ik_leg_l = _has_control(bone_names, "ik", "leg", "l")
        has_ik_leg_r = _has_control(bone_names, "ik", "leg", "r")
        has_fk_arm_l = _has_control(bone_names, "fk", "arm", "l")
        has_fk_arm_r = _has_control(bone_names, "fk", "arm", "r")
        has_fk_leg_l = _has_control(bone_names, "fk", "leg", "l")
        has_fk_leg_r = _has_control(bone_names, "fk", "leg", "r")

        has_secondary_hair = any("hair" in _bone_tokens(name) for name in bone_names)
        has_secondary_jacket = any(
            "jacket" in _bone_tokens(name) for name in bone_names
        )

    for mesh in _meshes_driven_by(meshes, armature):
        if mesh.data.shape_keys:
            for kb in mesh.data.shape_keys.key_blocks:
                if kb.name != "Basis":
                    shape_keys.add(kb.name)

    result = {
        "has_ik_arm_l": has_ik_arm_l,
        "has_ik_arm_r": has_ik_arm_r,
        "has_ik_leg_l": has_ik_leg_l,
        "has_ik_leg_r": has_ik_leg_r,
        "has_fk_arm_l": has_fk_arm_l,
        "has_fk_arm_r": has_fk_arm_r,
        "has_fk_leg_l": has_fk_leg_l,
        "has_fk_leg_r": has_fk_leg_r,
        "has_secondary_hair": has_secondary_hair,
        "has_secondary_jacket": has_secondary_jacket,
        "shape_keys": sorted(shape_keys),
        "available_actions": available_actions,
        "is_valid": len(errors) == 0,
        "errors": errors,
    }

    print("###JSON_START###")
    print(json.dumps(result))
    print("###JSON_END###")


def preview_action(model_path, action_name, output_path, fps):
    bpy.ops.wm.open_mainfile(filepath=model_path)

    # Set FPS
    bpy.context.scene.render.fps = fps

    armatures = [obj for obj in bpy.data.objects if obj.type == "ARMATURE"]
    errors = []
    armature = _select_main_armature(armatures, errors)
    if armature is None:
        raise ValueError(" ".join(errors))

    linked_actions = _linked_actions(armature)
    if action_name not in linked_actions:
        raise ValueError(f"Action '{action_name}' is not linked to the main armature.")

    action = linked_actions[action_name]

    # Configure movie output before assigning the Blender 5.x slotted action.
    # Blender 5.1 can narrow ImageFormatSettings enums while a slot is active.
    available_engines = {
        item.identifier
        for item in bpy.context.scene.render.bl_rna.properties["engine"].enum_items
    }
    for engine in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        if engine in available_engines:
            bpy.context.scene.render.engine = engine
            break
    else:
        raise RuntimeError("No compatible EEVEE render engine is available.")
    image_settings = bpy.context.scene.render.image_settings
    if hasattr(image_settings, "media_type"):
        image_settings.media_type = "VIDEO"
    image_settings.file_format = "FFMPEG"
    bpy.context.scene.render.ffmpeg.format = "MPEG4"
    bpy.context.scene.render.ffmpeg.codec = "H264"
    bpy.context.scene.render.filepath = output_path
    bpy.context.scene.render.use_file_extension = True

    # Assign action to armature
    if not armature.animation_data:
        armature.animation_data_create()
    armature.animation_data.action = action

    # Set frame range based on action
    bpy.context.scene.frame_start = int(action.frame_range[0])
    bpy.context.scene.frame_end = int(action.frame_range[1])

    # Render animation
    bpy.ops.render.render(animation=True)


if __name__ == "__main__":
    if bpy is None:
        print("This script must be run inside Blender.")
        sys.exit(1)

    args = parse_args()

    if args.command == "validate":
        validate_rig(args.model)
    elif args.command == "preview":
        if not args.action or not args.output:
            print("Action and output must be specified for preview.")
            sys.exit(1)
        preview_action(args.model, args.action, args.output, args.fps)
