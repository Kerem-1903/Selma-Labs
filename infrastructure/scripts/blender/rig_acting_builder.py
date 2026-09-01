import argparse
import json
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
        args = sys.argv[idx+1:]
    except ValueError:
        args = []

    return parser.parse_args(args)


def validate_rig(model_path):
    # Load model
    bpy.ops.wm.open_mainfile(filepath=model_path)

    # We look for a main armature
    armatures = [obj for obj in bpy.data.objects if obj.type == 'ARMATURE']
    meshes = [obj for obj in bpy.data.objects if obj.type == 'MESH']

    errors = []
    if not armatures:
        errors.append("No armature found in the model.")

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
    available_actions = [action.name for action in bpy.data.actions]

    if armatures:
        armature = armatures[0]
        # In a real scenario, we would check specific bone names or constraints.
        # For demonstration, we'll check if bones with specific substrings exist.
        bone_names = [bone.name.lower() for bone in armature.data.bones]

        has_ik_arm_l = any("ik" in name and "arm" in name and "l" in name for name in bone_names)
        has_ik_arm_r = any("ik" in name and "arm" in name and "r" in name for name in bone_names)
        has_ik_leg_l = any("ik" in name and "leg" in name and "l" in name for name in bone_names)
        has_ik_leg_r = any("ik" in name and "leg" in name and "r" in name for name in bone_names)
        has_fk_arm_l = any("fk" in name and "arm" in name and "l" in name for name in bone_names)
        has_fk_arm_r = any("fk" in name and "arm" in name and "r" in name for name in bone_names)
        has_fk_leg_l = any("fk" in name and "leg" in name and "l" in name for name in bone_names)
        has_fk_leg_r = any("fk" in name and "leg" in name and "r" in name for name in bone_names)

        has_secondary_hair = any("hair" in name for name in bone_names)
        has_secondary_jacket = any("jacket" in name for name in bone_names)

    for mesh in meshes:
        if mesh.data.shape_keys:
            for kb in mesh.data.shape_keys.key_blocks:
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
        "shape_keys": list(shape_keys),
        "available_actions": available_actions,
        "is_valid": len(errors) == 0,
        "errors": errors
    }

    print("###JSON_START###")
    print(json.dumps(result))
    print("###JSON_END###")


def preview_action(model_path, action_name, output_path, fps):
    # Load model
    bpy.ops.wm.open_mainfile(filepath=model_path)

    # Set FPS
    bpy.context.scene.render.fps = fps

    # Find armature
    armatures = [obj for obj in bpy.data.objects if obj.type == 'ARMATURE']
    if not armatures:
        raise ValueError("No armature found.")

    armature = armatures[0]

    # Find action
    if action_name not in bpy.data.actions:
        raise ValueError(f"Action '{action_name}' not found.")

    action = bpy.data.actions[action_name]

    # Assign action to armature
    if not armature.animation_data:
        armature.animation_data_create()
    armature.animation_data.action = action

    # Set frame range based on action
    bpy.context.scene.frame_start = int(action.frame_range[0])
    bpy.context.scene.frame_end = int(action.frame_range[1])

    # Setup EEVEE render
    bpy.context.scene.render.engine = 'BLENDER_EEVEE_NEXT' if hasattr(bpy.types.RenderSettings, 'engine') and 'BLENDER_EEVEE_NEXT' in [e.identifier for e in bpy.types.RenderEngine.bl_rna.properties['engine'].enum_items] else 'BLENDER_EEVEE'
    bpy.context.scene.render.filepath = output_path
    bpy.context.scene.render.image_settings.file_format = 'FFMPEG'
    bpy.context.scene.render.ffmpeg.format = 'MPEG4'
    bpy.context.scene.render.ffmpeg.codec = 'H264'

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
