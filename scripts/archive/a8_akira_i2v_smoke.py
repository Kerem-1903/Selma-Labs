from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import aiohttp

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.provider_registry import get_image_to_video_generation_provider
from config.settings import get_settings
from core.application.services.approved_keyframe_motion_service import (
    ApprovedKeyframeMotionService,
)
from core.application.services.candidate.candidate_evaluation_service import (
    CandidateEvaluationService,
)
from infrastructure.repositories.candidate.sqlite_keyframe_candidate_repository import (
    SqliteKeyframeCandidateRepository,
)
from infrastructure.repositories.local_json_shot_motion_clip_repository import (
    LocalJsonShotMotionClipRepository,
)
from infrastructure.repositories.local_json_shot_storyboard_repository import (
    LocalJsonShotStoryboardRepository,
)
from infrastructure.storage.local_fs_storage import LocalFsStorage


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Animate one A7-approved Akira storyboard frame through ComfyUI."
    )
    parser.add_argument("--storyboard-id", required=True)
    parser.add_argument("--storyboard-dir", default="output/a7_akira_smoke/storyboards")
    parser.add_argument("--candidate-db", default="output/a7_akira_smoke/candidates.db")
    parser.add_argument("--clip-dir", default="output/a8_akira_smoke/clips")
    parser.add_argument("--duration", type=float, default=4.0)
    parser.add_argument("--fps", type=float, default=24.0)
    parser.add_argument("--width", type=int, default=1024)
    parser.add_argument("--height", type=int, default=576)
    parser.add_argument("--seed", type=int, default=1903)
    parser.add_argument(
        "--motion-prompt",
        default="Akira breathes naturally while rain and hair move subtly",
    )
    parser.add_argument("--camera-motion", default="slow cinematic push-in")
    return parser.parse_args()


async def run(args: argparse.Namespace) -> None:
    settings = get_settings()
    if not Path(settings.comfyui_i2v_workflow_path).is_file():
        raise FileNotFoundError(
            f"ComfyUI I2V workflow is missing: {settings.comfyui_i2v_workflow_path}"
        )
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(settings.comfyui_api_url, timeout=3) as response:
                if response.status != 200:
                    raise RuntimeError(f"ComfyUI returned HTTP {response.status}.")
        except Exception as error:
            raise RuntimeError(
                f"ComfyUI is not reachable at {settings.comfyui_api_url}."
            ) from error

    storage = LocalFsStorage(settings.storage_root_dir)
    storyboard_repository = LocalJsonShotStoryboardRepository(args.storyboard_dir)
    storyboard = await storyboard_repository.load(args.storyboard_id)
    candidates = CandidateEvaluationService(
        SqliteKeyframeCandidateRepository(args.candidate_db)
    )
    clips = LocalJsonShotMotionClipRepository(args.clip_dir)
    provider_settings = settings.model_copy(
        update={"image_to_video_provider": "comfyui"}
    )
    provider = get_image_to_video_generation_provider(
        provider_settings, storage=storage
    )
    service = ApprovedKeyframeMotionService(
        generator=provider,
        storage=storage,
        candidates=candidates,
        clips=clips,
    )
    clip = await service.generate(
        storyboard=storyboard,
        target_duration_seconds=args.duration,
        motion_prompt=args.motion_prompt,
        camera_motion=args.camera_motion,
        width=args.width,
        height=args.height,
        fps=args.fps,
        seed=args.seed,
    )
    print(f"A8 motion clip generated: {clip.storage_key}")
    print(f"Metadata: {Path(args.clip_dir) / f'{clip.id}.json'}")


if __name__ == "__main__":
    try:
        asyncio.run(run(_arguments()))
    except Exception as error:
        print(f"A8 smoke test failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
