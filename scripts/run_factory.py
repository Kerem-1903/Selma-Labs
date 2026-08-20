"""Single composition root for topic-first and audio-first Shorts production."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from contextlib import suppress
from pathlib import Path
from typing import Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"
RUN_INPUT_SCHEMA_VERSION = 1


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the focused CLI for creating or resuming one local factory run."""
    parser = argparse.ArgumentParser(
        description="Render a durable YouTube Short from one topic or licensed audio file.",
    )
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "--audio-path",
        help="Path to the licensed .mp3 or .wav source audio file.",
    )
    source_group.add_argument(
        "--topic",
        help="Generate a complete narrated Short from this topic.",
    )
    source_group.add_argument(
        "--autonomous",
        action="store_true",
        help="Continuously claim licensed audio from the local inbox.",
    )
    parser.add_argument(
        "--inbox-directory",
        default="input_audio",
        help="Directory watched by --autonomous (default: input_audio).",
    )
    parser.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=15.0,
        help="Seconds to wait while an autonomous inbox is empty (default: 15).",
    )
    parser.add_argument(
        "--max-inbox-attempts",
        type=int,
        default=3,
        help="Attempts before an inbox item moves to failed/ (default: 3).",
    )
    parser.add_argument(
        "--inbox-lease-seconds",
        type=int,
        default=3_600,
        help="Lease duration for an active autonomous job (default: 3600).",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="With --autonomous, process one claimed item then exit.",
    )
    parser.add_argument(
        "--run-id",
        help="Existing pipeline UUID to resume; omit to create a new run.",
    )
    parser.add_argument(
        "--additional-retries",
        type=int,
        default=0,
        help="Add recovery attempts to a failed --run-id (default: 0).",
    )
    parser.add_argument(
        "--reprocess-from",
        choices=(
            "RETENTION_PLAN_V1",
            "VISUAL_LOCALIZATION_V2",
            "VISUAL_EDIT_PLAN_V1",
            "MUSIC_SELECTION",
            "SOUND_DESIGN_V1",
            "VISION_SEARCH",
            "RENDER",
            "AUDIO_QUALITY_V1",
            "VISUAL_QUALITY_V1",
            "UPLOAD_PACKAGE",
        ),
        help="Reopen --run-id and invalidate this stage plus downstream outputs.",
    )
    parser.add_argument(
        "--accept-configuration-change",
        action="store_true",
        help=(
            "With --run-id and --reprocess-from, bind the reopened run to the "
            "current provider/render configuration."
        ),
    )
    parser.add_argument(
        "--target-duration-ms",
        type=int,
        default=20_000,
        help="Target hook duration in milliseconds (default: 20000).",
    )
    parser.add_argument(
        "--duration-seconds",
        type=int,
        default=24,
        help="Target narration duration for --topic (default: 24 seconds).",
    )
    parser.add_argument(
        "--language",
        default="en",
        help="Narration/alignment language code for --topic (default: en).",
    )
    parser.add_argument(
        "--voice-id",
        help="Override the configured ElevenLabs voice id for --topic.",
    )
    parser.add_argument(
        "--music-theme",
        help="Override automatic licensed background-music theme selection.",
    )
    parser.add_argument(
        "--music-track",
        help="Select a licensed manifest track by title, filename, or stem.",
    )
    parser.add_argument(
        "--no-background-music",
        action="store_true",
        help="Render topic narration without a background music bed.",
    )
    parser.add_argument(
        "--visual-manifest",
        help=(
            "Path to an operator-approved local visual manifest. This bypasses "
            "remote search and vision scoring without lowering their thresholds."
        ),
    )
    parser.add_argument(
        "--run-directory",
        default=".selma_runs",
        help="Directory for durable run JSON files (default: .selma_runs).",
    )
    parser.add_argument(
        "--output-directory",
        help="Directory for downloaded clips, ASS subtitles, and final MP4.",
    )
    return parser


