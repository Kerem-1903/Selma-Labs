from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config.provider_registry import (
    get_keyframe_generation_provider,
    get_vision_provider,
)
from config.settings import Settings, get_settings
from core.application.services.animatic_planning_service import AnimaticPlanningService
from core.application.services.animation_orchestrator_service import (
    AnimationOrchestratorService,
)
from core.application.services.animation_ready_packaging_service import (
    AnimationReadyPackagingService,
)
from core.application.services.background_factory_service import (
    BackgroundFactoryService,
)
from core.application.services.candidate.candidate_evaluation_service import (
    CandidateEvaluationService,
)
from core.application.services.character_canonical_approval_service import (
    CharacterCanonicalApprovalService,
)
from core.application.services.character_design_service import CharacterDesignService
from core.application.services.character_identity_prompt_service import (
    CharacterIdentityPromptService,
)
from core.application.services.character_golden_set_service import (
    CharacterGoldenSetService,
)
from core.application.services.character_onboarding_service import (
    CharacterOnboardingService,
)
from core.application.services.character_pose_pack_service import (
    CharacterPosePackService,
)
from core.application.services.character_view_pack_approval_service import (
    CharacterViewPackApprovalService,
)
from core.application.services.character_view_pack_asset_service import (
    CharacterViewPackAssetService,
)
from core.application.services.character_turnaround_drift_service import (
    CharacterTurnaroundDriftService,
    load_drift_thresholds,
)
from core.domain.value_objects.generation_capability import GenerationCapability
from core.application.services.character_view_pack_generation_service import (
    CharacterViewPackGenerationService,
)
from core.application.services.character_view_quality_gate import (
    CharacterViewQualityGate,
)
from core.application.services.episode_asset_generation_service import (
    EpisodeAssetGenerationService,
)
from core.application.services.episode_director_service import EpisodeDirectorService
from core.application.services.hierarchical_shot_planning_service import (
    HierarchicalShotPlanningService,
)
from core.application.services.keyframe_generation_service import (
    KeyframeGenerationService,
)
from core.application.services.keyframe_pair_quality_gate import (
    KeyframePairQualityGate,
)
from core.application.services.model_lock_service import load_model_lock
from core.application.services.production_manifest_service import (
    ProductionManifestService,
)
from core.application.services.script_breakdown_service import ScriptBreakdownService
from core.application.services.series_style_lock_service import SeriesStyleLockService
from core.application.services.story_engine_service import StoryEngineService
from core.application.services.streak_pre_gate import StreakPreGate
from core.application.services.structured_mark_validation_service import (
    StructuredMarkValidationService,
)
from core.application.services.view_framing_gate import ViewFramingGate
from core.domain.entities.character_bible import CharacterBible
from core.domain.ports.canon_repository_port import CanonRepositoryPort
from core.domain.ports.keyframe_generation_port import KeyframeGenerationPort
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
from infrastructure.providers.vision.guarded_golden_set_evaluator import (
    GuardedGoldenSetEvaluator,
)
from infrastructure.providers.vision.insightface_head_region_provider import (
    InsightFaceHeadRegionProvider,
)
from infrastructure.providers.vision.local_golden_review_evaluator import (
    LocalGoldenReviewEvaluator,
)
from infrastructure.providers.vision.ultralytics_character_view_detector import (
    UltralyticsCharacterViewDetector,
)
from infrastructure.providers.vision.vision_preproduction_image_evaluator import (
    VisionPreproductionImageEvaluator,
)
from infrastructure.repositories.candidate.sqlite_keyframe_candidate_repository import (
    SqliteKeyframeCandidateRepository,
)
from infrastructure.repositories.local_json_canon_repository import (
    LocalJsonCanonRepository,
)
from infrastructure.repositories.local_json_character_bible_repository import (
    LocalJsonCharacterBibleRepository,
)
from infrastructure.repositories.local_json_shot_storyboard_repository import (
    LocalJsonShotStoryboardRepository,
)
from infrastructure.repositories.local_json_story_approval_repository import (
    LocalJsonStoryApprovalRepository,
)
from infrastructure.storage.local_fs_storage import LocalFsStorage


