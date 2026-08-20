"""Music-first durable orchestration for the autonomous Shorts Factory."""
from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

from core.application.orchestration.run_executor import RunExecutor
from core.application.services.alignment_quality_service import AlignmentQualityService
from core.application.services.audio_quality_gate_service import AudioQualityGateService
from core.application.services.asset_diversity_service import AssetDiversityService
from core.application.services.caption_ux_service import CaptionUxService
from core.application.services.creative_quality_gate_service import CreativeQualityGateService
from core.application.services.brand_narration_service import BrandNarrationService
from core.application.services.cue_partitioning_service import CuePartitioningService
from core.application.services.editorial_rhythm_service import EditorialRhythmService
from core.application.services.music_intelligence_service import MusicIntelligenceService
from core.application.services.music_director_service import MusicDirectorService
from core.application.services.narrative_quality_service import NarrativeQualityService
from core.application.services.premium_subtitle_formatter import PremiumSubtitleFormatter
from core.application.services.post_render_quality_service import PostRenderQualityService
from core.application.services.remotion_timeline_service import RemotionTimelineService
from core.application.services.retention_planning_service import RetentionPlanningService
from core.application.services.scene_planning_service import ScenePlanningService
from core.application.services.sound_design_planning_service import SoundDesignPlanningService
from core.application.services.script_fact_check_service import ScriptFactCheckService
from core.application.services.script_service import ScriptService
from core.application.services.video_search_service import VideoSearchService
from core.application.services.vision_asset_scoring_service import VisionAssetScoringService
from core.application.services.visual_intent_localization_service import (
    VisualIntentLocalizationService,
)
from core.application.services.visual_edit_planning_service import VisualEditPlanningService
from core.application.services.visual_quality_gate_service import VisualQualityGateService
from core.application.services.voice_service import VoiceService
from core.application.services.youtube_upload_package_service import YoutubeUploadPackageService
from core.application.services.youtube_performance_learning_service import (
    YoutubePerformanceLearningService,
)
from core.domain.entities.audio_asset import AudioAsset
from core.domain.entities.media_asset import MediaAsset
from core.domain.entities.script import Script
from core.domain.entities.voice_track import VoiceTrack
from core.domain.exceptions import (
    AssetDiversityError,
    BackgroundMusicError,
    FactCheckError,
    LowVisionConfidenceError,
    VisualAssetNotFoundError,
)
from core.domain.ports.render_port import RenderPort
from core.domain.ports.media_inspection_port import MediaInspectionPort
from core.domain.ports.media_quality_analysis_port import MediaQualityAnalysisPort
from core.domain.ports.script_rewriter_port import ScriptRewriterPort
from core.domain.ports.word_alignment_port import WordAlignmentPort
from core.domain.ports.visual_manifest_port import VisualManifestPort
from core.domain.value_objects.asset_score import AssetScore
from core.domain.value_objects.audio_quality_report import AudioQualityReport
from core.domain.value_objects.background_track import BackgroundTrack
from core.domain.value_objects.asset_diversity import AssetUsage
from core.domain.value_objects.creative_quality_report import CreativeQualityReport
from core.domain.value_objects.media_inspection import MediaInspection
from core.domain.value_objects.media_quality_signals import MediaQualitySignals
from core.domain.value_objects.narrative_quality_report import NarrativeQualityReport
from core.domain.value_objects.narrative_contract import NarrativeBeat, NarrativeContract
from core.domain.value_objects.retention_plan import RetentionPlan
from core.domain.value_objects.selected_highlight import SelectedHighlight
from core.domain.value_objects.sound_design_plan import SoundDesignPlan
from core.domain.value_objects.scored_asset import ScoredAsset
from core.domain.value_objects.subtitle_cue import SubtitleCue
from core.domain.value_objects.speech_segment import SpeechSegment
from core.domain.value_objects.visual_intent import VisualIntent
from core.domain.value_objects.visual_edit_plan import VisualEditPlan
from core.domain.value_objects.visual_quality_report import VisualQualityReport
from core.domain.value_objects.word_timing import WordTiming
from core.domain.value_objects.voice_direction import VoiceDirection


