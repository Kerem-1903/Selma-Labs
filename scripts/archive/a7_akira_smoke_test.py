from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import aiohttp
from PIL import Image, ImageStat

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.provider_registry import get_keyframe_generation_provider
from config.settings import get_settings
from core.application.services.candidate.candidate_evaluation_service import (
    CandidateEvaluationService,
)
from core.application.services.character_reference_asset_service import (
    CharacterReferenceAssetService,
)
from core.application.services.keyframe_generation_service import KeyframeGenerationService
from core.domain.entities.character_bible import CharacterBible
from core.domain.entities.character_state import CharacterState
from core.domain.entities.shot_contract import ShotContract
from core.domain.value_objects.character_identity import IdentityConstraints, ReferenceView
from core.domain.value_objects.shot_constraints import (
    ActionConstraints,
    CameraConstraints,
    VisualConstraints,
)
from core.domain.value_objects.style_profile import StyleProfile
from infrastructure.repositories.candidate.sqlite_keyframe_candidate_repository import (
    SqliteKeyframeCandidateRepository,
)
from infrastructure.repositories.local_json_character_bible_repository import (
    LocalJsonCharacterBibleRepository,
)
from infrastructure.repositories.local_json_shot_storyboard_repository import (
    LocalJsonShotStoryboardRepository,
)
from infrastructure.storage.local_fs_storage import LocalFsStorage


def _reference_path(storage_root: Path) -> Path:
    configured = os.environ.get("A7_AKIRA_REFERENCE_PATH", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (storage_root / "assets/references/akira_base.png").resolve()


def _read_real_reference(path: Path) -> tuple[bytes, str]:
    if not path.is_file():
        raise FileNotFoundError(
            "A real Akira reference is required. Set A7_AKIRA_REFERENCE_PATH "
            f"or place it at {path}."
        )
    content_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }
    content_type = content_types.get(path.suffix.lower())
    if content_type is None:
        raise ValueError("Akira reference must be PNG, JPEG, or WebP.")
    with Image.open(path) as image:
        image.verify()
    with Image.open(path) as image:
        variance = sum(ImageStat.Stat(image.convert("RGB")).var)
    if variance < 5.0:
        raise ValueError("Akira reference appears blank; a real character image is required.")
    return path.read_bytes(), content_type


async def _select_candidate(candidate_count: int) -> int:
    configured = os.environ.get("A7_APPROVE_INDEX", "").strip()
    raw = configured or await asyncio.to_thread(
        input, f"Approve candidate index [0-{candidate_count - 1}]: "
    )
    selected = int(raw)
    if not 0 <= selected < candidate_count:
        raise ValueError("Approved candidate index is outside the generated range.")
    return selected


async def run_smoke() -> None:
    settings = get_settings()
    storage_root = Path(settings.storage_root_dir).expanduser().resolve()
    storage = LocalFsStorage(str(storage_root))
    reference_bytes, reference_content_type = _read_real_reference(
        _reference_path(storage_root)
    )

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(settings.comfyui_api_url, timeout=3) as response:
                if response.status != 200:
                    raise RuntimeError(f"ComfyUI health check returned HTTP {response.status}.")
        except Exception as error:
            raise RuntimeError(
                f"ComfyUI is not reachable at {settings.comfyui_api_url}."
            ) from error

    workspace = PROJECT_ROOT / "output" / "a7_akira_smoke"
    workspace.mkdir(parents=True, exist_ok=True)
    candidate_repository = SqliteKeyframeCandidateRepository(
        str(workspace / "candidates.db")
    )
    evaluation = CandidateEvaluationService(candidate_repository)
    bibles = LocalJsonCharacterBibleRepository(workspace / "bibles")
    storyboards = LocalJsonShotStoryboardRepository(workspace / "storyboards")

    bible = CharacterBible(
        character_id="akira",
        identity_constraints=IdentityConstraints(
            eye_color="brown",
            hair="black hair with a recognizable silhouette",
            facial_geometry="angular anime face",
            body_proportions="athletic",
            silhouette="lean swordswoman",
        ),
        style_profile=StyleProfile(
            base_style="cinematic anime",
            negative_prompts=["identity drift", "duplicate character", "extra limbs"],
        ),
    )
    await CharacterReferenceAssetService(storage).save_reference(
        bible,
        ReferenceView.FRONT,
        reference_bytes,
        reference_content_type,
    )
    await bibles.save(bible)

    comfy_settings = settings.model_copy(
        update={"keyframe_generation_provider": "comfyui"}
    )
    provider = get_keyframe_generation_provider(comfy_settings, storage=storage)
    service = KeyframeGenerationService(
        generator=provider,
        storage=storage,
        character_bibles=bibles,
        storyboards=storyboards,
        candidate_evaluation=evaluation,
    )
    shot_id = datetime.now(timezone.utc).strftime("akira-a7-%Y%m%d-%H%M%S")
    contract = ShotContract(
        id=shot_id,
        camera_constraints=CameraConstraints("wide full body", "35mm", "tracking"),
        action_constraints=ActionConstraints("Akira walks through a neon street"),
        visual_constraints=VisualConstraints("cinematic neon", "anime city", "rain"),
        required_character_states=[
            CharacterState("akira", "battle-jacket", [], ["katana"])
        ],
    )

    print(f"Generating three review candidates for {shot_id}...")
    await service.generate_candidates(shot_contract=contract, count=3)
    candidates = await evaluation.get_candidates_for_shot(shot_id)
    if len(candidates) != 3:
        raise RuntimeError(f"Expected 3 candidates, found {len(candidates)}.")
    for index, candidate in enumerate(candidates):
        if not await storage.exists(candidate.storage_key):
            raise RuntimeError(f"Candidate asset is missing: {candidate.storage_key}")
        print(f"[{index}] {candidate.status.value}: {candidate.storage_key}")

    selected_index = await _select_candidate(len(candidates))
    selected = candidates[selected_index]
    await evaluation.approve_candidate(selected.id)
    storyboard = await service.commit_approved_candidate(shot_id)
    persisted = await storyboards.load(storyboard.id)
    if persisted != storyboard or len(storyboard.frames) != 1:
        raise RuntimeError("Committed storyboard did not round-trip correctly.")
    print(f"APPROVED STORAGE KEY: {storyboard.frames[0].storage_key}")
    print(f"STORYBOARD: {workspace / 'storyboards' / f'{storyboard.id}.json'}")


if __name__ == "__main__":
    try:
        asyncio.run(run_smoke())
    except Exception as error:
        print(f"A7 smoke test failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
