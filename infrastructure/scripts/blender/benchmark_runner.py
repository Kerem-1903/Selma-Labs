import argparse
import json
import sys
import time
import bpy

def run_benchmark(model_path):
    resolutions = [
        {"name": "540p", "x": 960, "y": 540},
        {"name": "720p", "x": 1280, "y": 720},
        {"name": "1080p", "x": 1920, "y": 1080},
    ]

    bpy.context.scene.render.engine = 'BLENDER_EEVEE_NEXT'
    if not hasattr(bpy.context.scene.render, 'engine') or bpy.context.scene.render.engine != 'BLENDER_EEVEE_NEXT':
         bpy.context.scene.render.engine = 'BLENDER_EEVEE'

    results = {}

    for res in resolutions:
        bpy.context.scene.render.resolution_x = res["x"]
        bpy.context.scene.render.resolution_y = res["y"]
        bpy.context.scene.render.resolution_percentage = 100

        # We render just 1 frame for benchmarking
        start_time = time.time()
        bpy.ops.render.render(write_still=False)
        end_time = time.time()

        frame_time_ms = (end_time - start_time) * 1000

        # Approximate FPS
        fps = 1000.0 / frame_time_ms if frame_time_ms > 0 else 0

        # VRAM in MB
        try:
            # Note: This is an approximation of peak memory used by Blender in MB
            vram_usage = (bpy.context.scene.render.engine == 'BLENDER_EEVEE' or bpy.context.scene.render.engine == 'BLENDER_EEVEE_NEXT')
            # Currently Blender API doesn't expose EEVEE VRAM directly via Python without parsing log output
            # We provide a placeholder for VRAM usage (or system RAM for CPU) via sys info
            import psutil
            process = psutil.Process()
            memory_info = process.memory_info()
            vram_mb = memory_info.rss / (1024 * 1024)
        except:
            vram_mb = 0

        results[res["name"]] = {
            "frame_time_ms": frame_time_ms,
            "fps": fps,
            "vram_mb": vram_mb
        }

    return results

def main():
    if "--" not in sys.argv:
        print("No arguments passed to script.")
        return

    argv = sys.argv[sys.argv.index("--") + 1:]

    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    args = parser.parse_args(argv)

    # Import model
    if args.model.endswith('.obj'):
        bpy.ops.wm.obj_import(filepath=args.model)
    elif args.model.endswith('.fbx'):
        bpy.ops.import_scene.fbx(filepath=args.model)
    elif args.model.endswith('.gltf') or args.model.endswith('.glb'):
        bpy.ops.import_scene.gltf(filepath=args.model)

    # Setup some basic scene elements
    bpy.ops.object.light_add(type='SUN', location=(5, 5, 5))
    bpy.ops.object.camera_add(location=(0, -5, 1), rotation=(1.5708, 0, 0))
    bpy.context.scene.camera = bpy.context.object

    benchmark_data = run_benchmark(args.model)

    print("---BENCHMARK_RESULT_START---")
    print(json.dumps(benchmark_data))
    print("---BENCHMARK_RESULT_END---")

if __name__ == "__main__":
    main()
