"""Run a controlled Kaito left-profile IP-Adapter/OpenPose comparison."""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.application.services.character_identity_prompt_service import (  # noqa: E402
    CharacterIdentityPromptService,
)
from core.application.services.model_lock_service import load_model_lock  # noqa: E402
from core.domain.value_objects.character_creation_brief import (  # noqa: E402
    CharacterCreationBrief,
)
from infrastructure.providers.keyframe.comfyui_keyframe_provider import (  # noqa: E402
    ComfyUIKeyframeProvider,
)
from infrastructure.storage.local_fs_storage import LocalFsStorage  # noqa: E402


SEED = 2275216479
CANONICAL_KEY = "characters/kaito/v5/fullbody_anchor.png"
FACE_KEY = "characters/kaito/v5/face_anchor.png"
POSE_KEY = "characters/_pose_templates/pose_profile_left.png"
VARIANTS = (
    ("legacy-weak", (0.12, 0.10), 0.65),
    ("balanced", (0.35, 0.25), 0.80),
    ("identity-strong", (0.55, 0.35), 0.80),
)


async def run() -> None:
    storage = LocalFsStorage(ROOT / "output" / "production")
    brief_payload = json.loads(
        (ROOT / "tmp" / "kaito-turnaround-demo-brief.json").read_text(
            encoding="utf-8"
        )
    )
    brief = CharacterCreationBrief.from_dict(brief_payload)
    canonical = await storage.load(CANONICAL_KEY)
    face = await storage.load(FACE_KEY)
    references = (
        ("FRONT", CANONICAL_KEY, hashlib.sha256(canonical).hexdigest(), 0.55),
        ("FACE_CLOSEUP", FACE_KEY, hashlib.sha256(face).hexdigest(), 0.35),
    )
    request = CharacterIdentityPromptService().build_reference_request(
        brief,
        view="PROFILE_LEFT",
        direction=(
            "strict left side profile, full body neutral standing character reference, "
            "nose points to the left edge, only one eye visible, shoulders and hips "
            "overlap in silhouette, entire head and both feet visible"
        ),
        seed=SEED,
        references=references,
        pose_storage_key=POSE_KEY,
    )
    provider = ComfyUIKeyframeProvider(
        api_url="http://127.0.0.1:8188",
        workflow_path=ROOT / "assets" / "comfyui_keyframe_workflow.json",
        storage=storage,
        model_lock=load_model_lock(ROOT / "models.lock.json"),
        timeout_seconds=300.0,
        poll_interval_seconds=1.0,
    )
    output_dir = ROOT / "output" / "diagnostics" / "kaito-ipadapter-profile-ab"
    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, object]] = []
    for name, weights, end_at in VARIANTS:
        constraints = {
            **request.visual_constraints,
            "identity_reference_weights": list(weights),
            "identity_start_at": 0.0,
            "identity_end_at": end_at,
            "pose_strength": 1.0,
            "workflow_version": f"kaito-ipadapter-profile-ab:{name}",
        }
        variant_request = replace(
            request,
            shot_contract_id=f"kaito-profile-ab-{name}",
            visual_constraints=constraints,
        )
        generated = await provider.generate_keyframe(variant_request)
        image_path = output_dir / f"{name}.png"
        image_path.write_bytes(generated.image_bytes)
        results.append(
            {
                "variant": name,
                "image_path": str(image_path),
                "seed": SEED,
                "identity_reference_weights": list(weights),
                "identity_start_at": 0.0,
                "identity_end_at": end_at,
                "pose_strength": 1.0,
                "content_hash": hashlib.sha256(generated.image_bytes).hexdigest(),
                "width": generated.width,
                "height": generated.height,
                "metadata": generated.metadata,
            }
        )
        print(f"completed {name}: {image_path}", flush=True)
    manifest = output_dir / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "source": CANONICAL_KEY,
                "face_reference": FACE_KEY,
                "pose": POSE_KEY,
                "seed": SEED,
                "lora": None,
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"manifest: {manifest}", flush=True)


if __name__ == "__main__":
    asyncio.run(run())