@dataclass(frozen=True)
class AnimationContainer:
    character_bible: CharacterBible | None
    storage: StoragePort
    keyframe_storage: StoragePort
    script_breakdown_service: ScriptBreakdownService
    animation_orchestrator_service: AnimationOrchestratorService
    story_engine_service: StoryEngineService
    character_golden_set_service: CharacterGoldenSetService
    character_design_service: CharacterDesignService
    character_canonical_approval_service: CharacterCanonicalApprovalService
    character_view_pack_generation_service: CharacterViewPackGenerationService
    character_view_pack_asset_service: CharacterViewPackAssetService
    character_view_pack_approval_service: CharacterViewPackApprovalService
    character_onboarding_service: CharacterOnboardingService
    character_pose_pack_service: CharacterPosePackService
    style_lock_service: SeriesStyleLockService
    production_workflow_path: str
    background_factory_service: BackgroundFactoryService
    episode_asset_generation_service: EpisodeAssetGenerationService
    hierarchical_shot_planning_service: HierarchicalShotPlanningService
    animatic_planning_service: AnimaticPlanningService
    animation_ready_packaging_service: AnimationReadyPackagingService
    canon_repository: CanonRepositoryPort
    episode_director_service: EpisodeDirectorService
    keyframe_generation_service: KeyframeGenerationService
    #: The engine that runs the series' locked production dialect. Exposed so
    #: the style-lock smoke can render through the same engine the lock pins.
    keyframe_generation_provider: KeyframeGenerationPort

    def __getitem__(self, name: str) -> Any:
        """Keep dictionary-style access for early CLI consumers."""
        try:
            return getattr(self, name)
        except AttributeError as error:
            raise KeyError(name) from error


def _drift_band(settings: Settings) -> dict[str, Any]:
    """Resolve the calibrated drift band, failing closed when it is configured.

    A configured band that is missing or corrupt stops container creation
    instead of silently measuring against the looser built-in defaults; that
    fallback is how a calibrated gate turns back into an uncalibrated one.
    """
    configured = str(getattr(settings, "character_drift_thresholds_path", "") or "")
    if not configured.strip():
        return {}
    try:
        band, source = load_drift_thresholds(configured)
    except (OSError, TypeError, ValueError) as error:
        raise ValueError(
            f"Character drift thresholds are configured but unusable: {error}"
        ) from error
    return {"thresholds": band, "threshold_source": source}


