from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config.provider_registry import get_keyframe_generation_provider
from config.settings import Settings, get_settings
from core.application.services.animatic_planning_service import AnimaticPlanningService
from core.application.services.animation_orchestrator_service import (
    AnimationOrchestratorService,
)
from core.application.services.animation_ready_packaging_service import (
    AnimationReadyPackagingService,
)
from core.application.services.candidate.candidate_evaluation_service import (
    CandidateEvaluationService,
)
from core.application.services.character_golden_set_service import (
    CharacterGoldenSetService,
)
from core.application.services.hierarchical_shot_planning_service import (
    HierarchicalShotPlanningService,
)
from core.application.services.script_breakdown_service import ScriptBreakdownService
from core.application.services.story_engine_service import StoryEngineService
from core.domain.entities.character_bible import CharacterBible
from core.domain.ports.canon_repository_port import CanonRepositoryPort
from core.domain.ports.storage_port import StoragePort
from core.domain.value_objects.render_config import RenderConfig
from infrastructure.compositor.layered_compositor import LayeredCompositor
from infrastructure.providers.keyframe.golden_set_keyframe_adapter import (
    GoldenSetKeyframeAdapter,
)
from infrastructure.providers.lipsync.liveportrait_adapter import LivePortraitAdapter
from infrastructure.providers.motion.comfyui_motion_adapter import ComfyUIMotionAdapter
from infrastructure.providers.motion.comfyui_ws_client import ComfyUIWsClient
from infrastructure.providers.script.ollama_story_development_provider import (
    OllamaStoryDevelopmentProvider,
)
from infrastructure.providers.vision.local_golden_review_evaluator import (
    LocalGoldenReviewEvaluator,
)
from infrastructure.repositories.candidate.sqlite_keyframe_candidate_repository import (
    SqliteKeyframeCandidateRepository,
)
from infrastructure.repositories.local_json_canon_repository import (
    LocalJsonCanonRepository,
)
from infrastructure.repositories.local_json_story_approval_repository import (
    LocalJsonStoryApprovalRepository,
)
from infrastructure.storage.local_fs_storage import LocalFsStorage


@dataclass(frozen=True)
class AnimationContainer:
    character_bible: CharacterBible
    storage: StoragePort
    script_breakdown_service: ScriptBreakdownService
    animation_orchestrator_service: AnimationOrchestratorService
    story_engine_service: StoryEngineService
    character_golden_set_service: CharacterGoldenSetService
    hierarchical_shot_planning_service: HierarchicalShotPlanningService
    animatic_planning_service: AnimaticPlanningService
    animation_ready_packaging_service: AnimationReadyPackagingService
    canon_repository: CanonRepositoryPort

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
    preproduction_storage = LocalFsStorage(resolved.preproduction_asset_root)
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
    canon_repository = LocalJsonCanonRepository(
        resolved.preproduction_canon_dir,
        resolved.preproduction_character_dir,
    )
    story_writer = OllamaStoryDevelopmentProvider(
        api_url=resolved.ollama_api_url,
        model=resolved.story_development_model,
        reviewer_name="story-architect",
    )
    reviewers = tuple(
        OllamaStoryDevelopmentProvider(
            api_url=resolved.ollama_api_url,
            model=resolved.story_development_model,
            reviewer_name=role,
        )
        for role in ("continuity-reviewer", "character-voice-reviewer", "final-editor")
    )
    story_engine = StoryEngineService(
        story_generator=story_writer,
        dialogue_generator=story_writer,
        reviewers=reviewers,
        canon_repository=canon_repository,
        approval_repository=LocalJsonStoryApprovalRepository(
            resolved.preproduction_approval_dir
        ),
    )
    golden_set = CharacterGoldenSetService(
        GoldenSetKeyframeAdapter(
            get_keyframe_generation_provider(
                resolved, storage=preproduction_storage
            ),
            preproduction_storage,
            output_prefix=resolved.golden_set_output_prefix,
        ),
        LocalGoldenReviewEvaluator(resolved.golden_review_manifest),
    )
    hierarchical = HierarchicalShotPlanningService(breakdown)
    return AnimationContainer(
        character_bible=character_bible,
        storage=asset_storage,
        script_breakdown_service=breakdown,
        animation_orchestrator_service=orchestrator,
        story_engine_service=story_engine,
        character_golden_set_service=golden_set,
        hierarchical_shot_planning_service=hierarchical,
        animatic_planning_service=AnimaticPlanningService(asset_storage),
        animation_ready_packaging_service=AnimationReadyPackagingService(asset_storage),
        canon_repository=canon_repository,
    )