def build_orchestrator(
    repository: "RunRepositoryPort",
    output_directory: Path,
    target_duration_ms: int,
    *,
    enable_topic_pipeline: bool = False,
    voice_id: str | None = None,
    content_language: str | None = None,
    visual_manifest_path: str | Path | None = None,
) -> "PipelineOrchestrator":
    """Instantiate adapters and services without placing business logic in CLI code."""
    from config.provider_registry import (
        get_fact_check_provider,
        get_fact_source_provider,
        get_background_music_provider,
        get_pipeline_video_source_provider,
        get_script_provider,
        get_script_rewriter_provider,
        get_translation_provider,
        get_vision_asset_scoring_service,
        get_voice_provider,
        get_video_generation_port,
        get_youtube_upload_port,
    )
    from core.application.services.vision_safety_gate import VisionSafetyGate
    from config.settings import get_settings
    from core.application.orchestration.pipeline_orchestrator import PipelineOrchestrator
    from core.application.orchestration.run_executor import RunExecutor
    from core.application.services.alignment_quality_service import AlignmentQualityService
    from core.application.services.audio_quality_gate_service import AudioQualityGateService
    from core.application.services.asset_diversity_service import AssetDiversityService
    from core.application.services.caption_ux_service import CaptionUxService
    from core.application.services.creative_quality_gate_service import (
        CreativeQualityGateService,
    )
    from core.application.services.brand_narration_service import BrandNarrationService
    from core.application.services.cue_partitioning_service import CuePartitioningService
    from core.application.services.editorial_rhythm_service import EditorialRhythmService
    from core.application.services.music_intelligence_service import MusicIntelligenceService
    from core.application.services.music_director_service import MusicDirectorService
    from core.application.services.narrative_quality_service import NarrativeQualityService
    from core.application.services.narration_text_preparation_service import NarrationTextPreparationService
    from core.application.services.premium_subtitle_formatter import PremiumSubtitleFormatter
    from core.application.services.post_render_quality_service import PostRenderQualityService
    from core.application.services.remotion_timeline_service import RemotionTimelineService
    from core.application.services.retention_planning_service import RetentionPlanningService
    from core.application.services.scene_planning_service import ScenePlanningService
    from core.application.services.sound_design_planning_service import SoundDesignPlanningService
    from core.application.services.script_fact_check_service import ScriptFactCheckService
    from core.application.services.script_service import ScriptService
    from core.application.services.video_search_service import VideoSearchService
    from core.application.services.voice_service import VoiceService
    from core.application.services.voice_direction_service import VoiceDirectionService
    from core.application.services.visual_intent_localization_service import (
        VisualIntentLocalizationService,
    )
    from core.application.services.visual_edit_planning_service import (
        VisualEditPlanningService,
    )
    from core.application.services.visual_quality_gate_service import (
        VisualQualityGateService,
    )
    from core.application.services.youtube_upload_package_service import (
        YoutubeUploadPackageService,
    )
    from core.application.services.youtube_performance_learning_service import (
        YoutubePerformanceLearningService,
    )
    from core.domain.value_objects.scene import Scene
    from core.domain.value_objects.caption_ux import CaptionSafeZoneProfile
    from infrastructure.providers.audio.librosa_highlight_selector import (
        LibrosaHighlightSelector,
    )
    from infrastructure.providers.audio.local_audio_source_provider import (
        LocalAudioSourceProvider,
    )
    from infrastructure.providers.audio.whisperx_word_alignment_provider import (
        WhisperXWordAlignmentProvider,
    )
    from infrastructure.providers.frame_extraction.ffmpeg_frame_extractor import (
        FfmpegFrameExtractor,
    )
    from infrastructure.providers.render.ffmpeg_render_provider import FfmpegRenderProvider
    from infrastructure.providers.render.remotion_render_provider import RemotionRenderProvider
    from infrastructure.providers.render.ffprobe_media_inspection_provider import (
        FfprobeMediaInspectionProvider,
    )
    from infrastructure.providers.render.ffmpeg_media_quality_analysis_provider import (
        FfmpegMediaQualityAnalysisProvider,
    )
    from infrastructure.storage.local_fs_storage import LocalFsStorage
    from infrastructure.repositories.sqlite_youtube_performance_repository import (
        SQLiteYoutubePerformanceRepository,
    )
    from infrastructure.providers.video.local_visual_manifest_provider import (
        LocalVisualManifestProvider,
    )

    class MusicOnlyScenePlanningProvider:
        """Compatibility adapter unused by music-first visual planning."""

        provider_identity = "local:music-only"

        async def plan_scenes(self, narration_text: str) -> list[Scene]:
            del narration_text
            raise RuntimeError(
                "The local factory uses music-first visual planning only."
            )

    settings = get_settings()
    if visual_manifest_path is None:
        if not settings.vision_enabled:
            raise RuntimeError(
                "VISION_ENABLED must be true for the strict visual-quality gate. "
                "Enable it only after confirming the selected vision provider and budget."
            )
        _require_factory_configuration(settings.pexels_api_key, "PEXELS_API_KEY")
        if settings.vision_provider == "openai":
            _require_factory_configuration(settings.openai_api_key, "OPENAI_API_KEY")
        elif settings.vision_provider == "anthropic":
            _require_factory_configuration(settings.anthropic_api_key, "ANTHROPIC_API_KEY")
        elif settings.vision_provider == "nvidia":
            _require_factory_configuration(settings.nvidia_api_key, "NVIDIA_API_KEY")
        else:
            raise RuntimeError(
                f"Unsupported VISION_PROVIDER={settings.vision_provider!r}."
            )

    audio_source = LocalAudioSourceProvider(
        settings.ffprobe_binary_path,
        license_manifest_path=settings.audio_license_manifest_path,
        require_license_manifest=settings.require_audio_license_manifest,
    )
    highlight_selector = LibrosaHighlightSelector()
    word_alignment = WhisperXWordAlignmentProvider()
    ffmpeg_render_provider = FfmpegRenderProvider(
        ffmpeg_binary=settings.ffmpeg_binary_path,
        ffprobe_binary=settings.ffprobe_binary_path,
        output_width=settings.render_output_width,
        output_height=settings.render_output_height,
        fps=settings.render_fps,
        background_music_volume=settings.background_music_volume,
    )
    render_provider = (
        RemotionRenderProvider(
            project_directory=settings.remotion_project_dir,
            remotion_cli_path=settings.remotion_cli_path,
            ffmpeg_binary=settings.ffmpeg_binary_path,
            ffmpeg_fallback=ffmpeg_render_provider,
            subprocess_timeout_seconds=settings.remotion_subprocess_timeout_seconds,
            background_music_volume=settings.background_music_volume,
        )
        if settings.render_provider == "remotion"
        else ffmpeg_render_provider
    )
    video_storage = LocalFsStorage(str(output_directory))
    video_search = (
        VideoSearchService(
            get_pipeline_video_source_provider(settings),
            video_storage,
        )
        if visual_manifest_path is None
        else None
    )

    music_intelligence = MusicIntelligenceService(audio_source, highlight_selector)
    alignment_quality = AlignmentQualityService()
    caption_profile = CaptionSafeZoneProfile(
        margin_left=settings.caption_safe_margin_left,
        margin_right=settings.caption_safe_margin_right,
        caption_baseline_y=settings.caption_baseline_y,
        font_size=settings.caption_font_size,
        outline_width=settings.caption_outline_width,
        active_scale_percent=settings.caption_active_scale_percent,
        minimum_scaled_emphasis_ms=(
            settings.caption_minimum_scaled_emphasis_ms
        ),
    )
    caption_ux = CaptionUxService(caption_profile)
    cue_partitioning = CuePartitioningService(
        maximum_words_per_cue=settings.caption_maximum_words_per_cue,
        maximum_cue_duration_ms=settings.caption_maximum_cue_duration_ms,
        line_width_validator=caption_ux.words_fit
    )
    scene_planning = ScenePlanningService(
        MusicOnlyScenePlanningProvider(),
        maximum_visual_intent_duration_ms=(
            settings.editorial_maximum_visual_beat_ms
        ),
    )
    vision_scoring = (
        get_vision_asset_scoring_service(settings)
        if visual_manifest_path is None
        else None
    )
    video_generation = get_video_generation_port(settings)
    youtube_upload = get_youtube_upload_port(settings)
    vision_safety_gate = VisionSafetyGate(vision_scoring_service=vision_scoring, relevance_threshold=settings.vision_relevance_threshold) if (vision_scoring and settings.vision_safety_gate_enabled) else None
    script_service = None
    script_fact_check_service = None
    script_rewriter = None
    voice_service = None
    music_director_service = None
    if enable_topic_pipeline:
        if settings.script_provider == "claude":
            _require_factory_configuration(settings.anthropic_api_key, "ANTHROPIC_API_KEY")
        # NVIDIA remains mandatory in topic mode because claim extraction,
        # independent audit, and grounded rewrite use its configured models
        # even when Claude generates the initial draft.
        _require_factory_configuration(settings.nvidia_api_key, "NVIDIA_API_KEY")
        _require_factory_configuration(settings.elevenlabs_api_key, "ELEVENLABS_API_KEY")
        script_service = ScriptService(get_script_provider(settings))
        script_fact_check_service = ScriptFactCheckService(
            source_provider=get_fact_source_provider(
                settings,
                language=content_language,
            ),
            fact_check_provider=get_fact_check_provider(settings),
            max_sources=settings.fact_check_source_limit,
        )
        script_rewriter = get_script_rewriter_provider(settings)
        voice_service = VoiceService(
            provider=get_voice_provider(settings),
            storage=video_storage,
            default_voice_name=voice_id or settings.elevenlabs_voice_id,
            direction_service=VoiceDirectionService(),
            text_preparation_service=NarrationTextPreparationService(
                settings.pronunciation_lexicon_path
            ),
        )
        if settings.background_music_enabled:
            music_director_service = MusicDirectorService(
                get_background_music_provider(settings)
            )

    return PipelineOrchestrator(
        executor=RunExecutor(repository),
        music_intelligence_service=music_intelligence,
        word_alignment=word_alignment,
        cue_partitioning_service=cue_partitioning,
        scene_planning_service=scene_planning,
        alignment_quality_service=alignment_quality,
        caption_ux_service=caption_ux,
        video_search_service=video_search,
        vision_asset_scoring_service=vision_scoring,
        video_generation_port=video_generation,
        vision_safety_gate=vision_safety_gate,
        asset_diversity_service=(AssetDiversityService(
            perceptual_distance_threshold=(
                settings.asset_perceptual_distance_threshold
            ),
            maximum_asset_uses=settings.asset_maximum_source_uses,
            maximum_pose_uses=settings.asset_maximum_pose_uses,
            maximum_camera_angle_uses=(
                settings.asset_maximum_camera_angle_uses
            ),
            maximum_background_uses=settings.asset_maximum_background_uses,
            frame_extractor=FfmpegFrameExtractor(
                ffmpeg_binary=settings.ffmpeg_binary_path,
                max_width=480,
            )
        ) if visual_manifest_path is None else None),
        editorial_rhythm_service=EditorialRhythmService(
            alignment_tolerance_ms=settings.editorial_alignment_tolerance_ms,
            maximum_low_motion_ms=settings.editorial_maximum_low_motion_ms,
        ),
        render_port=render_provider,
        premium_subtitle_formatter=PremiumSubtitleFormatter(caption_profile),
        media_inspection_port=FfprobeMediaInspectionProvider(
            ffmpeg_binary=settings.ffmpeg_binary_path,
            ffprobe_binary=settings.ffprobe_binary_path,
        ),
        media_quality_analysis_port=FfmpegMediaQualityAnalysisProvider(
            ffmpeg_binary=settings.ffmpeg_binary_path,
        ),
        post_render_quality_service=PostRenderQualityService(),
        remotion_timeline_service=RemotionTimelineService(
            fps=settings.render_fps,
            brand_signature="STRANGE THINGS",
        ),
        script_service=script_service,
        script_fact_check_service=script_fact_check_service,
        script_rewriter=script_rewriter,
        narrative_quality_service=(
            NarrativeQualityService() if enable_topic_pipeline else None
        ),
        retention_planning_service=(
            RetentionPlanningService() if enable_topic_pipeline else None
        ),
        performance_learning_service=(
            YoutubePerformanceLearningService(
                SQLiteYoutubePerformanceRepository(
                    settings.youtube_performance_store
                )
            )
            if enable_topic_pipeline
            else None
        ),
        brand_narration_service=(
            BrandNarrationService(settings.brand_signature_text)
            if enable_topic_pipeline and settings.brand_signature_enabled
            else None
        ),
        voice_service=voice_service,
        music_director_service=music_director_service,
        sound_design_planning_service=SoundDesignPlanningService(),
        audio_quality_gate_service=AudioQualityGateService(),
        youtube_upload_package_service=(
            YoutubeUploadPackageService(
                FfprobeMediaInspectionProvider(
                    ffmpeg_binary=settings.ffmpeg_binary_path,
                    ffprobe_binary=settings.ffprobe_binary_path,
                )
            )
            if enable_topic_pipeline
            else None
        ),
        creative_quality_gate_service=(
            CreativeQualityGateService() if enable_topic_pipeline else None
        ),
        visual_edit_planning_service=VisualEditPlanningService(),
        visual_quality_gate_service=VisualQualityGateService(),
        visual_intent_localization_service=(
            VisualIntentLocalizationService(get_translation_provider(settings))
            if enable_topic_pipeline
            else None
        ),
        visual_manifest=(
            LocalVisualManifestProvider(visual_manifest_path)
            if visual_manifest_path is not None
            else None
        ),
        fact_check_max_rewrites=settings.fact_check_rewrite_attempts,
        procedural_audio_accents_enabled=settings.procedural_audio_accents_enabled,
        output_directory=output_directory,
        target_duration_ms=target_duration_ms,
    )