def create_container(
    *,
    settings: Settings | None = None,
    storage: StoragePort | None = None,
    comfyui_client: ComfyUIWsClient | None = None,
    human_review_required: bool = True,
    character_bible: CharacterBible | None = None,
) -> AnimationContainer:
    resolved = settings or get_settings()
    asset_storage = storage or LocalFsStorage(resolved.storage_root_dir)
    preproduction_storage = LocalFsStorage(resolved.preproduction_asset_root)
    keyframe_storage = LocalFsStorage(resolved.keyframe_storage_root_dir)
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
    # The orchestrator is created after the keyframe service below so pair-backed
    # shots can be hash-verified at the final animation boundary.
    canon_repository = LocalJsonCanonRepository(
        resolved.preproduction_canon_dir,
        resolved.preproduction_character_dir,
    )
    story_writer = OllamaStoryDevelopmentProvider(
        api_url=resolved.ollama_api_url,
        model=resolved.story_development_model,
        reviewer_name="story-architect",
        timeout_seconds=resolved.story_development_timeout_seconds,
    )
    reviewers = tuple(
        OllamaStoryDevelopmentProvider(
            api_url=resolved.ollama_api_url,
            model=resolved.story_development_model,
            reviewer_name=role,
            timeout_seconds=resolved.story_development_timeout_seconds,
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
    golden_evaluator = LocalGoldenReviewEvaluator(resolved.golden_review_manifest)
    if resolved.golden_marker_gate_enabled:
        configured_providers = tuple(
            provider.strip()
            for provider in resolved.insightface_providers.split(",")
            if provider.strip()
        )
        golden_evaluator = GuardedGoldenSetEvaluator(
            human_evaluator=golden_evaluator,
            storage=preproduction_storage,
            head_region_provider=InsightFaceHeadRegionProvider(
                model_name=resolved.insightface_model_name,
                model_root=resolved.insightface_model_root,
                det_size=(
                    resolved.insightface_detection_size,
                    resolved.insightface_detection_size,
                ),
                ctx_id=resolved.insightface_ctx_id,
                providers=configured_providers or None,
                hair_pad_top=resolved.insightface_hair_pad_top,
                hair_pad_side=resolved.insightface_hair_pad_side,
            ),
            mark_validator=StructuredMarkValidationService(),
        )
    golden_set = CharacterGoldenSetService(
        GoldenSetKeyframeAdapter(
            get_keyframe_generation_provider(
                resolved,
                capability=GenerationCapability.GOLDEN_SET,
                storage=preproduction_storage,
            ),
            preproduction_storage,
            output_prefix=resolved.golden_set_output_prefix,
            character_lora_active=bool(resolved.comfyui_character_lora_name),
        ),
        golden_evaluator,
    )
    hierarchical = HierarchicalShotPlanningService(breakdown)
    # One engine cannot serve every workload: text-only design candidates,
    # source-led turnaround edits, pose-conditioned packs, storyboard keyframes
    # and golden-set evaluation are distinct capabilities. Resolving per
    # capability is what lets the turnaround run on FLUX.2 while storyboard
    # keyframes stay on the pose-conditioned SDXL dialect.
    def _capability_generator(capability: GenerationCapability):
        return get_keyframe_generation_provider(
            resolved, capability=capability, storage=keyframe_storage
        )

    design_generator = _capability_generator(GenerationCapability.CHARACTER_DESIGN)
    onboarding_generator = _capability_generator(
        GenerationCapability.CHARACTER_ONBOARDING
    )
    turnaround_generator = _capability_generator(
        GenerationCapability.CHARACTER_TURNAROUND
    )
    pose_pack_generator = _capability_generator(
        GenerationCapability.CHARACTER_POSE_PACK
    )
    keyframe_generator = _capability_generator(
        GenerationCapability.STORYBOARD_KEYFRAME
    )
    identity_prompt_service = CharacterIdentityPromptService()
    production_manifest = ProductionManifestService(
        resolved.keyframe_storage_root_dir
    )
    canonical_approval_service = CharacterCanonicalApprovalService(
        keyframe_storage,
        production_manifest=production_manifest,
    )
    edit_dialect = turnaround_generator.name == "comfyui:flux2-edit"
    character_view_quality_gate = None
    real_generators = (
        design_generator,
        onboarding_generator,
        turnaround_generator,
        pose_pack_generator,
        keyframe_generator,
    )
    if any(not item.name.startswith("fake:") for item in real_generators):
        # The detector roles live in whichever lock backs the turnaround engine.
        model_lock = load_model_lock(
            resolved.comfyui_flux2_model_lock_path
            if edit_dialect
            else resolved.comfyui_model_lock_path
        )
        model_root = Path(model_lock.comfyui_root).expanduser()
        character_view_quality_gate = CharacterViewQualityGate(
            UltralyticsCharacterViewDetector(
                face_model=str(model_root / model_lock.entry("face_detector").relative_path),
                pose_model=str(model_root / model_lock.entry("pose_detector").relative_path),
                confidence=resolved.character_qc_confidence,
            )
        )
    preproduction_evaluator = VisionPreproductionImageEvaluator(
        get_vision_provider(resolved)
    )
    character_design_service = CharacterDesignService(
        design_generator,
        keyframe_storage,
        quality_gate=character_view_quality_gate,
        max_view_attempts=resolved.character_view_max_attempts,
        production_manifest=production_manifest,
        prompt_service=identity_prompt_service,
    )
    character_view_pack_approval_service = CharacterViewPackApprovalService(
        keyframe_storage,
        acceptance_dir=resolved.character_acceptance_dir
        if hasattr(resolved, "character_acceptance_dir")
        else None,
    )
    character_view_pack_asset_service = CharacterViewPackAssetService(
        keyframe_storage,
        production_manifest=production_manifest,
    )
    character_view_pack_service = CharacterViewPackGenerationService(
        turnaround_generator,
        keyframe_storage,
        quality_gate=character_view_quality_gate,
        max_view_attempts=resolved.character_view_max_attempts,
        production_manifest=production_manifest,
        prompt_service=identity_prompt_service,
        approval_service=character_view_pack_approval_service,
        asset_service=character_view_pack_asset_service,
        edit_dialect=edit_dialect,
        # Advisory drift evidence is written by both real dialects: the two
        # measurable defects (prop scale/recolour, mark lost or mirrored) are a
        # property of any render, not of FLUX.2 in particular. Offline fake runs
        # skip it -- synthetic double images carry no studio framing to measure.
        drift_service=(
            None
            if turnaround_generator.name.startswith("fake:")
            else CharacterTurnaroundDriftService(
                accent_colour=resolved.character_drift_accent_colour,
                mark_side=resolved.character_drift_mark_side,
                **_drift_band(resolved),
            )
        ),
        view_candidate_count=resolved.character_view_candidate_count,
    )
    style_lock_service = SeriesStyleLockService(
        Path(__file__).resolve().parents[1]
    )

    async def require_view_pack(character_id: str, character_version: int) -> object:
        return await character_view_pack_service.load_approved_view_pack(
            character_id=character_id,
            character_version=character_version,
        )

    character_pose_pack_service = CharacterPosePackService(
        pose_pack_generator,
        keyframe_storage,
        quality_gate=character_view_quality_gate,
        max_attempts=resolved.character_pose_pack_max_attempts,
        pose_width=resolved.character_pose_pack_width,
        pose_height=resolved.character_pose_pack_height,
        require_real_provenance=not pose_pack_generator.name.startswith("fake:"),
        style_lock_resolver=style_lock_service,
        active_series_path=resolved.active_series_path,
        production_workflow_path=resolved.comfyui_keyframe_workflow_path,
        default_mode="PRODUCTION",
        prompt_service=identity_prompt_service,
        view_pack_approval_guard=require_view_pack,
    )

    keyframe_service = KeyframeGenerationService(
        generator=keyframe_generator,
        storage=keyframe_storage,
        character_bibles=LocalJsonCharacterBibleRepository(
            resolved.character_bible_repository_dir
        ),
        storyboards=LocalJsonShotStoryboardRepository(
            resolved.storyboard_repository_dir
        ),
        candidate_evaluation=candidate_evaluation,
        human_review_required=human_review_required,
        character_lora_active=bool(resolved.comfyui_character_lora_name),
        view_pack_approval_guard=require_view_pack,
        pair_quality_gate=(
            KeyframePairQualityGate(character_view_quality_gate)
            if character_view_quality_gate is not None
            else None
        ),
        pair_max_attempts=resolved.keyframe_pair_max_attempts,
        pose_dimensions=(resolved.keyframe_pose_width, resolved.keyframe_pose_height),
    )

    async def require_pair_approval(shot_plan):
        return await keyframe_service.require_approved_pair(shot_plan)

    async def require_pose_pack_approval(shot_plan):
        manifest_key = shot_plan.pose_pack_manifest_key
        approval_key = shot_plan.pose_pack_approval_key
        if not manifest_key or not approval_key:
            raise ValueError("Pose-pack keys are required for pose-pack-backed shots.")
        return await character_pose_pack_service.require_approved_pack(
            manifest_storage_key=manifest_key,
            approval_storage_key=approval_key,
        )

    orchestrator = AnimationOrchestratorService(
        motion,
        lipsync,
        compositor,
        pair_approval_guard=require_pair_approval,
        pose_pack_approval_guard=require_pose_pack_approval,
    )
    background_factory_service = BackgroundFactoryService(
        keyframe_generator, keyframe_storage, preproduction_evaluator
    )
    episode_asset_generation_service = EpisodeAssetGenerationService(
        character_pose_pack_service,
        background_factory_service,
        keyframe_storage,
        style_lock_resolver=style_lock_service,
    )
    return AnimationContainer(
        character_bible=character_bible,
        storage=asset_storage,
        keyframe_storage=keyframe_storage,
        script_breakdown_service=breakdown,
        animation_orchestrator_service=orchestrator,
        story_engine_service=story_engine,
        character_golden_set_service=golden_set,
        character_design_service=character_design_service,
        character_canonical_approval_service=canonical_approval_service,
        character_view_pack_generation_service=character_view_pack_service,
        character_view_pack_asset_service=character_view_pack_asset_service,
        character_view_pack_approval_service=character_view_pack_approval_service,
        character_onboarding_service=CharacterOnboardingService(
            onboarding_generator,
            keyframe_storage,
            preproduction_evaluator,
            streak_pre_gate=(
                StreakPreGate() if resolved.streak_pre_gate_enabled else None
            ),
            framing_gate=(
                ViewFramingGate()
                if resolved.character_framing_gate_enabled
                else None
            ),
            style_refine=resolved.character_style_refine_enabled,
        ),
        character_pose_pack_service=character_pose_pack_service,
        style_lock_service=style_lock_service,
        production_workflow_path=resolved.comfyui_keyframe_workflow_path,
        background_factory_service=background_factory_service,
        episode_asset_generation_service=episode_asset_generation_service,
        hierarchical_shot_planning_service=hierarchical,
        animatic_planning_service=AnimaticPlanningService(asset_storage),
        animation_ready_packaging_service=AnimationReadyPackagingService(asset_storage),
        canon_repository=canon_repository,
        episode_director_service=EpisodeDirectorService(),
        keyframe_generation_service=keyframe_service,
        keyframe_generation_provider=keyframe_generator,
    )
