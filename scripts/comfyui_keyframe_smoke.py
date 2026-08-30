import asyncio
import os
import sys
import time
from pathlib import Path
from PIL import Image

from core.domain.value_objects.keyframe_generation_request import KeyframeGenerationRequest
from infrastructure.providers.keyframe.comfyui_keyframe_provider import ComfyUIKeyframeProvider
from infrastructure.storage.local_fs_storage import LocalFsStorage
from config.settings import get_settings

def build_akira_contract(shot_id: str, camera_lens: str, camera_angle: str, action: str) -> KeyframeGenerationRequest:
    return KeyframeGenerationRequest(
        shot_contract_id=shot_id,
        camera_constraints={"lens": camera_lens, "angle": camera_angle, "movement": "static"},
        action_constraints={"primary_action": action},
        visual_constraints={"lighting": "cinematic lighting", "environment_style": "cyberpunk city"},
        reference_asset_ids=("ref-akira-1",),
        reference_storage_keys=("assets/references/akira_base.png",),
        width=1024,
        height=1024,
        seed=42
    )

async def setup_mock_akira_reference(storage: LocalFsStorage) -> None:
    # Create a 1x1 black image simulating an Akira reference for the smoke test
    # so we have an actual file on disk.
    akira_key = "assets/references/akira_base.png"
    if not await storage.exists(akira_key):
        print(f"Creating mock Akira reference at {akira_key}")
        img = Image.new('RGB', (1024, 1024), color='black')
        tmp_path = "tmp_akira.png"
        img.save(tmp_path)
        with open(tmp_path, "rb") as f:
            await storage.save(akira_key, f.read(), "image/png")
        os.remove(tmp_path)
    else:
        print(f"Mock Akira reference exists at {akira_key}")

async def run_smoke():
    settings = get_settings()
    provider = ComfyUIKeyframeProvider(
        api_url=settings.comfyui_api_url,
        workflow_path=settings.comfyui_keyframe_workflow_path
    )
    storage = LocalFsStorage(settings.storage_root_dir)

    print("=" * 60)
    print("A5.2 ComfyUI Keyframe Generation Smoke Test")
    print(f"Target API: {settings.comfyui_api_url}")
    print(f"Workflow: {settings.comfyui_keyframe_workflow_path}")
    print("=" * 60)

    await setup_mock_akira_reference(storage)

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

    failures = 0
    for shot_id, lens, angle, action in shots:
        print(f"\n--- Generating: {shot_id} ---")
        request = build_akira_contract(shot_id, lens, angle, action)
        print(f"Contract Constraints: {request.camera_constraints}, {request.action_constraints}")

        start_time = time.time()
        try:
            generated = await provider.generate_keyframe(request)
            duration = time.time() - start_time

            output_key = f"output/smoke_{shot_id}.png"
            await storage.save(output_key, generated.image_bytes, generated.content_type)

            print("Status: SUCCESS")
            print(f"Time: {duration:.2f} seconds")
            print(f"Resolution: {generated.width}x{generated.height}")
            print(f"File Size: {len(generated.image_bytes) / 1024:.2f} KB")
            print(f"Saved to Virtual Storage: {output_key}")

        except Exception as e:
            duration = time.time() - start_time
            print("Status: FAILED")
            print(f"Time: {duration:.2f} seconds")
            print(f"Error: {e}")
            failures += 1

    if failures > 0:
        print(f"\n{failures} shot(s) failed. Exiting with code 1.")
        sys.exit(1)
    else:
        print("\nAll shots generated successfully.")

if __name__ == "__main__":
    asyncio.run(run_smoke())