async def run(arguments: argparse.Namespace) -> str:
    """Create or resume a durable run, then return the final MP4 path."""
    from config.settings import get_settings
    from core.domain.entities.pipeline_run import PipelineRun
    from infrastructure.repositories.local_json_run_repository import LocalJsonRunRepository

    if arguments.target_duration_ms <= 0:
        raise ValueError("--target-duration-ms must be greater than zero.")
    if not 15 <= arguments.duration_seconds <= 90:
        raise ValueError("--duration-seconds must be between 15 and 90.")
    if arguments.poll_interval_seconds <= 0:
        raise ValueError("--poll-interval-seconds must be greater than zero.")
    if arguments.inbox_lease_seconds <= 0:
        raise ValueError("--inbox-lease-seconds must be greater than zero.")
    if arguments.additional_retries < 0:
        raise ValueError("--additional-retries must not be negative.")
    if arguments.additional_retries and not arguments.run_id:
        raise ValueError("--additional-retries requires --run-id.")
    if arguments.reprocess_from and not arguments.run_id:
        raise ValueError("--reprocess-from requires --run-id.")
    if arguments.accept_configuration_change and not (
        arguments.run_id and arguments.reprocess_from
    ):
        raise ValueError(
            "--accept-configuration-change requires --run-id and --reprocess-from."
        )
    if not arguments.topic and (
        arguments.music_theme
        or arguments.music_track
        or arguments.no_background_music
    ):
        raise ValueError("Background-music controls are available only with --topic.")

    settings = get_settings()
    from core.application.services.system_health_service import SystemHealthService

    output_directory = Path(arguments.output_directory or settings.storage_root_dir)
    health_profile = "factory" if arguments.topic else "audio"
    health = SystemHealthService(
        settings,
        project_root=PROJECT_ROOT,
    ).evaluate(
        profile=health_profile,
        run_directory=arguments.run_directory,
        output_directory=output_directory,
        local_visual_manifest=arguments.visual_manifest,
    )
    if not health.ready:
        failures = "; ".join(
            f"{check.name}: {check.details}" for check in health.failures
        )
        raise RuntimeError(f"Production preflight failed: {failures}")
    repository = LocalJsonRunRepository(arguments.run_directory)
    if arguments.autonomous:
        return await _run_autonomous(
            arguments,
            repository,
            output_directory,
            settings,
        )

    if arguments.run_id:
        run_id = arguments.run_id
        pipeline_run = await repository.get_by_id(run_id)
        current_fingerprint = _build_run_input_fingerprint(arguments, settings)
        if arguments.reprocess_from:
            final_stages = [
                "RETENTION_PLAN_V1",
                "VOICE_GENERATION",
                "AUDIO_INTELLIGENCE",
                "WORD_ALIGNMENT",
                "CUE_PARTITIONING_V2",
                "CAPTION_UX_V1",
                "SCENE_PLANNING",
                "VISUAL_LOCALIZATION_V2",
                "VISUAL_EDIT_PLAN_V1",
                "MUSIC_SELECTION",
                "SOUND_DESIGN_V1",
                "VISION_SEARCH",
                "EDITORIAL_RHYTHM_V1",
                "RENDER",
                "AUDIO_QUALITY_V1",
                "VISUAL_QUALITY_V1",
                "CAPTION_PREVIEWS_V1",
                "CREATIVE_QUALITY_V1",
                "UPLOAD_PACKAGE",
            ]
            start_index = final_stages.index(arguments.reprocess_from)
            pipeline_run.reopen_with_invalidated_stages(final_stages[start_index:])
            if arguments.accept_configuration_change:
                pipeline_run.rebind_input_fingerprint_after_reprocess(
                    current_fingerprint
                )
            else:
                pipeline_run.bind_input_fingerprint(current_fingerprint)
        else:
            pipeline_run.bind_input_fingerprint(current_fingerprint)
        if arguments.additional_retries:
            pipeline_run.extend_retry_budget(arguments.additional_retries)
        # Persist a newly bound fingerprint as well as any recovery mutation
        # before RunExecutor reloads the aggregate from the repository.
        await repository.save(pipeline_run)
    else:
        pipeline_run = PipelineRun.create()
        run_id = pipeline_run.run_id
        pipeline_run.bind_input_fingerprint(
            _build_run_input_fingerprint(arguments, settings)
        )
        await repository.save(pipeline_run)

    orchestrator = build_orchestrator(
        repository,
        output_directory,
        arguments.target_duration_ms,
        enable_topic_pipeline=bool(arguments.topic),
        voice_id=arguments.voice_id,
        content_language=arguments.language if arguments.topic else None,
        visual_manifest_path=arguments.visual_manifest,
    )
    if arguments.topic:
        result = await orchestrator.run_topic_factory(
            run_id,
            arguments.topic,
            target_duration_seconds=arguments.duration_seconds,
            language=arguments.language,
            use_background_music=not arguments.no_background_music,
            music_theme=arguments.music_theme,
            music_track=arguments.music_track,
        )
    else:
        result = await orchestrator.run_factory(run_id, arguments.audio_path)
    return str(result["output_path"])


