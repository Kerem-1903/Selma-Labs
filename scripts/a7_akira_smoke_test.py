import asyncio
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from datetime import datetime, timezone
from core.application.services.keyframe_generation_service import KeyframeGenerationService
from core.application.services.candidate.candidate_evaluation_service import CandidateEvaluationService
from core.domain.entities.candidate.keyframe_candidate import CandidateStatus
from core.domain.entities.shot_contract import ShotContract
from core.domain.value_objects.shot_constraints import CameraConstraints, ActionConstraints, VisualConstraints
from infrastructure.repositories.candidate.sqlite_keyframe_candidate_repository import SqliteKeyframeCandidateRepository
from infrastructure.repositories.local_json_shot_storyboard_repository import LocalJsonShotStoryboardRepository
from infrastructure.repositories.local_json_character_bible_repository import LocalJsonCharacterBibleRepository
from infrastructure.providers.keyframe.comfyui_keyframe_provider import ComfyUIKeyframeProvider
from infrastructure.storage.local_fs_storage import LocalFsStorage
import httpx
from pydantic_settings import BaseSettings

class DummySettings(BaseSettings):
    comfyui_host: str = "127.0.0.1"
    comfyui_port: int = 8188
    comfyui_https: bool = False
    workflow_search_paths: list[str] = ["infrastructure/providers/video/comfyui/workflows"]

async def main():
    print("Starting A7 Akira Smoke Test...")
    workspace = "./workspace/a7_smoke"
    os.makedirs(workspace, exist_ok=True)

    # 1. Setup real infra (using local fs and sqlite)
    candidate_repo = SqliteKeyframeCandidateRepository(f"{workspace}/candidates.db")
    eval_service = CandidateEvaluationService(candidate_repo)

    storyboards = LocalJsonShotStoryboardRepository(f"{workspace}/storyboards")
    bibles = LocalJsonCharacterBibleRepository(f"{workspace}/bibles")
    storage = LocalFsStorage(f"{workspace}/storage")

    settings = DummySettings()

    # Check if ComfyUI is up
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"http://{settings.comfyui_host}:{settings.comfyui_port}/system_stats", timeout=2.0)
            if resp.status_code != 200:
                print("ComfyUI not available, skipping actual generation.")
                return
    except Exception:
        print("ComfyUI not available, skipping actual generation.")
        return

    provider = ComfyUIKeyframeProvider(settings=settings)

    keyframe_service = KeyframeGenerationService(
        generator=provider,
        storage=storage,
        character_bibles=bibles,
        storyboards=storyboards,
        candidate_evaluation=eval_service
    )

    contract = ShotContract(
        id="akira-test-01",
        camera_constraints=CameraConstraints(angle="wide", lens="35mm", movement="static"),
        action_constraints=ActionConstraints(primary_action="walking in neo-tokyo"),
        visual_constraints=VisualConstraints(lighting="neon", environment_style="anime", weather="rain")
    )

    print("Generating 3 candidates...")
    await keyframe_service.generate_candidates(shot_contract=contract, count=3)

    candidates = await eval_service.get_candidates_for_shot(contract.id)
    print(f"Generated {len(candidates)} candidates.")

    for i, c in enumerate(candidates):
        print(f"Candidate {i}: ID={c.id}, Status={c.status.value}, StorageKey={c.storage_key}")

    if len(candidates) > 0:
        print(f"Approving candidate 1: {candidates[1].id}")
        await eval_service.approve_candidate(candidates[1].id)

        print("Committing to storyboard...")
        storyboard = await keyframe_service.commit_approved_candidate(contract.id)
        print(f"Storyboard created successfully with frame pointing to: {storyboard.frames[0].storage_key}")

    print("A7 Akira Smoke Test Complete.")

if __name__ == "__main__":
    asyncio.run(main())