class PipelineOrchestrator:
    """Coordinates recoverable music, caption, and visual-planning stages.

    All checkpoint artifacts are JSON-safe dictionaries. Domain objects are
    rehydrated only at stage boundaries, keeping the repository independent
    from audio, alignment, caption, and vision implementation details.
    """

    SCRIPT_GENERATION = "SCRIPT_GENERATION"
    FACT_CHECK = "FACT_CHECK"
    NARRATIVE_QUALITY = "NARRATIVE_QUALITY_V1"
    RETENTION_PLAN = "RETENTION_PLAN_V1"
    BRAND_NARRATION = "BRAND_NARRATION_V1"
    VOICE_GENERATION = "VOICE_GENERATION"
    AUDIO_INTELLIGENCE = "AUDIO_INTELLIGENCE"
    WORD_ALIGNMENT = "WORD_ALIGNMENT"
    CUE_PARTITIONING = "CUE_PARTITIONING_V2"
    CAPTION_UX = "CAPTION_UX_V1"
    SCENE_PLANNING = "SCENE_PLANNING"
    VISUAL_LOCALIZATION = "VISUAL_LOCALIZATION_V2"
    VISUAL_EDIT_PLAN = "VISUAL_EDIT_PLAN_V1"
    MUSIC_SELECTION = "MUSIC_SELECTION"
    SOUND_DESIGN = "SOUND_DESIGN_V1"
    VISION_SEARCH = "VISION_SEARCH"
    EDITORIAL_RHYTHM = "EDITORIAL_RHYTHM_V1"
    RENDER = "RENDER"
    AUDIO_QUALITY = "AUDIO_QUALITY_V1"
    VISUAL_QUALITY = "VISUAL_QUALITY_V1"
    CAPTION_PREVIEWS = "CAPTION_PREVIEWS_V1"
    CREATIVE_QUALITY = "CREATIVE_QUALITY_V1"
    UPLOAD_PACKAGE = "UPLOAD_PACKAGE"

    def __init__(
        self,
        executor: RunExecutor,
        music_intelligence_service: MusicIntelligenceService,
        word_alignment: WordAlignmentPort,
        cue_partitioning_service: CuePartitioningService,
        scene_planning_service: ScenePlanningService,
        *,
        alignment_quality_service: AlignmentQualityService | None = None,
        caption_ux_service: CaptionUxService | None = None,
        video_search_service: VideoSearchService | None = None,
        vision_asset_scoring_service: VisionAssetScoringService | None = None,
        video_generation_port: VideoGenerationPort | None = None,
        vision_safety_gate: VisionSafetyGate | None = None,
        asset_diversity_service: AssetDiversityService | None = None,
        editorial_rhythm_service: EditorialRhythmService | None = None,
        render_port: RenderPort | None = None,
        premium_subtitle_formatter: PremiumSubtitleFormatter | None = None,
        media_inspection_port: MediaInspectionPort | None = None,
        media_quality_analysis_port: MediaQualityAnalysisPort | None = None,
        post_render_quality_service: PostRenderQualityService | None = None,
        youtube_upload_port: YoutubeUploadPort | None = None,
        youtube_upload_privacy: str = "unlisted",
        remotion_timeline_service: RemotionTimelineService | None = None,
        script_service: ScriptService | None = None,
        script_fact_check_service: ScriptFactCheckService | None = None,
        script_rewriter: ScriptRewriterPort | None = None,
        narrative_quality_service: NarrativeQualityService | None = None,
        retention_planning_service: RetentionPlanningService | None = None,
        performance_learning_service: YoutubePerformanceLearningService | None = None,
        brand_narration_service: BrandNarrationService | None = None,
        voice_service: VoiceService | None = None,
        music_director_service: MusicDirectorService | None = None,
        sound_design_planning_service: SoundDesignPlanningService | None = None,
        audio_quality_gate_service: AudioQualityGateService | None = None,
        youtube_upload_package_service: YoutubeUploadPackageService | None = None,
        creative_quality_gate_service: CreativeQualityGateService | None = None,
        visual_intent_localization_service: VisualIntentLocalizationService | None = None,
        visual_edit_planning_service: VisualEditPlanningService | None = None,
        visual_quality_gate_service: VisualQualityGateService | None = None,
        visual_manifest: VisualManifestPort | None = None,
        fact_check_max_rewrites: int = 2,
        procedural_audio_accents_enabled: bool = True,
        output_directory: str | Path = "output",
        target_duration_ms: int = 20_000,
    ) -> None:
        if target_duration_ms <= 0:
            raise ValueError("target_duration_ms must be greater than zero.")
        self._executor = executor
        self._music_intelligence_service = music_intelligence_service
        self._word_alignment = word_alignment
        self._alignment_quality_service = alignment_quality_service
        self._caption_ux_service = caption_ux_service
        self._cue_partitioning_service = cue_partitioning_service
        self._scene_planning_service = scene_planning_service
        if (render_port is None) != (premium_subtitle_formatter is None):
            raise ValueError(
                "Render port and ASS formatter must be configured together."
            )
        if (
            render_port is not None
            and visual_manifest is None
            and (video_search_service is None or vision_asset_scoring_service is None)
        ):
            raise ValueError(
                "Final rendering requires either an approved visual manifest or "
                "both video search and vision scoring."
            )
        self._video_search_service = video_search_service
        self._vision_asset_scoring_service = vision_asset_scoring_service
        self._video_generation_port = video_generation_port
        self._vision_safety_gate = vision_safety_gate
        self._asset_diversity_service = asset_diversity_service
        self._editorial_rhythm_service = editorial_rhythm_service
        self._render_port = render_port
        self._premium_subtitle_formatter = premium_subtitle_formatter
        if (media_inspection_port is None) != (post_render_quality_service is None):
            raise ValueError("Media inspection and post-render quality must be configured together.")
        self._media_inspection_port = media_inspection_port
        if media_quality_analysis_port is not None and post_render_quality_service is None:
            raise ValueError(
                "Media quality analysis requires post-render quality validation."
            )
        self._media_quality_analysis_port = media_quality_analysis_port
        self._post_render_quality_service = post_render_quality_service
        self._youtube_upload_port = youtube_upload_port
        self._youtube_upload_privacy = youtube_upload_privacy
        self._remotion_timeline_service = remotion_timeline_service
        topic_dependencies = (
            script_service,
            script_fact_check_service,
            script_rewriter,
            voice_service,
        )
        if any(topic_dependencies) and not all(topic_dependencies):
            raise ValueError(
                "Script, fact-check, rewrite, and voice services must be configured "
                "together for topic runs."
            )
        if fact_check_max_rewrites < 0:
            raise ValueError("fact_check_max_rewrites must not be negative.")
        self._script_service = script_service
        self._script_fact_check_service = script_fact_check_service
        self._script_rewriter = script_rewriter
        self._narrative_quality_service = narrative_quality_service
        self._retention_planning_service = retention_planning_service
        self._performance_learning_service = performance_learning_service
        self._brand_narration_service = brand_narration_service
        self._voice_service = voice_service
        self._music_director_service = music_director_service
        self._sound_design_planning_service = sound_design_planning_service
        self._audio_quality_gate_service = audio_quality_gate_service
        self._youtube_upload_package_service = youtube_upload_package_service
        self._creative_quality_gate_service = creative_quality_gate_service
        self._visual_intent_localization_service = visual_intent_localization_service
        self._visual_edit_planning_service = visual_edit_planning_service
        self._visual_quality_gate_service = visual_quality_gate_service
        self._visual_manifest = visual_manifest
        self._fact_check_max_rewrites = fact_check_max_rewrites
        self._procedural_audio_accents_enabled = procedural_audio_accents_enabled
        self._output_directory = Path(output_directory)
        self._target_duration_ms = target_duration_ms

    async def run_factory(self, run_id: str, source_uri: str) -> dict[str, Any]:
        """Run the durable factory stages and return rehydrated artifacts.

        Calling this method again with the same ``run_id`` is safe: the
        executor reads each completed stage from the repository and invokes
        only the first stage that lacks a persisted artifact.
        """
        audio_artifact = await self._executor.execute_stage(
            run_id,
            self.AUDIO_INTELLIGENCE,
            lambda: self._run_audio_intelligence(source_uri),
        )
        return await self._continue_from_audio(
            run_id,
            audio_artifact,
            transcript=None,
            visual_anchor=None,
            narrative_beats=(),
        )

    async def run_topic_factory(
        self,
        run_id: str,
        topic: str,
        *,
        target_duration_seconds: int = 24,
        language: str = "en",
        use_background_music: bool = True,
        music_theme: str | None = None,
        music_track: str | None = None,
    ) -> dict[str, Any]:
        """Run topic → verified script → voice → alignment → render in one saga."""
        if any(
            dependency is None
            for dependency in (
                self._script_service,
                self._script_fact_check_service,
                self._script_rewriter,
                self._voice_service,
            )
        ):
            raise RuntimeError(
                "Topic mode requires script, fact-check, rewrite, and voice services."
            )
        script_artifact = await self._executor.execute_stage(
            run_id,
            self.SCRIPT_GENERATION,
            lambda: self._run_script_generation(
                topic,
                target_duration_seconds,
                language,
            ),
        )
        original_script = self._script_from_dict(script_artifact["script"])
        fact_check_artifact = await self._executor.execute_stage(
            run_id,
            self.FACT_CHECK,
            lambda: self._run_fact_check(original_script),
        )
        script = self._script_from_dict(fact_check_artifact["verified_script"])
        narrative_quality_artifact = None
        if self._narrative_quality_service is not None:
            narrative_quality_artifact = await self._executor.execute_stage(
                run_id,
                self.NARRATIVE_QUALITY,
                lambda: self._run_narrative_quality(script, language),
            )
            script = self._script_from_dict(narrative_quality_artifact["script"])
        brand_narration_artifact = None
        if self._brand_narration_service is not None:
            brand_narration_artifact = await self._executor.execute_stage(
                run_id,
                self.BRAND_NARRATION,
                lambda: self._run_brand_narration(script),
            )
            script = self._script_from_dict(brand_narration_artifact["script"])
        retention_plan_artifact = None
        if self._retention_planning_service is not None:
            retention_plan_artifact = await self._executor.execute_stage(
                run_id,
                self.RETENTION_PLAN,
                lambda: self._run_retention_plan(script, language),
            )
        voice_artifact = await self._executor.execute_stage(
            run_id,
            self.VOICE_GENERATION,
            lambda: self._run_voice_generation(script),
        )
        voice_track = self._voice_track_from_dict(voice_artifact["voice_track"])
        audio_artifact = await self._executor.execute_stage(
            run_id,
            self.AUDIO_INTELLIGENCE,
            lambda: self._run_narrated_audio(voice_track, language),
        )
        result = await self._continue_from_audio(
            run_id,
            audio_artifact,
            transcript=voice_track.spoken_text or script.full_text,
            visual_anchor=topic,
            narrative_beats=script.narrative_beats,
            music_context=(
                {
                    "topic": topic,
                    "script_text": script.full_text,
                    "theme_override": music_theme,
                    "track_override": music_track,
                }
                if use_background_music and self._music_director_service is not None
                else None
            ),
            package_context=(
                {
                    "topic": topic,
                    "script": self._script_to_dict(script),
                    "language": language,
                    "fact_check_passed": True,
                    "voice_direction": (
                        voice_track.direction.to_dict()
                        if voice_track.direction is not None
                        else None
                    ),
                    "narrative_quality_report": (
                        dict(narrative_quality_artifact["report"])
                        if narrative_quality_artifact is not None
                        else None
                    ),
                    "retention_plan": (
                        dict(retention_plan_artifact["plan"])
                        if retention_plan_artifact is not None
                        else None
                    ),
                }
                if self._youtube_upload_package_service is not None
                else None
            ),
        )
        result.update(
            {
                "original_script": original_script,
                "script": script,
                "fact_check_reports": list(fact_check_artifact["reports"]),
                "voice_track": voice_track,
                "narrative_quality_report": (
                    dict(narrative_quality_artifact["report"])
                    if narrative_quality_artifact is not None
                    else None
                ),
                "retention_plan": (
                    dict(retention_plan_artifact["plan"])
                    if retention_plan_artifact is not None
                    else None
                ),
                "brand_narration": (
                    dict(brand_narration_artifact)
                    if brand_narration_artifact is not None
                    else None
                ),
            }
        )
        return result

    async def _continue_from_audio(
        self,
        run_id: str,
        audio_artifact: dict[str, Any],
        *,
        transcript: str | None,
        visual_anchor: str | None,
        narrative_beats: tuple[NarrativeBeat, ...] = (),
        music_context: dict[str, Any] | None = None,
        package_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute the shared alignment-to-render half of every factory run."""
        audio_asset = AudioAsset.from_dict(audio_artifact["audio_asset"])
        highlight = self._highlight_from_dict(audio_artifact["selected_highlight"])

        alignment_artifact = await self._executor.execute_stage(
            run_id,
            self.WORD_ALIGNMENT,
            lambda: self._run_word_alignment(
                audio_asset,
                highlight,
                transcript=transcript,
            ),
        )
        word_timings = [
            self._word_timing_from_dict(item)
            for item in alignment_artifact["word_timings"]
        ]

        cue_artifact = await self._executor.execute_stage(
            run_id,
            self.CUE_PARTITIONING,
            lambda: self._run_cue_partitioning(word_timings),
        )
        cues = [self._cue_from_dict(item) for item in cue_artifact["subtitle_cues"]]
        caption_ux_artifact: dict[str, Any] | None = None
        if self._caption_ux_service is not None:
            caption_ux_artifact = await self._executor.execute_stage(
                run_id,
                self.CAPTION_UX,
                lambda: self._run_caption_ux(cues),
            )

        visual_artifact = await self._executor.execute_stage(
            run_id,
            self.SCENE_PLANNING,
            lambda: self._run_scene_planning(
                highlight,
                cues,
                narrative_beats=narrative_beats,
                visual_anchor=visual_anchor,
            ),
        )
        visual_intents = [
            self._visual_intent_from_dict(item)
            for item in visual_artifact["visual_intents"]
        ]
        if self._visual_intent_localization_service is not None:
            localization_artifact = await self._executor.execute_stage(
                run_id,
                self.VISUAL_LOCALIZATION,
                lambda: self._run_visual_localization(
                    visual_intents, visual_anchor=visual_anchor
                ),
            )
            visual_intents = [
                self._visual_intent_from_dict(item)
                for item in localization_artifact["visual_intents"]
            ]
        visual_edit_plan_artifact: dict[str, Any] | None = None
        if self._visual_edit_planning_service is not None:
            visual_edit_plan_artifact = await self._executor.execute_stage(
                run_id,
                self.VISUAL_EDIT_PLAN,
                lambda: self._run_visual_edit_plan(visual_intents),
            )
            visual_intents = [
                self._visual_intent_from_dict(item)
                for item in visual_edit_plan_artifact["visual_intents"]
            ]
        music_selection: dict[str, Any] | None = None
        background_music_path: str | None = None
        if music_context is not None:
            music_selection = await self._executor.execute_stage(
                run_id,
                self.MUSIC_SELECTION,
                lambda: self._run_music_selection(
                    music_context,
                    visual_intents,
                ),
            )
            background_music_path = music_selection.get("track_file_path")
        result: dict[str, Any] = {
            "audio_asset": audio_asset,
            "selected_highlight": highlight,
            "word_timings": word_timings,
            "subtitle_cues": cues,
            "visual_intents": visual_intents,
        }
        if music_selection is not None:
            result["music_selection"] = music_selection
        if visual_edit_plan_artifact is not None:
            result["visual_edit_plan"] = visual_edit_plan_artifact["plan"]
        sound_design_artifact: dict[str, Any] | None = None
        if self._sound_design_planning_service is not None:
            sound_design_artifact = await self._executor.execute_stage(
                run_id,
                self.SOUND_DESIGN,
                lambda: self._run_sound_design(
                    visual_intents,
                    has_music=bool(
                        music_selection
                        and music_selection.get("status") == "selected"
                    ),
                ),
            )
            result["sound_design"] = sound_design_artifact
        if caption_ux_artifact is not None:
            result["caption_ux"] = caption_ux_artifact
        if not self._is_finalization_configured:
            return result

        video_artifact = await self._executor.execute_stage(
            run_id,
            self.VISION_SEARCH,
            lambda: self._run_vision_search(visual_intents),
        )
        video_clips = [str(path) for path in video_artifact["video_clips"]]
        selected_assets = [
            MediaAsset(**item) for item in video_artifact.get("selected_assets", [])
        ]
        usages = [
            AssetUsage.from_dict(item)
            for item in video_artifact.get("asset_usages", [])
        ]
        if self._editorial_rhythm_service is not None:
            rhythm_artifact = await self._executor.execute_stage(
                run_id,
                self.EDITORIAL_RHYTHM,
                lambda: self._run_editorial_rhythm(
                    visual_intents,
                    cues,
                    usages,
                ),
            )
            result["editorial_rhythm"] = rhythm_artifact

        render_artifact = await self._executor.execute_stage(
            run_id,
            self.RENDER,
            lambda: self._run_render(
                run_id,
                audio_asset,
                highlight,
                cues,
                visual_intents,
                video_clips,
                background_music_path,
                transcript is not None and self._procedural_audio_accents_enabled,
                sound_design_artifact,
                visual_edit_plan_artifact,
            ),
        )
        result.update(
            {
                "video_clips": video_clips,
                "subtitle_ass_path": str(render_artifact["subtitle_ass_path"]),
                "output_path": str(render_artifact["output_path"]),
            }
        )
        audio_quality_artifact = None
        if self._audio_quality_gate_service is not None and sound_design_artifact is not None:
            audio_quality_artifact = await self._executor.execute_stage(
                run_id,
                self.AUDIO_QUALITY,
                lambda: self._run_audio_quality(
                    sound_design_artifact,
                    render_artifact,
                    music_selection,
                ),
            )
            result["audio_quality"] = audio_quality_artifact
        visual_quality_artifact = None
        if (
            self._visual_quality_gate_service is not None
            and visual_edit_plan_artifact is not None
        ):
            visual_quality_artifact = await self._executor.execute_stage(
                run_id,
                self.VISUAL_QUALITY,
                lambda: self._run_visual_quality(
                    visual_edit_plan_artifact,
                    visual_intents,
                    selected_assets,
                    usages,
                    render_artifact,
                ),
            )
            result["visual_quality"] = visual_quality_artifact
        if (
            self._caption_ux_service is not None
            and self._media_inspection_port is not None
        ):
            preview_artifact = await self._executor.execute_stage(
                run_id,
                self.CAPTION_PREVIEWS,
                lambda: self._run_caption_previews(
                    run_id,
                    str(render_artifact["output_path"]),
                    cues,
                ),
            )
            result["caption_previews"] = preview_artifact
        creative_quality_artifact = None
        if self._creative_quality_gate_service is not None and package_context is not None:
            creative_quality_artifact = await self._executor.execute_stage(
                run_id,
                self.CREATIVE_QUALITY,
                lambda: self._run_creative_quality(
                    package_context=package_context,
                    visual_intents=visual_intents,
                    cues=cues,
                    source_assets=selected_assets,
                    render_artifact=render_artifact,
                    music_selection=music_selection,
                ),
            )
            result["creative_quality"] = creative_quality_artifact
        if package_context is not None:
            package_artifact = await self._executor.execute_stage(
                run_id,
                self.UPLOAD_PACKAGE,
                lambda: self._run_upload_package(
                    run_id=run_id,
                    package_context=package_context,
                    video_path=str(render_artifact["output_path"]),
                    cues=cues,
                    source_assets=selected_assets,
                    music_selection=music_selection,
                    creative_quality_report=(
                        dict(creative_quality_artifact)
                        if creative_quality_artifact is not None
                        else None
                    ),
                    audio_quality_report=(
                        dict(audio_quality_artifact)
                        if audio_quality_artifact is not None
                        else None
                    ),
                    visual_quality_report=(
                        dict(visual_quality_artifact)
                        if visual_quality_artifact is not None
                        else None
                    ),
                ),
            )
            result["upload_package"] = package_artifact

        if self._youtube_upload_port is not None and "output_path" in result:
            upload_artifact = await self._executor.execute_stage(
                run_id,
                "YOUTUBE_UPLOAD",
                lambda: self._run_youtube_upload(result["output_path"], package_context.get("script"), self._youtube_upload_privacy)
            )
            result["youtube_upload"] = upload_artifact

        await self._executor.complete_run(run_id)
        return result

    @property
    def _is_finalization_configured(self) -> bool:
        return self._render_port is not None

    async def _run_audio_intelligence(self, source_uri: str) -> dict[str, Any]:
        audio_asset, highlight = (
            await self._music_intelligence_service.process_music_hook_with_asset(
                source_uri,
                self._target_duration_ms,
            )
        )
        return {
            "audio_asset": audio_asset.to_dict(),
            "selected_highlight": self._highlight_to_dict(highlight),
        }

    async def _run_script_generation(
        self,
        topic: str,
        target_duration_seconds: int,
        language: str,
    ) -> dict[str, Any]:
        assert self._script_service is not None
        script = await self._script_service.generate(
            topic,
            target_duration_seconds,
            language=language,
        )
        return {"script": self._script_to_dict(script)}

    async def _run_voice_generation(self, script: Script) -> dict[str, Any]:
        assert self._voice_service is not None
        voice_track = await self._voice_service.generate(script)
        return {"voice_track": self._voice_track_to_dict(voice_track)}

    async def _run_brand_narration(self, script: Script) -> dict[str, Any]:
        assert self._brand_narration_service is not None
        branded_script = self._brand_narration_service.apply(script)
        return {
            "script": self._script_to_dict(branded_script),
            "signature": self._brand_narration_service.signature,
            "position": "after_hook",
        }

    async def _run_narrative_quality(
        self,
        script: Script,
        language: str,
    ) -> dict[str, Any]:
        assert self._narrative_quality_service is not None
        enriched_script, report = self._narrative_quality_service.validate(
            script,
            language=language,
        )
        return {
            "script": self._script_to_dict(enriched_script),
            "report": report.to_dict(),
        }

    async def _run_retention_plan(
        self,
        script: Script,
        language: str,
    ) -> dict[str, Any]:
        assert self._retention_planning_service is not None
        guidance = None
        if self._performance_learning_service is not None:
            guidance = await self._performance_learning_service.build_guidance(
                "single_fact" if script.target_duration_seconds <= 60 else "long_form"
            )
        plan = self._retention_planning_service.build(
            script,
            language=language,
            performance_guidance=guidance,
        )
        return {"plan": plan.to_dict()}

    async def _run_fact_check(self, script: Script) -> dict[str, Any]:
        assert self._script_fact_check_service is not None
        assert self._script_rewriter is not None
        verified_script, reports = (
            await self._script_fact_check_service.verify_with_rewrites(
                script,
                self._script_rewriter,
                max_rewrites=self._fact_check_max_rewrites,
            )
        )
        final_report = reports[-1] if reports else None
        if final_report is None or not final_report.verified:
            failed_claims = [
                claim.claim
                for claim in (final_report.claims if final_report else [])
                if claim.verdict != "supported"
            ]
            details = "; ".join(failed_claims[:5]) or "no verified claims"
            raise FactCheckError(
                "Script remains unsupported after the allowed grounded rewrites: "
                f"{details}."
            )
        return {
            "original_script_id": script.id,
            "verified_script": self._script_to_dict(verified_script),
            "rewrite_count": max(0, len(reports) - 1),
            "reports": [report.to_dict() for report in reports],
        }

    async def _run_narrated_audio(
        self,
        voice_track: VoiceTrack,
        language: str,
    ) -> dict[str, Any]:
        duration_ms = round(voice_track.duration_seconds * 1_000)
        audio_asset = AudioAsset.create(
            source_provider=voice_track.provider,
            source_asset_id=voice_track.audio_id,
            local_path=voice_track.file_path,
            duration_ms=duration_ms,
            media_type="audio/mpeg",
            license="self-generated narration",
            usage_rights="publish",
            language=language.strip() or None,
            sample_rate_hz=voice_track.sample_rate,
            metadata={
                "script_id": voice_track.script_id,
                "word_timings": [
                    {
                        "text": segment.text,
                        "start_ms": round(segment.start * 1_000),
                        "end_ms": round(segment.end * 1_000),
                    }
                    for segment in voice_track.segments
                ],
            },
        )
        highlight = SelectedHighlight(
            audio_asset_id=audio_asset.id,
            start_ms=0,
            end_ms=duration_ms,
            score=0.55,
            selector_used="full-narration",
            hook_type="narration",
            rationale="The complete generated narration is the editorial timeline.",
        )
        return {
            "audio_asset": audio_asset.to_dict(),
            "selected_highlight": self._highlight_to_dict(highlight),
        }

    async def _run_word_alignment(
        self,
        audio_asset: AudioAsset,
        highlight: SelectedHighlight,
        *,
        transcript: str | None = None,
    ) -> dict[str, Any]:
        embedded_timings = audio_asset.metadata.get("word_timings") or []
        words = [
            WordTiming(
                text=str(item["text"]),
                start_ms=int(item["start_ms"]),
                end_ms=int(item["end_ms"]),
            )
            for item in embedded_timings
            if isinstance(item, dict)
            and str(item.get("text") or "").strip()
            and int(item.get("end_ms") or 0) > int(item.get("start_ms") or 0)
        ]
        if not words:
            words = await self._word_alignment.align(
                audio_asset,
                highlight,
                language=audio_asset.language,
                transcript=transcript,
            )
        if self._alignment_quality_service is not None:
            self._alignment_quality_service.validate(words, highlight)
        return {"word_timings": [self._word_timing_to_dict(word) for word in words]}

    async def _run_cue_partitioning(
        self,
        word_timings: list[WordTiming],
    ) -> dict[str, Any]:
        cues = self._cue_partitioning_service.partition(word_timings)
        return {"subtitle_cues": [self._cue_to_dict(cue) for cue in cues]}

    async def _run_scene_planning(
        self,
        highlight: SelectedHighlight,
        cues: list[SubtitleCue],
        *,
        narrative_beats: tuple[NarrativeBeat, ...] = (),
        visual_anchor: str | None = None,
    ) -> dict[str, Any]:
        if narrative_beats:
            intents = self._scene_planning_service.plan_visual_intents(
                highlight,
                cues,
                narrative_beats=narrative_beats,
                visual_anchor=visual_anchor,
            )
        else:
            # Compatibility for audio-first planning and older injected test
            # doubles. Topic runs with Sprint 18 metadata always use the
            # semantic branch above.
            intents = self._scene_planning_service.plan_visual_intents(
                highlight,
                cues,
            )
        return {
            "visual_intents": [self._visual_intent_to_dict(intent) for intent in intents]
        }

    async def _run_vision_search(
        self,
        visual_intents: list[VisualIntent],
    ) -> dict[str, Any]:
        """Search, evidence-rank, and persist one visual asset per intent."""
        if self._visual_manifest is not None:
            assets, usages = self._visual_manifest.select(visual_intents)
            return {
                "video_clips": [str(asset.local_path) for asset in assets],
                "selected_asset_ids": sorted(asset.id for asset in assets),
                "selected_assets": [asset.to_dict() for asset in assets],
                "asset_usages": [usage.to_dict() for usage in usages],
                "selection_mode": "operator_approved_manifest",
            }
        assert self._video_search_service is not None
        assert self._vision_asset_scoring_service is not None
        video_clips: list[str] = []
        selected_assets: list[dict[str, Any]] = []
        selected_asset_ids: set[str] = set()
        last_selected_asset_id: str | None = None
        asset_usages: list[AssetUsage] = []
        for intent in visual_intents:
            # Explanatory beats need footage that supports the stated action,
            # not merely generic footage of the topic. Context-only beats keep
            # the compact subject query to avoid over-constraining stock search.
            primary_query = (
                intent.search_query
                if intent.explanatory_required or intent.required_actions
                else intent.primary_keyword
            )
            candidates = await self._video_search_service.search(
                primary_query,
                max_results=10,
            )
            fresh_candidates = [
                candidate
                for candidate in candidates
                if candidate.id not in selected_asset_ids
            ]
            fallback_query = (
                intent.primary_keyword
                if primary_query != intent.primary_keyword
                else intent.search_query
            )
            if not fresh_candidates and fallback_query != primary_query:
                fallback_candidates = await self._video_search_service.search(
                    fallback_query,
                    max_results=10,
                )
                candidates_by_id = {
                    candidate.id: candidate
                    for candidate in [*candidates, *fallback_candidates]
                }
                candidates = list(candidates_by_id.values())
                fresh_candidates = [
                    candidate
                    for candidate in candidates
                    if candidate.id not in selected_asset_ids
                ]
            scoring_candidates = fresh_candidates or candidates
            scored_candidates = [
                ScoredAsset(asset=asset, score=AssetScore(final_score=0.50))
                for asset in scoring_candidates
            ]
            accepted_asset = None
            try:
                accepted_scores = await self._vision_asset_scoring_service.score_visual_intent(
                    intent,
                    scored_candidates,
                )

                if self._vision_safety_gate:
                    is_safe = await self._vision_safety_gate.evaluate(accepted_scores[0].asset, intent, intent.narration_text)
                    if not is_safe:
                        raise VisualAssetNotFoundError("Asset rejected by Vision Safety Gate")

                accepted_asset = accepted_scores[0]
            except (LowVisionConfidenceError, VisualAssetNotFoundError):
                # Try Text-to-Video generation if stock videos fail safety or aren't found
                if self._video_generation_port and getattr(intent, 'generation_prompt', None):
                    duration_sec = (intent.end_ms - intent.start_ms) / 1000.0
                    if duration_sec <= 0:
                        duration_sec = 5.0
                    try:
                        gen_asset = await self._video_generation_port.generate_video(intent.generation_prompt, duration_sec)
                        accepted_asset = ScoredAsset(asset=gen_asset, score=AssetScore(final_score=1.0))
                    except Exception as e:
                        pass # Fallback to stock reuse if T2V fails

                # If still not accepted, do the stock fallback
                if not accepted_asset:
                    reusable = [
                        asset for asset in candidates if asset.id != last_selected_asset_id
                    ]
                    if not reusable:
                        raise
                    try:
                        fallback_scores = await self._vision_asset_scoring_service.score_visual_intent(
                            intent,
                            [
                                ScoredAsset(asset=asset, score=AssetScore(final_score=0.50))
                                for asset in reusable
                            ],
                        )
                        if self._vision_safety_gate:
                            is_safe = await self._vision_safety_gate.evaluate(fallback_scores[0].asset, intent, intent.narration_text)
                            if not is_safe:
                                raise VisualAssetNotFoundError("Asset rejected by Vision Safety Gate")
                        accepted_asset = fallback_scores[0]
                    except (LowVisionConfidenceError, VisualAssetNotFoundError):
                        if last_selected_asset_id is None:
                            raise
                        final_scores = await self._vision_asset_scoring_service.score_visual_intent(
                            intent,
                            [
                                ScoredAsset(asset=asset, score=AssetScore(final_score=0.50))
                                for asset in candidates
                            ],
                        )
                        accepted_asset = final_scores[0]

            # The downstream code expects a list called `accepted`
            accepted = [accepted_asset]
            selected_usage: AssetUsage | None = None
            if self._asset_diversity_service is None:
                selected = await self._video_search_service.download(accepted[0].asset)
            else:
                remaining_candidates = list(accepted)
                while remaining_candidates:
                    selected_candidate, provisional_usage = (
                        self._asset_diversity_service.select(
                            intent,
                            remaining_candidates,
                            asset_usages,
                        )
                    )
                    selected = await self._video_search_service.download(
                        selected_candidate.asset
                    )
                    refined_usage = await self._asset_diversity_service.refine_downloaded_usage(
                        selected,
                        provisional_usage,
                    )
                    try:
                        self._asset_diversity_service.validate_usage(
                            refined_usage,
                            asset_usages,
                        )
                    except AssetDiversityError:
                        remaining_candidates = [
                            candidate
                            for candidate in remaining_candidates
                            if candidate.asset.id != selected_candidate.asset.id
                        ]
                        if not remaining_candidates:
                            raise
                        continue
                    selected_usage = refined_usage
                    selected = replace(
                        selected,
                        metadata={
                            **selected.metadata,
                            "perceptual_hashes": list(
                                refined_usage.perceptual_hashes
                            ),
                        },
                    )
                    break
            if not selected.local_path:
                raise RuntimeError(
                    f"Downloaded visual asset '{selected.id}' has no local path."
                )
            selected_asset_ids.add(selected.id)
            last_selected_asset_id = selected.id
            video_clips.append(selected.local_path)
            selected_assets.append(selected.to_dict())
            if selected_usage is not None:
                asset_usages.append(selected_usage)
        return {
            "video_clips": video_clips,
            "selected_asset_ids": sorted(selected_asset_ids),
            "selected_assets": selected_assets,
            "asset_usages": [usage.to_dict() for usage in asset_usages],
        }

    def _run_editorial_rhythm(
        self,
        visual_intents: list[VisualIntent],
        cues: list[SubtitleCue],
        usages: list[AssetUsage],
    ) -> dict[str, Any]:
        assert self._editorial_rhythm_service is not None
        return self._editorial_rhythm_service.validate(
            visual_intents,
            cues,
            usages,
        ).to_dict()

    def _run_caption_ux(self, cues: list[SubtitleCue]) -> dict[str, Any]:
        assert self._caption_ux_service is not None
        return self._caption_ux_service.evaluate(cues).to_dict()

    async def _run_caption_previews(
        self,
        run_id: str,
        video_path: str,
        cues: list[SubtitleCue],
    ) -> dict[str, Any]:
        assert self._caption_ux_service is not None
        assert self._media_inspection_port is not None
        report = self._caption_ux_service.evaluate(cues)
        preview_directory = self._output_directory / f"{run_id}_caption_previews"
        preview_directory.mkdir(parents=True, exist_ok=True)
        samples: list[dict[str, Any]] = []
        for sample in report.preview_samples:
            source_path = preview_directory / f"{sample.kind}_100.jpg"
            await self._media_inspection_port.extract_frame(
                video_path,
                str(source_path),
                sample.timestamp_ms / 1_000,
            )
            variants = await asyncio.to_thread(
                self._caption_ux_service.create_preview_variants,
                str(source_path),
            )
            samples.append({**sample.to_dict(), "paths": variants})
        return {
            "profile_name": report.profile_name,
            "sizes": ["100%", "75%", "small_phone"],
            "samples": samples,
        }

    async def _run_visual_localization(
        self,
        visual_intents: list[VisualIntent],
        *,
        visual_anchor: str | None,
    ) -> dict[str, Any]:
        assert self._visual_intent_localization_service is not None
        localized = await self._visual_intent_localization_service.localize(
            visual_intents, "English", source_anchor=visual_anchor
        )
        return {
            "target_language": "English",
            "visual_intents": [
                self._visual_intent_to_dict(intent) for intent in localized
            ],
        }

    def _run_visual_edit_plan(
        self,
        visual_intents: list[VisualIntent],
    ) -> dict[str, Any]:
        assert self._visual_edit_planning_service is not None
        adjusted, plan = self._visual_edit_planning_service.plan(visual_intents)
        return {
            "plan": plan.to_dict(),
            "visual_intents": [
                self._visual_intent_to_dict(intent) for intent in adjusted
            ],
        }

    async def _run_music_selection(
        self,
        music_context: dict[str, Any],
        visual_intents: list[VisualIntent],
    ) -> dict[str, Any]:
        """Choose only licensed music and degrade explicitly to narration-only."""
        assert self._music_director_service is not None
        try:
            decision = await self._music_director_service.decide(
                topic=str(music_context["topic"]),
                script_text=str(music_context["script_text"]),
                scene_moods=[intent.mood for intent in visual_intents],
                theme_override=music_context.get("theme_override"),
                track_override=music_context.get("track_override"),
            )
        except BackgroundMusicError as error:
            return {
                "status": "narration_only",
                "reason": str(error),
                "track_file_path": None,
            }
        return {"status": "selected", **decision.to_dict()}

    def _run_sound_design(
        self,
        visual_intents: list[VisualIntent],
        *,
        has_music: bool,
    ) -> dict[str, Any]:
        assert self._sound_design_planning_service is not None
        return self._sound_design_planning_service.plan(
            visual_intents,
            has_music=has_music,
        ).to_dict()

    def _run_audio_quality(
        self,
        sound_design_artifact: dict[str, Any],
        render_artifact: dict[str, Any],
        music_selection: dict[str, Any] | None,
    ) -> dict[str, Any]:
        assert self._audio_quality_gate_service is not None
        inspection_data = render_artifact.get("inspection")
        signal_data = render_artifact.get("quality_signals")
        if not inspection_data or not signal_data:
            raise RuntimeError("Audio quality requires media inspection and signal evidence.")
        track = self._background_track_from_selection(music_selection)
        report = self._audio_quality_gate_service.evaluate(
            plan=SoundDesignPlan.from_dict(sound_design_artifact),
            inspection=MediaInspection.from_dict(dict(inspection_data)),
            signals=MediaQualitySignals.from_dict(dict(signal_data)),
            music_track=track,
        )
        if not report.passed:
            failures = ", ".join(
                check.name for check in report.checks if check.blocking and not check.passed
            )
            raise RuntimeError(
                f"Audio master scored {report.score}/100 and cannot be packaged"
                f"{f': {failures}' if failures else '.'}"
            )
        return report.to_dict()

    def _run_visual_quality(
        self,
        visual_edit_plan_artifact: dict[str, Any],
        visual_intents: list[VisualIntent],
        source_assets: list[MediaAsset],
        usages: list[AssetUsage],
        render_artifact: dict[str, Any],
    ) -> dict[str, Any]:
        assert self._visual_quality_gate_service is not None
        signal_data = render_artifact.get("quality_signals")
        if not signal_data:
            raise RuntimeError(
                "Visual quality requires measured rendered-video evidence."
            )
        report = self._visual_quality_gate_service.evaluate(
            plan=VisualEditPlan.from_dict(
                dict(visual_edit_plan_artifact["plan"])
            ),
            visual_intents=visual_intents,
            source_assets=source_assets,
            asset_usages=usages,
            quality_signals=MediaQualitySignals.from_dict(dict(signal_data)),
        )
        if not report.passed:
            failures = ", ".join(
                check.name
                for check in report.checks
                if check.blocking and not check.passed
            )
            raise RuntimeError(
                f"Visual edit scored {report.automatic_score}/90 and cannot be packaged"
                f"{f': {failures}' if failures else '.'}"
            )
        return report.to_dict()

    @staticmethod
    def _background_track_from_selection(
        music_selection: dict[str, Any] | None,
    ) -> BackgroundTrack | None:
        if not music_selection or music_selection.get("status") != "selected":
            return None
        return BackgroundTrack(
            file_path=str(music_selection["track_file_path"]),
            title=str(music_selection["track_title"]),
            attribution=str(music_selection["track_attribution"]),
            license=str(music_selection["track_license"]),
            themes=[str(value) for value in music_selection.get("track_themes", [])],
            source_url=str(music_selection.get("track_source_url") or ""),
            sha256=str(music_selection.get("track_sha256") or ""),
            evidence_reference=str(music_selection.get("track_evidence_reference") or ""),
            commercial_use=bool(music_selection.get("track_commercial_use", True)),
            youtube_allowed=bool(music_selection.get("track_youtube_allowed", True)),
            attribution_required=bool(music_selection.get("track_attribution_required", True)),
        )

    async def _run_upload_package(
        self,
        *,
        run_id: str,
        package_context: dict[str, Any],
        video_path: str,
        cues: list[SubtitleCue],
        source_assets: list[MediaAsset],
        music_selection: dict[str, Any] | None,
        creative_quality_report: dict[str, Any] | None,
        audio_quality_report: dict[str, Any] | None,
        visual_quality_report: dict[str, Any] | None,
    ) -> dict[str, Any]:
        assert self._youtube_upload_package_service is not None
        credited_assets = list(source_assets)
        if music_selection and music_selection.get("status") == "selected":
            credited_assets.append(
                MediaAsset(
                    id=f"music:{music_selection['track_title']}",
                    provider="local-licensed-music",
                    provider_asset_id=str(music_selection["track_title"]),
                    media_type="audio",
                    original_url=str(music_selection.get("track_source_url") or ""),
                    attribution=str(music_selection["track_attribution"]),
                    license=str(music_selection["track_license"]),
                    local_path=str(music_selection["track_file_path"]),
                    tags=list(music_selection.get("track_themes", [])),
                )
            )
        package = await self._youtube_upload_package_service.prepare_factory_output(
            topic=str(package_context["topic"]),
            script=self._script_from_dict(package_context["script"]),
            video_path=video_path,
            subtitle_cues=cues,
            source_assets=credited_assets,
            output_directory=str(self._output_directory / f"{run_id}_youtube"),
            language=str(package_context.get("language") or "en"),
            creative_quality_report=(
                CreativeQualityReport.from_dict(creative_quality_report)
                if creative_quality_report is not None
                else None
            ),
            audio_quality_report=(
                AudioQualityReport.from_dict(audio_quality_report)
                if audio_quality_report is not None
                else None
            ),
            visual_quality_report=(
                VisualQualityReport.from_dict(visual_quality_report)
                if visual_quality_report is not None
                else None
            ),
        )
        return package.to_dict()

    async def _run_youtube_upload(self, video_path: str, script: dict[str, Any] | None, privacy: str = "unlisted") -> dict[str, Any]:
        if self._youtube_upload_port is None:
            return {"status": "skipped"}

        title = "Automated Video"
        description = "Automated Video Upload"
        tags = ["Science", "Mystery"]

        if script:
            title = script.get("topic", title)[:100]
            description = script.get("full_text", description)
            tags = list(set(script.get("topic", "").split() + ["StrangeThingsLab", "Science", "Mystery"]))

        video_id = await self._youtube_upload_port.upload_video(
            video_path=video_path,
            title=title,
            description=description,
            tags=tags,
            privacy_status=privacy
        )
        return {
            "youtube_video_id": video_id,
            "url": f"https://youtu.be/{video_id}"
        }

    def _run_creative_quality(
        self,
        *,
        package_context: dict[str, Any],
        visual_intents: list[VisualIntent],
        cues: list[SubtitleCue],
        source_assets: list[MediaAsset],
        render_artifact: dict[str, Any],
        music_selection: dict[str, Any] | None,
    ) -> dict[str, Any]:
        assert self._creative_quality_gate_service is not None
        narrative_data = package_context.get("narrative_quality_report")
        retention_data = package_context.get("retention_plan")
        voice_direction_data = package_context.get("voice_direction")
        inspection_data = render_artifact.get("inspection")
        signal_data = render_artifact.get("quality_signals")
        if not narrative_data or not retention_data or not inspection_data or not signal_data:
            raise RuntimeError(
                "Creative quality requires narrative, retention, inspection, and media signal evidence."
            )
        sound_mode = (
            "licensed_music"
            if music_selection and music_selection.get("status") == "selected"
            else "procedural"
            if self._procedural_audio_accents_enabled
            else "none"
        )
        report = self._creative_quality_gate_service.evaluate(
            narrative_report=NarrativeQualityReport.from_dict(dict(narrative_data)),
            visual_intents=visual_intents,
            subtitle_cues=cues,
            source_assets=source_assets,
            inspection=MediaInspection.from_dict(dict(inspection_data)),
            quality_signals=MediaQualitySignals.from_dict(dict(signal_data)),
            fact_check_passed=bool(package_context.get("fact_check_passed")),
            caption_ux_passed=self._caption_ux_service is not None,
            visual_relevance_passed=bool(source_assets),
            sound_design_mode=sound_mode,
            retention_plan=RetentionPlan.from_dict(dict(retention_data)),
            voice_direction=(
                VoiceDirection.from_dict(dict(voice_direction_data))
                if voice_direction_data
                else None
            ),
        )
        return report.to_dict()

    async def _run_render(
        self,
        run_id: str,
        audio_asset: AudioAsset,
        highlight: SelectedHighlight,
        cues: list[SubtitleCue],
        visual_intents: list[VisualIntent],
        video_clips: list[str],
        background_music_path: str | None,
        procedural_audio_accents: bool,
        sound_design_artifact: dict[str, Any] | None,
        visual_edit_plan_artifact: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Materialize ASS captions and delegate final MP4 creation to a port."""
        assert self._render_port is not None
        assert self._premium_subtitle_formatter is not None
        subtitle_path = self._output_directory / f"{run_id}.ass"
        output_path = self._output_directory / f"{run_id}.mp4"
        ass_document = self._premium_subtitle_formatter.format(
            cues,
            visual_intents=visual_intents,
        )
        await asyncio.to_thread(self._write_text, subtitle_path, ass_document)
        creative_timeline_path: Path | None = None
        visual_edit_plan = (
            VisualEditPlan.from_dict(dict(visual_edit_plan_artifact["plan"]))
            if visual_edit_plan_artifact is not None
            else None
        )
        if self._remotion_timeline_service is not None:
            creative_timeline_path = self._output_directory / f"{run_id}.motion.json"
            creative_timeline = self._remotion_timeline_service.build(
                title=visual_intents[0].primary_keyword,
                cues=cues,
                visual_intents=visual_intents,
                video_clips=video_clips,
                visual_edit_plan=visual_edit_plan,
            )
            await asyncio.to_thread(
                self._write_text,
                creative_timeline_path,
                json.dumps(creative_timeline, ensure_ascii=False, indent=2),
            )
        clip_durations_seconds = [
            intent.duration_ms / 1_000 for intent in visual_intents
        ]
        expected_duration_seconds = (
            highlight.end_ms - highlight.start_ms
        ) / 1_000
        # Runs checkpointed before time-coded storyboard support can still be
        # resumed. New runs always satisfy this branch and preserve exact cuts;
        # legacy artifacts fall back to the renderer's bounded-cut policy.
        if (
            any(duration <= 0 for duration in clip_durations_seconds)
            or abs(sum(clip_durations_seconds) - expected_duration_seconds) > 0.050
        ):
            clip_durations_seconds = None
        rendered_path = await self._render_port.render_shorts(
            audio_asset.local_path,
            str(subtitle_path),
            video_clips,
            str(output_path),
            audio_start_ms=highlight.start_ms,
            audio_end_ms=highlight.end_ms,
            clip_durations_seconds=clip_durations_seconds,
            motion_types=[intent.motion_type for intent in visual_intents],
            shot_types=[intent.shot_type for intent in visual_intents],
            visual_jobs=[intent.visual_job for intent in visual_intents],
            background_music_path=background_music_path,
            procedural_audio_accents=procedural_audio_accents,
            sound_design_plan=sound_design_artifact,
            creative_timeline_path=(
                str(creative_timeline_path)
                if creative_timeline_path is not None
                else None
            ),
        )
        inspection = None
        if self._media_inspection_port is not None:
            assert self._post_render_quality_service is not None
            inspection = await self._media_inspection_port.inspect(rendered_path)
            self._post_render_quality_service.validate(
                inspection,
                expected_duration_seconds=(highlight.end_ms - highlight.start_ms) / 1_000,
                expected_width=1080,
                expected_height=1920,
            )
        quality_signals = None
        if self._media_quality_analysis_port is not None:
            assert self._post_render_quality_service is not None
            quality_signals = await self._media_quality_analysis_port.analyze(rendered_path)
            self._post_render_quality_service.validate_content(
                quality_signals,
                expected_duration_seconds=(highlight.end_ms - highlight.start_ms) / 1_000,
            )
        return {
            "subtitle_ass_path": str(subtitle_path),
            "output_path": rendered_path,
            "creative_timeline_path": (
                str(creative_timeline_path)
                if creative_timeline_path is not None
                else None
            ),
            "quality_signals": (
                quality_signals.to_dict() if quality_signals is not None else None
            ),
            "inspection": inspection.to_dict() if inspection is not None else None,
        }

    @staticmethod
    def _write_text(path: Path, content: str) -> None:
        """Write a deterministic renderer input without blocking the event loop."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    @staticmethod
    def _script_to_dict(script: Script) -> dict[str, Any]:
        return {
            "id": script.id,
            "topic": script.topic,
            "full_text": script.full_text,
            "target_duration_seconds": script.target_duration_seconds,
            "estimated_word_count": script.estimated_word_count,
            "provider_used": script.provider_used,
            "created_at": script.created_at.isoformat(),
            "narrative_contract": (
                script.narrative_contract.to_dict()
                if script.narrative_contract is not None
                else None
            ),
            "narrative_beats": [beat.to_dict() for beat in script.narrative_beats],
        }

    @staticmethod
    def _script_from_dict(data: dict[str, Any]) -> Script:
        return Script(
            id=str(data["id"]),
            topic=str(data["topic"]),
            full_text=str(data["full_text"]),
            target_duration_seconds=int(data["target_duration_seconds"]),
            estimated_word_count=int(data["estimated_word_count"]),
            provider_used=str(data["provider_used"]),
            created_at=datetime.fromisoformat(str(data["created_at"])),
            narrative_contract=(
                NarrativeContract.from_dict(dict(data["narrative_contract"]))
                if data.get("narrative_contract")
                else None
            ),
            narrative_beats=tuple(
                NarrativeBeat.from_dict(dict(item))
                for item in data.get("narrative_beats", [])
            ),
        )

    @staticmethod
    def _voice_track_to_dict(voice_track: VoiceTrack) -> dict[str, Any]:
        return {
            "audio_id": voice_track.audio_id,
            "script_id": voice_track.script_id,
            "duration_seconds": voice_track.duration_seconds,
            "provider": voice_track.provider,
            "voice_name": voice_track.voice_name,
            "sample_rate": voice_track.sample_rate,
            "file_path": voice_track.file_path,
            "created_at": voice_track.created_at.isoformat(),
            "segments": [
                {"text": segment.text, "start": segment.start, "end": segment.end}
                for segment in voice_track.segments
            ],
            "direction": (
                voice_track.direction.to_dict()
                if voice_track.direction is not None
                else None
            ),
            "spoken_text": voice_track.spoken_text,
            "pronunciation_replacements": [
                {"source": source, "spoken": spoken}
                for source, spoken in voice_track.pronunciation_replacements
            ],
        }

    @staticmethod
    def _voice_track_from_dict(data: dict[str, Any]) -> VoiceTrack:
        return VoiceTrack(
            audio_id=str(data["audio_id"]),
            script_id=(str(data["script_id"]) if data.get("script_id") else None),
            duration_seconds=float(data["duration_seconds"]),
            provider=str(data["provider"]),
            voice_name=str(data["voice_name"]),
            sample_rate=int(data["sample_rate"]),
            file_path=str(data["file_path"]),
            created_at=datetime.fromisoformat(str(data["created_at"])),
            segments=[
                SpeechSegment(
                    text=str(segment["text"]),
                    start=float(segment["start"]),
                    end=float(segment["end"]),
                )
                for segment in data.get("segments", [])
            ],
            direction=(
                VoiceDirection.from_dict(dict(data["direction"]))
                if data.get("direction")
                else None
            ),
            spoken_text=str(data.get("spoken_text") or ""),
            pronunciation_replacements=tuple(
                (str(item["source"]), str(item["spoken"]))
                for item in data.get("pronunciation_replacements", [])
            ),
        )

    @staticmethod
    def _highlight_to_dict(highlight: SelectedHighlight) -> dict[str, Any]:
        return {
            "audio_asset_id": highlight.audio_asset_id,
            "start_ms": highlight.start_ms,
            "end_ms": highlight.end_ms,
            "score": highlight.score,
            "selector_used": highlight.selector_used,
            "hook_type": highlight.hook_type,
            "rationale": highlight.rationale,
        }

    @staticmethod
    def _highlight_from_dict(data: dict[str, Any]) -> SelectedHighlight:
        return SelectedHighlight(
            audio_asset_id=str(data["audio_asset_id"]),
            start_ms=int(data["start_ms"]),
            end_ms=int(data["end_ms"]),
            score=float(data["score"]),
            selector_used=str(data["selector_used"]),
            hook_type=str(data["hook_type"]),
            rationale=str(data["rationale"]),
        )

    @staticmethod
    def _word_timing_to_dict(word: WordTiming) -> dict[str, Any]:
        return {
            "text": word.text,
            "start_ms": word.start_ms,
            "end_ms": word.end_ms,
            "confidence": word.confidence,
        }

    @staticmethod
    def _word_timing_from_dict(data: dict[str, Any]) -> WordTiming:
        confidence = data.get("confidence")
        return WordTiming(
            text=str(data["text"]),
            start_ms=int(data["start_ms"]),
            end_ms=int(data["end_ms"]),
            confidence=float(confidence) if confidence is not None else None,
        )

    @classmethod
    def _cue_to_dict(cls, cue: SubtitleCue) -> dict[str, Any]:
        return {
            "index": cue.index,
            "scene_index": cue.scene_index,
            "words": [cls._word_timing_to_dict(word) for word in cue.words],
        }

    @classmethod
    def _cue_from_dict(cls, data: dict[str, Any]) -> SubtitleCue:
        words = [cls._word_timing_from_dict(item) for item in data["words"]]
        return SubtitleCue.from_words(
            words,
            index=int(data.get("index", 0)),
            scene_index=int(data.get("scene_index", -1)),
        )

    @staticmethod
    def _visual_intent_to_dict(intent: VisualIntent) -> dict[str, Any]:
        return {
            "primary_keyword": intent.primary_keyword,
            "mood": intent.mood,
            "motion_type": intent.motion_type,
            "forbidden_concepts": list(intent.forbidden_concepts),
            "secondary_keywords": list(intent.secondary_keywords),
            "start_ms": intent.start_ms,
            "end_ms": intent.end_ms,
            "narrative_role": intent.narrative_role,
            "shot_type": intent.shot_type,
            "narration_text": intent.narration_text,
            "visual_job": intent.visual_job,
            "required_subjects": list(intent.required_subjects),
            "required_actions": list(intent.required_actions),
            "required_relations": list(intent.required_relations),
            "forbidden_dominant_subjects": list(intent.forbidden_dominant_subjects),
            "explanation_mode": intent.explanation_mode,
            "overlay_labels": list(intent.overlay_labels),
            "explanatory_required": intent.explanatory_required,
        }

    @staticmethod
    def _visual_intent_from_dict(data: dict[str, Any]) -> VisualIntent:
        return VisualIntent(
            primary_keyword=str(data["primary_keyword"]),
            mood=str(data["mood"]),
            motion_type=str(data["motion_type"]),
            forbidden_concepts=tuple(data.get("forbidden_concepts", ())),
            secondary_keywords=tuple(data.get("secondary_keywords", ())),
            start_ms=int(data.get("start_ms", 0)),
            end_ms=int(data.get("end_ms", 0)),
            narrative_role=str(data.get("narrative_role", "development")),
            shot_type=str(data.get("shot_type", "medium")),
            narration_text=str(data.get("narration_text", "")),
            visual_job=str(data.get("visual_job", "support_context")),
            required_subjects=tuple(data.get("required_subjects", ())),
            required_actions=tuple(data.get("required_actions", ())),
            required_relations=tuple(data.get("required_relations", ())),
            forbidden_dominant_subjects=tuple(
                data.get("forbidden_dominant_subjects", ())
            ),
            explanation_mode=str(data.get("explanation_mode", "stock")),
            overlay_labels=tuple(data.get("overlay_labels", ())),
            explanatory_required=bool(data.get("explanatory_required", False)),
        )