async def _run_autonomous(
    arguments: argparse.Namespace,
    repository: "RunRepositoryPort",
    output_directory: Path,
    settings: object,
) -> str:
    """Continuously process durable jobs claimed from the licensed audio inbox."""
    from core.domain.entities.pipeline_run import PipelineRun
    from core.domain.exceptions import PipelineRunNotFoundError
    from infrastructure.providers.audio.local_audio_inbox import LocalAudioInbox

    inbox = LocalAudioInbox(
        arguments.inbox_directory,
        max_attempts=arguments.max_inbox_attempts,
        lease_seconds=arguments.inbox_lease_seconds,
    )
    orchestrator = build_orchestrator(
        repository,
        output_directory,
        arguments.target_duration_ms,
    )
    while True:
        job = await inbox.claim_next()
        if job is None:
            if arguments.once:
                raise RuntimeError("No eligible MP3 or WAV file exists in the audio inbox.")
            await asyncio.sleep(arguments.poll_interval_seconds)
            continue
        try:
            try:
                pipeline_run = await repository.get_by_id(job.run_id)
            except PipelineRunNotFoundError:
                pipeline_run = PipelineRun(run_id=job.run_id)
            pipeline_run.bind_input_fingerprint(
                _build_audio_job_fingerprint(
                    job.source_uri,
                    target_duration_ms=arguments.target_duration_ms,
                    settings=settings,
                )
            )
            await repository.save(pipeline_run)
            heartbeat = asyncio.create_task(
                _renew_inbox_lease(inbox, job, arguments.inbox_lease_seconds)
            )
            try:
                result = await orchestrator.run_factory(job.run_id, job.source_uri)
            finally:
                heartbeat.cancel()
                with suppress(asyncio.CancelledError):
                    await heartbeat
            await inbox.mark_completed(job)
            output_path = str(result["output_path"])
            if arguments.once:
                return output_path
            print(f"{GREEN}Short rendered successfully: {Path(output_path).resolve()}{RESET}")
        except Exception as error:
            await inbox.mark_failed(job, str(error))
            if arguments.once:
                raise
            print(f"{RED}Factory job failed: {error}{RESET}", file=sys.stderr)
            await asyncio.sleep(arguments.poll_interval_seconds)


