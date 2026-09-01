import argparse
import json
import os
import sys
import time
import bpy

def setup_eevee_toon_shader(contour_type="inverted_hull", use_custom_face_normals=True):
    # Setup base materials for toon shader
    # Check if we have an active object
    obj = bpy.context.active_object
    if not obj or obj.type != 'MESH':
        return

    # Delete existing materials
    obj.data.materials.clear()

    # Create new material
    mat = bpy.data.materials.new(name="ToonShader")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links

    # Clear default nodes
    for node in nodes:
        nodes.remove(node)

    # Diffuse BSDF
    diffuse = nodes.new(type="ShaderNodeBsdfDiffuse")
    diffuse.location = (-600, 0)

    # Custom Face Normals logic for spherical shading
    if use_custom_face_normals:
        normal_node = nodes.new(type="ShaderNodeNormal")
        normal_node.location = (-800, -200)
        links.new(normal_node.outputs[0], diffuse.inputs['Normal'])

    # Shader to RGB (only works in EEVEE)
    shader_to_rgb = nodes.new(type="ShaderNodeShaderToRGB")
    shader_to_rgb.location = (-400, 0)

    # ColorRamp (2-band, Akira's palette colors)
    color_ramp = nodes.new(type="ShaderNodeValToRGB")
    color_ramp.location = (-200, 0)
    color_ramp.color_ramp.interpolation = 'CONSTANT'
    color_ramp.color_ramp.elements[0].position = 0.5
    color_ramp.color_ramp.elements[0].color = (0.2, 0.2, 0.2, 1.0) # Dark shade
    color_ramp.color_ramp.elements[1].position = 0.51
    color_ramp.color_ramp.elements[1].color = (0.8, 0.0, 0.0, 1.0) # Akira Red

    # Material Output
    output = nodes.new(type="ShaderNodeOutputMaterial")
    output.location = (200, 0)

    # Connect them
    links.new(diffuse.outputs[0], shader_to_rgb.inputs[0])
    links.new(shader_to_rgb.outputs[0], color_ramp.inputs[0])
    links.new(color_ramp.outputs[0], output.inputs[0])

    obj.data.materials.append(mat)

    # Outline / Contour logic
    if contour_type == "inverted_hull":
        # Inverted Hull (Solidify modifier + backface culling)
        mat_outline = bpy.data.materials.new(name="Outline")
        mat_outline.use_nodes = True
        mat_outline.use_backface_culling = True # Essential for inverted hull

        nodes_out = mat_outline.node_tree.nodes
        links_out = mat_outline.node_tree.links
        for n in nodes_out:
            nodes_out.remove(n)

        emission = nodes_out.new(type="ShaderNodeEmission")
        emission.inputs[0].default_value = (0, 0, 0, 1) # Black outline

        out = nodes_out.new(type="ShaderNodeOutputMaterial")
        links_out.new(emission.outputs[0], out.inputs[0])

        obj.data.materials.append(mat_outline)

        # Add Solidify modifier
        mod = obj.modifiers.new(name="Outline", type='SOLIDIFY')
        mod.thickness = 0.02
        mod.offset = 1.0
        mod.use_flip_normals = True
        mod.material_offset = 1

    elif contour_type == "freestyle":
        bpy.context.scene.render.use_freestyle = True
        freestyle = bpy.context.view_layer.freestyle_settings
        freestyle.linesets.new("LineSet")

    elif contour_type == "grease_pencil":
        bpy.ops.object.gpencil_add(align='WORLD', location=(0, 0, 0), type='LRT_OBJECT')
        gp_obj = bpy.context.active_object
        if gp_obj:
            gp_mod = gp_obj.grease_pencil_modifiers.new(name="LineArt", type='GP_LINEART')
            gp_mod.source_type = 'OBJECT'
            gp_mod.source_object = obj

