import asyncio
import io
import os
import sys
import time
from pathlib import Path
from PIL import Image, ImageDraw

# Ensure the project root is in sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from core.domain.value_objects.keyframe_generation_request import KeyframeGenerationRequest
from infrastructure.providers.keyframe.comfyui_keyframe_provider import ComfyUIKeyframeProvider
from infrastructure.storage.local_fs_storage import LocalFsStorage
from config.settings import get_settings

def build_akira_contract(
    shot_id: str,
    camera_lens: str,
    camera_angle: str,
    action: str,
    pose_storage_key: str | None = None,
) -> KeyframeGenerationRequest:
    return KeyframeGenerationRequest(
        shot_contract_id=shot_id,
        camera_constraints={"lens": camera_lens, "angle": camera_angle, "movement": "static"},
        action_constraints={"primary_action": action},
        visual_constraints={
            "lighting": "cinematic lighting",
            "environment_style": "cyberpunk city",
            **({"pose_storage_key": pose_storage_key} if pose_storage_key else {}),
        },
        reference_asset_ids=("ref-akira-1",),
        reference_storage_keys=("assets/references/akira_base.png",),
        width=1024,
        height=1024,
        seed=42
    )

async def setup_mock_akira_reference(storage: LocalFsStorage) -> None:
    # A technical smoke test mock. Visual consistency tests require a real image here.
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


async def setup_mock_pose_guide(storage: LocalFsStorage) -> str:
    pose_key = "assets/references/akira_pose.png"
    if await storage.exists(pose_key):
        return pose_key

    image = Image.new("RGB", (1024, 1024), color="black")
    draw = ImageDraw.Draw(image)
    joints = {
        "head": (520, 180),
        "neck": (500, 290),
        "left_hand": (300, 450),
        "right_hand": (730, 360),
        "hip": (480, 570),
        "left_foot": (250, 850),
        "right_foot": (760, 780),
    }
    for start, end, color in (
        ("head", "neck", "white"),
        ("neck", "left_hand", "red"),
        ("neck", "right_hand", "green"),
        ("neck", "hip", "blue"),
        ("hip", "left_foot", "yellow"),
        ("hip", "right_foot", "cyan"),
    ):
        draw.line((joints[start], joints[end]), fill=color, width=24)
    for point in joints.values():
        draw.ellipse(
            (point[0] - 14, point[1] - 14, point[0] + 14, point[1] + 14),
            fill="white",
        )
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    await storage.save(pose_key, buffer.getvalue(), "image/png")
    print(f"Created mock OpenPose guide at {pose_key}")
    return pose_key

async def run_smoke():
    settings = get_settings()
    storage = LocalFsStorage(settings.storage_root_dir)

    provider = ComfyUIKeyframeProvider(
        api_url=settings.comfyui_api_url,
        workflow_path=settings.comfyui_keyframe_workflow_path,
        storage=storage,
        checkpoint_name=settings.comfyui_keyframe_checkpoint,
        timeout_seconds=settings.comfyui_keyframe_timeout_seconds,
        poll_interval_seconds=settings.comfyui_keyframe_poll_interval_seconds
    )

    print("=" * 60)
    print("A5.2 ComfyUI Keyframe Generation Smoke Test")
    print(f"Target API: {settings.comfyui_api_url}")
    print(f"Workflow: {settings.comfyui_keyframe_workflow_path}")
    print("=" * 60)

    await setup_mock_akira_reference(storage)
    pose_key = await setup_mock_pose_guide(storage)

    shots = [
        ("shot-akira-face", "85mm", "extreme close-up", "intense stare at the camera", None),
        ("shot-akira-profile", "50mm", "side profile", "looking left towards a neon sign", None),
        ("shot-akira-action", "24mm", "wide full body", "sprinting forward with a sword drawn", pose_key),
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
    for shot_id, lens, angle, action, shot_pose_key in shots:
        print(f"\n--- Generating: {shot_id} ---")
        request = build_akira_contract(
            shot_id, lens, angle, action, shot_pose_key
        )
        print(f"Contract Constraints: {request.camera_constraints}, {request.action_constraints}")

        start_time = time.time()
        try:
            generated = await provider.generate_keyframe(request)
            duration = time.time() - start_time

            output_key = f"smoke/smoke_{shot_id}.png"
            ref = await storage.save(output_key, generated.image_bytes, generated.content_type)

            print("Status: SUCCESS")
            print(f"Time: {duration:.2f} seconds")
            print(f"Resolution: {generated.width}x{generated.height}")
            print(f"File Size: {len(generated.image_bytes) / 1024:.2f} KB")
            print(f"Saved to Physical Path: {ref.path}")

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