async def _renew_inbox_lease(
    inbox: "AudioInboxPort",
    job: "AudioInboxJob",
    lease_seconds: int,
) -> None:
    """Keep a durable inbox claim alive while its pipeline run is executing."""
    interval_seconds = max(1.0, lease_seconds / 3)
    while True:
        await asyncio.sleep(interval_seconds)
        await inbox.renew_lease(job)


def main(argv: Sequence[str] | None = None) -> int:
    """Parse CLI arguments, execute the async factory, and color the result."""
    arguments = build_arg_parser().parse_args(argv)
    try:
        output_path = asyncio.run(run(arguments))
    except Exception as error:  # noqa: BLE001 - top-level CLI boundary
        print(f"{RED}Factory failed: {error}{RESET}", file=sys.stderr)
        return 1
    print(f"{GREEN}Short rendered successfully: {Path(output_path).resolve()}{RESET}")
    return 0


def _require_factory_configuration(value: str, variable_name: str) -> None:
    """Fail before expensive local analysis if required external access is absent."""
    if not value.strip():
        raise RuntimeError(f"{variable_name} must be configured in .env.")


def _build_run_input_fingerprint(arguments: argparse.Namespace, settings: object) -> str:
    """Hash non-secret inputs whose outputs may be reused by checkpoints."""
    if arguments.topic:
        source: dict[str, object] = {
            "mode": "topic",
            "topic": " ".join(arguments.topic.split()),
            "duration_seconds": arguments.duration_seconds,
            "language": arguments.language.strip().lower(),
            "voice_id": arguments.voice_id or getattr(settings, "elevenlabs_voice_id"),
            "background_music": not arguments.no_background_music,
            "music_theme": arguments.music_theme,
            "music_track": arguments.music_track,
            "visual_manifest": (
                _visual_manifest_identity(arguments.visual_manifest)
                if arguments.visual_manifest
                else None
            ),
        }
    else:
        source = {
            "mode": "audio",
            **_audio_source_identity(arguments.audio_path),
            "target_duration_ms": arguments.target_duration_ms,
            "visual_manifest": (
                _visual_manifest_identity(arguments.visual_manifest)
                if arguments.visual_manifest
                else None
            ),
        }
    return _fingerprint_payload(
        {
            "schema_version": RUN_INPUT_SCHEMA_VERSION,
            "source": source,
            "provider_profile": _provider_profile(settings),
        }
    )


