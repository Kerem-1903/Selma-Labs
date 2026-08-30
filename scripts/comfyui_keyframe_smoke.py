import asyncio
import os
import sys
import time

from core.domain.entities.shot_contract import ShotContract
from core.domain.value_objects.shot_constraints import ActionConstraints, CameraConstraints, VisualConstraints
from core.domain.value_objects.keyframe_generation_request import KeyframeGenerationRequest
from infrastructure.providers.keyframe.comfyui_keyframe_provider import ComfyUIKeyframeProvider
from config.settings import get_settings

def build_akira_contract(shot_id: str, camera_lens: str, camera_angle: str, action: str) -> KeyframeGenerationRequest:
    return KeyframeGenerationRequest(
        shot_contract_id=shot_id,
        camera_constraints={"lens": camera_lens, "angle": camera_angle, "movement": "static"},
        action_constraints={"primary_action": action},
        visual_constraints={"lighting": "cinematic lighting", "environment_style": "cyberpunk city"},
        # A mock reference asset that we simulate injecting
        reference_asset_ids=("ref-akira-1",),
        reference_storage_keys=("assets/references/akira_base.png",),
        width=1024,
        height=1024,
        seed=42
    )

async def run_smoke():
    settings = get_settings()
    provider = ComfyUIKeyframeProvider(
        api_url=settings.comfyui_api_url,
        workflow_path=settings.comfyui_keyframe_workflow_path
    )

    print("=" * 60)
    print("A5.2 ComfyUI Keyframe Generation Smoke Test")
    print(f"Target API: {settings.comfyui_api_url}")
    print(f"Workflow: {settings.comfyui_keyframe_workflow_path}")
    print("=" * 60)

    shots = [
        ("shot-akira-face", "85mm", "extreme close-up", "intense stare at the camera"),
        ("shot-akira-profile", "50mm", "side profile", "looking left towards a neon sign"),
        ("shot-akira-action", "24mm", "wide full body", "sprinting forward with a sword drawn")
    ]

    import aiohttp

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(settings.comfyui_api_url, timeout=2) as response:
                if response.status != 200:
                    print(f"WARNING: ComfyUI returned {response.status}")
    except Exception as e:
        print(f"ERROR: Could not connect to ComfyUI. Is it running on {settings.comfyui_api_url}?")
        print(f"Exception: {e}")
        print("Please start ComfyUI and try again.")
        sys.exit(1)

    for shot_id, lens, angle, action in shots:
        print(f"\n--- Generating: {shot_id} ---")
        request = build_akira_contract(shot_id, lens, angle, action)
        print(f"Contract Constraints: {request.camera_constraints}, {request.action_constraints}")

        start_time = time.time()
        try:
            generated = await provider.generate_keyframe(request)
            duration = time.time() - start_time

            output_path = f"output/smoke_{shot_id}.png"
            os.makedirs("output", exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(generated.image_bytes)

            print("Status: SUCCESS")
            print(f"Time: {duration:.2f} seconds")
            print(f"Resolution: {generated.width}x{generated.height}")
            print(f"File Size: {len(generated.image_bytes) / 1024:.2f} KB")
            print(f"Output: {output_path}")

        except Exception as e:
            duration = time.time() - start_time
            print("Status: FAILED")
            print(f"Time: {duration:.2f} seconds")
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(run_smoke())
