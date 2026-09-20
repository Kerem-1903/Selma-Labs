"""Generate a source-led FLUX.2 pose set through SELMA's locked provider."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import io
import json
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.provider_registry import get_keyframe_generation_provider
from config.settings import get_settings
from core.domain.value_objects.keyframe_generation_request import (
    KeyframeGenerationRequest,
)
from infrastructure.storage.local_fs_storage import LocalFsStorage

POSES = (
    (
        "neutral-alert",
        "an alert neutral standing pose, shoulders level, feet balanced, the single blade "
        "lowered naturally in her right hand",
    ),
    (
        "walking",
        "a controlled forward walking pose, one foot clearly ahead, coat moving slightly, "
        "the single blade kept low in her right hand",
    ),
    (
        "investigative-crouch",
        "a low investigative crouch examining the ground, stable anatomy, the single blade "
        "still lowered and safely controlled in her right hand",
    ),
    (
        "defensive-guard",
        "a balanced defensive guard pose, torso turned three quarters, the single blade held "
        "diagonally across the body in her right hand",
    ),
    (
        "kneeling-ready",
        "a composed one-knee kneeling pose, head raised and observant, the single blade resting "
        "beside her right leg while remaining in her right hand",
    ),
)


async def _run(source_path: Path, output_dir: Path, character_id: str) -> None:
    settings = get_settings().model_copy(
        update={
            "runtime_profile": "production",
            "keyframe_generation_provider": "comfyui-flux2-edit",
        }
    )
    storage = LocalFsStorage(settings.keyframe_storage_root_dir)
    provider = get_keyframe_generation_provider(settings, storage=storage)
    source_bytes = source_path.read_bytes()
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    source_key = f"characters/{character_id}/flux-pose-set/source-{source_hash[:12]}.png"
    await storage.save(source_key, source_bytes, "image/png")

    output_dir.mkdir(parents=True, exist_ok=True)
    frames: list[Image.Image] = []
    entries: list[dict[str, object]] = []
    for index, (pose_id, pose) in enumerate(POSES, start=1):
        instruction = (
            "Edit Picture 1 into a new full-body pose. Keep exactly the same adult woman, face, "
            "cold green eyes, jaw-length black bob haircut, body proportions, dark green high-collar "
            "coat, black trousers, boots, all seams, trim, colors, and exactly one long blade. "
            f"Change only her body pose to {pose}. Keep the complete head and both feet visible on "
            "the same plain light gray studio background. Do not redesign, mirror, crop, add another "
            "person, add another weapon, change clothing, or change facial identity."
        )
        request = KeyframeGenerationRequest(
            shot_contract_id=f"{character_id}-flux-pose-{index}",
            camera_constraints={"angle": "full body", "movement": "locked"},
            action_constraints={"primary_action": pose},
            visual_constraints={
                "image_edit_prompt": instruction,
                "image_edit_negative_mode": "append",
                "image_edit_negative_prompts": [
                    "identity drift",
                    "different face",
                    "different outfit",
                    "extra person",
                    "extra weapon",
                    "duplicate limbs",
                    "cropped head",
                    "cropped feet",
                    "text",
                    "watermark",
                ],
                "identity_reference_weights": [1.0],
                "image_edit_megapixels": 1.0,
                "sampling_steps": 4,
                "guidance_scale": 1.0,
            },
            reference_asset_ids=(f"source:{source_hash[:12]}",),
            reference_storage_keys=(source_key,),
            width=1024,
            height=1024,
            seed=2026091900 + index,
        )
        generated = await provider.generate_keyframe(request)
        filename = f"{index:02d}-{pose_id}.png"
        destination = output_dir / filename
        destination.write_bytes(generated.image_bytes)
        with Image.open(io.BytesIO(generated.image_bytes)) as image:
            tile = image.convert("RGB")
            tile.thumbnail((512, 512), Image.Resampling.LANCZOS)
            frames.append(tile.copy())
        entries.append(
            {
                "pose_id": pose_id,
                "file": filename,
                "seed": request.seed,
                "provider": provider.name,
                "source_hash": source_hash,
                "output_hash": hashlib.sha256(generated.image_bytes).hexdigest(),
                "metadata": generated.metadata,
            }
        )

    sheet = Image.new("RGB", (512 * len(frames), 512), "#e8edf2")
    for index, frame in enumerate(frames):
        sheet.paste(frame, (index * 512, 0))
    sheet.save(output_dir / "contact-sheet.png", "PNG")
    manifest = {
        "schema_version": 1,
        "character_id": character_id,
        "source": str(source_path.resolve()),
        "source_hash": source_hash,
        "provider": provider.name,
        "status": "UNAPPROVED_POSE_SET",
        "poses": entries,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--character-id", default="sera")
    arguments = parser.parse_args()
    asyncio.run(_run(arguments.source, arguments.output_dir, arguments.character_id))


if __name__ == "__main__":
    main()