def _provider_profile(settings: object) -> dict[str, object]:
    return {
        name: getattr(settings, name)
        for name in (
            "script_provider",
            "script_model",
            "nvidia_text_model",
            "fact_check_provider",
            "nvidia_fact_check_model",
            "nvidia_fact_check_audit_model",
            "fact_check_fallback_provider",
            "openai_fact_check_model",
            "voice_provider",
            "elevenlabs_model_id",
            "vision_provider",
            "vision_model",
            "openai_vision_model",
            "nvidia_vision_model",
            "vision_fallback_provider",
            "render_provider",
            "render_output_width",
            "render_output_height",
            "render_fps",
            "background_music_volume",
            "procedural_audio_accents_enabled",
            "vision_frames_per_asset",
            "vision_top_candidates",
            "vision_weight",
            "brand_signature_enabled",
            "brand_signature_text",
        )
    }


def _build_audio_job_fingerprint(
    source_uri: str,
    *,
    target_duration_ms: int,
    settings: object,
) -> str:
    return _fingerprint_payload(
        {
            "schema_version": RUN_INPUT_SCHEMA_VERSION,
            "source": {
                "mode": "audio",
                **_audio_source_identity(source_uri),
                "target_duration_ms": target_duration_ms,
            },
            "provider_profile": _provider_profile(settings),
        }
    )


