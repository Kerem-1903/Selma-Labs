from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config.settings import Settings, get_settings
from config.provider_registry import get_keyframe_generation_provider
from core.application.services.animation_orchestrator_service import (
    AnimationOrchestratorService,
)
from core.application.services.candidate.candidate_evaluation_service import (
    CandidateEvaluationService,
)
from core.application.services.keyframe_generation_service import (
    KeyframeGenerationService,
)
from core.application.services.script_breakdown_service import ScriptBreakdownService
from core.domain.entities.character_bible import CharacterBible
from core.domain.ports.storage_port import StoragePort
from core.domain.value_objects.render_config import RenderConfig
from infrastructure.compositor.layered_compositor import LayeredCompositor
from infrastructure.providers.lipsync.liveportrait_adapter import LivePortraitAdapter
from infrastructure.providers.motion.comfyui_motion_adapter import ComfyUIMotionAdapter
from infrastructure.providers.motion.comfyui_ws_client import ComfyUIWsClient
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


@dataclass(frozen=True)
class AnimationContainer:
    character_bible: CharacterBible
    storage: StoragePort
    script_breakdown_service: ScriptBreakdownService
    animation_orchestrator_service: AnimationOrchestratorService
    keyframe_generation_service: KeyframeGenerationService

    def __getitem__(self, name: str) -> Any:
        """Keep dictionary-style access for early CLI consumers."""
        try:
            return getattr(self, name)
        except AttributeError as error:
            raise KeyError(name) from error


def create_container(
    *,
    settings: Settings | None = None,
    storage: StoragePort | None = None,
    comfyui_client: ComfyUIWsClient | None = None,
) -> AnimationContainer:
    resolved = settings or get_settings()
    asset_storage = storage or LocalFsStorage(resolved.storage_root_dir)
    keyframe_storage = LocalFsStorage(resolved.keyframe_storage_root_dir)
    character_bible = CharacterBible.akira()
    render_config = RenderConfig(
        width=resolved.two_pass_motion_width,
        height=resolved.two_pass_motion_height,
        fps=resolved.two_pass_motion_fps,
        seed=resolved.two_pass_motion_seed,
        sampler_name=resolved.two_pass_motion_sampler,
        pass1_denoise=resolved.two_pass_motion_pass1_denoise,
        pass2_denoise=resolved.two_pass_motion_pass2_denoise,
        sampling_steps=resolved.two_pass_motion_sampling_steps,
        guidance_scale=resolved.two_pass_motion_guidance_scale,
    )
    candidate_db_path = Path(resolved.keyframe_candidate_db_path)
    if str(candidate_db_path) != ":memory:":
        candidate_db_path.parent.mkdir(parents=True, exist_ok=True)
    candidate_evaluation = CandidateEvaluationService(
        SqliteKeyframeCandidateRepository(str(candidate_db_path))
    )
    motion = ComfyUIMotionAdapter(
        resolved.comfyui_api_url,
        workflow_path=resolved.two_pass_motion_workflow_path,
        storage=asset_storage,
        client=comfyui_client,
        render_config=render_config,
        candidate_evaluation_service=candidate_evaluation,
        cache_prefix=resolved.two_pass_motion_cache_prefix,
        timeout_seconds=resolved.two_pass_motion_timeout_seconds,
    )
    lipsync = LivePortraitAdapter(storage=asset_storage)
    compositor = LayeredCompositor(
        storage=asset_storage,
        ffmpeg_binary=resolved.ffmpeg_binary_path,
        timeout_seconds=resolved.animation_compositor_timeout_seconds,
        width=resolved.render_output_width,
        height=resolved.render_output_height,
        fps=resolved.render_fps,
    )
    breakdown = ScriptBreakdownService(character_bible)
    orchestrator = AnimationOrchestratorService(motion, lipsync, compositor)
    keyframe_service = KeyframeGenerationService(
        generator=get_keyframe_generation_provider(
            resolved, storage=keyframe_storage
        ),
        storage=keyframe_storage,
        character_bibles=LocalJsonCharacterBibleRepository(
            resolved.character_bible_repository_dir
        ),
        storyboards=LocalJsonShotStoryboardRepository(
            resolved.storyboard_repository_dir
        ),
        candidate_evaluation=candidate_evaluation,
        human_review_required=False,
    )
    return AnimationContainer(
        character_bible=character_bible,
        storage=asset_storage,
        script_breakdown_service=breakdown,
        animation_orchestrator_service=orchestrator,
        keyframe_generation_service=keyframe_service,
    )