def create_turntable(frame_count=36):
    # Create empty at center
    bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0, 0, 0))
    empty = bpy.context.active_object

    # Assuming camera exists
    camera = bpy.context.scene.camera
    if camera:
        # Parent camera to empty
        camera.parent = empty

        # Animate empty rotation
        empty.rotation_euler = (0, 0, 0)
        empty.keyframe_insert(data_path="rotation_euler", frame=1)

        import math
        empty.rotation_euler = (0, 0, math.pi * 2)
        empty.keyframe_insert(data_path="rotation_euler", frame=frame_count+1)

        # Make interpolation linear
        for fcurve in empty.animation_data.action.fcurves:
            for keyframe in fcurve.keyframe_points:
                keyframe.interpolation = 'LINEAR'

    bpy.context.scene.frame_start = 1
    bpy.context.scene.frame_end = frame_count

def render(model_path, output_dir, quality, render_id):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Set up rendering engine to EEVEE
    bpy.context.scene.render.engine = 'BLENDER_EEVEE_NEXT'
    if not hasattr(bpy.context.scene.render, 'engine') or bpy.context.scene.render.engine != 'BLENDER_EEVEE_NEXT':
        # fallback for Blender 4.1 or older where it is BLENDER_EEVEE
         bpy.context.scene.render.engine = 'BLENDER_EEVEE'

    # Resolution based on quality
    if quality == "preview":
        res_x, res_y = 640, 360
    elif quality == "high":
        res_x, res_y = 1920, 1080
    else:
        res_x, res_y = 1280, 720

    bpy.context.scene.render.resolution_x = res_x
    bpy.context.scene.render.resolution_y = res_y
    bpy.context.scene.render.resolution_percentage = 100

    # Import model
    if model_path.endswith('.obj'):
        bpy.ops.wm.obj_import(filepath=model_path)
    elif model_path.endswith('.fbx'):
        bpy.ops.import_scene.fbx(filepath=model_path)
    elif model_path.endswith('.gltf') or model_path.endswith('.glb'):
        bpy.ops.import_scene.gltf(filepath=model_path)

    # Scale and center logic could go here depending on standard sizes

    # Ensure lighting
    bpy.ops.object.light_add(type='SUN', location=(5, 5, 5))
    sun = bpy.context.active_object
    sun.data.energy = 5.0

    # Apply Shader
    setup_eevee_toon_shader()

    # Turntable setup
    frame_count = 36
    create_turntable(frame_count)

    # Output settings
    output_video = os.path.join(output_dir, f"{render_id}_turntable.mp4")
    bpy.context.scene.render.filepath = output_video
    bpy.context.scene.render.image_settings.file_format = 'FFMPEG'
    bpy.context.scene.render.ffmpeg.format = 'MPEG4'
    bpy.context.scene.render.ffmpeg.codec = 'H264'
    bpy.context.scene.render.ffmpeg.constant_rate_factor = 'MEDIUM'

    start_time = time.time()

    # Render animation
    bpy.ops.render.render(animation=True)

    end_time = time.time()
    total_time = end_time - start_time
    avg_frame_time = (total_time / frame_count) * 1000 # ms

    manifest = {
        "render_id": render_id,
        "frame_count": frame_count,
        "avg_frame_time_ms": avg_frame_time,
        "resolution": f"{res_x}x{res_y}",
        "output_video_path": output_video,
        "engine": "EEVEE"
    }

    manifest_path = os.path.join(output_dir, f"{render_id}_manifest.json")
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f)

    print(f"Render complete. Manifest saved to {manifest_path}")

def main():
    if "--" not in sys.argv:
        print("No arguments passed to script.")
        return

    argv = sys.argv[sys.argv.index("--") + 1:]

    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--quality", default="preview")
    parser.add_argument("--render-id", required=True)

    args = parser.parse_args(argv)

    # Clear default scene
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)

    # Add a camera
    bpy.ops.object.camera_add(location=(0, -5, 1), rotation=(1.5708, 0, 0))
    bpy.context.scene.camera = bpy.context.object

    render(args.model, args.output_dir, args.quality, args.render_id)

if __name__ == "__main__":
    main()