def _audio_source_identity(source: str) -> dict[str, object]:
    path = Path(source).resolve()
    try:
        stat = path.stat()
    except OSError:
        return {"audio_path": str(path), "size_bytes": None, "modified_ns": None}
    return {
        "audio_path": str(path),
        "size_bytes": stat.st_size,
        "modified_ns": stat.st_mtime_ns,
    }


def _visual_manifest_identity(source: str) -> dict[str, object]:
    """Fingerprint a manifest and every local clip it references."""
    path = Path(source).resolve()
    identity: dict[str, object] = {"manifest_path": str(path), "assets": []}
    try:
        stat = path.stat()
        identity.update({"size_bytes": stat.st_size, "modified_ns": stat.st_mtime_ns})
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        identity.update({"size_bytes": None, "modified_ns": None})
        return identity
    asset_identities: list[dict[str, object]] = []
    for entry in data.get("assets", []) if isinstance(data, dict) else []:
        if not isinstance(entry, dict):
            continue
        asset_path = (path.parent / str(entry.get("file") or "")).resolve()
        try:
            asset_path.relative_to(path.parent.resolve())
            asset_stat = asset_path.stat()
        except (OSError, ValueError):
            asset_identities.append(
                {"path": str(asset_path), "size_bytes": None, "modified_ns": None}
            )
        else:
            asset_identities.append(
                {
                    "path": str(asset_path),
                    "size_bytes": asset_stat.st_size,
                    "modified_ns": asset_stat.st_mtime_ns,
                }
            )
    identity["assets"] = asset_identities
    return identity


def _fingerprint_payload(payload: dict[str, object]) -> str:
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
