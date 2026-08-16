from __future__ import annotations

import pytest
from contextlib import asynccontextmanager
from pathlib import Path

from PIL import Image

from core.application.orchestration.pipeline_orchestrator import PipelineOrchestrator
from core.application.orchestration.run_executor import RunExecutor
from core.application.services.narrative_quality_service import NarrativeQualityService
from core.application.services.brand_narration_service import BrandNarrationService
from core.application.services.caption_ux_service import CaptionUxService
from core.application.services.premium_subtitle_formatter import PremiumSubtitleFormatter
from core.domain.entities.audio_asset import AudioAsset
from core.domain.entities.media_asset import MediaAsset
from core.domain.entities.pipeline_run import PipelineRun
from core.domain.entities.pipeline_run import PipelineRunStatus
from core.domain.entities.script import Script
from core.domain.entities.voice_track import VoiceTrack
from core.domain.exceptions import (
    BackgroundMusicError,
    FactCheckError,
    LowVisionConfidenceError,
    NarrativeQualityError,
    PipelineRunNotFoundError,
)
from core.domain.value_objects.background_track import BackgroundTrack
from core.domain.value_objects.fact_check_report import FactCheckReport, FactClaim
from core.domain.value_objects.fact_source import FactSource
from core.domain.value_objects.music_selection_decision import MusicSelectionDecision
from core.domain.value_objects.media_inspection import MediaInspection
from core.domain.value_objects.selected_highlight import SelectedHighlight
from core.domain.value_objects.word_timing import WordTiming


class InMemoryRunRepository:
    def __init__(self, run: PipelineRun) -> None:
        self.runs = {run.run_id: run}

    async def save(self, run: PipelineRun) -> None:
        self.runs[run.run_id] = run

    async def get_by_id(self, run_id: str) -> PipelineRun:
        try:
            return self.runs[run_id]
        except KeyError as error:
            raise PipelineRunNotFoundError(run_id) from error

    @asynccontextmanager
    async def lock_run(self, run_id: str):
        del run_id
        yield


class FakeMusicIntelligenceService:
    def __init__(self) -> None:
        self.calls = 0
        self.asset = AudioAsset.create(
            source_provider="local",
            source_asset_id="song.mp3",
            local_path="/tmp/song.mp3",
            duration_ms=30_000,
            media_type="audio/mpeg",
            license="licensed",
            usage_rights="publish",
            language="en",
        )

    async def process_music_hook_with_asset(self, source_uri: str, target_duration_ms: int):
        self.calls += 1
        return self.asset, SelectedHighlight(
            audio_asset_id=self.asset.id,
            start_ms=0,
            end_ms=target_duration_ms,
            score=0.9,
            selector_used="fake",
            hook_type="chorus",
            rationale="test",
        )


class FakeWordAlignmentPort:
    def __init__(self, *, fail_once: bool = True) -> None:
        self.calls = 0
        self.fail_once = fail_once
        self.last_transcript = None

    async def align(self, audio_asset, highlight, *, language=None, transcript=None):
        self.calls += 1
        self.last_transcript = transcript
        if self.fail_once:
            self.fail_once = False
            raise RuntimeError("temporary alignment failure")
        return [
            WordTiming("Dancing", 0, 500, 0.99),
            WordTiming("tonight!", 510, 1_000, 0.99),
        ]


class FakeCuePartitioningService:
    def partition(self, words):
        from core.domain.value_objects.subtitle_cue import SubtitleCue

        return [SubtitleCue.from_words(list(words))]


class FakeScenePlanningService:
    def plan_visual_intents(self, highlight, cues):
        from core.domain.value_objects.visual_intent import VisualIntent

        return [
            VisualIntent(
                "dancing",
                "energetic",
                "fast-paced",
                start_ms=highlight.start_ms,
                end_ms=highlight.end_ms,
                narrative_role="hook",
                shot_type="macro-close-up",
            )
        ]


class FakeVideoSearchService:
    def __init__(self) -> None:
        self.search_calls = 0
        self.download_calls = 0
        self.asset = MediaAsset(
            id="fake:video-1",
            provider="fake",
            provider_asset_id="video-1",
            original_url="https://example.com/video-1.mp4",
        )

    async def search(self, query: str, max_results: int):
        self.search_calls += 1
        return [self.asset]

    async def download(self, asset: MediaAsset) -> MediaAsset:
        self.download_calls += 1
        return asset.with_local_path("/tmp/video-1.mp4")


class FakeVisionAssetScoringService:
    def __init__(self) -> None:
        self.calls = 0

    async def score_visual_intent(self, intent, candidates):
        self.calls += 1
        return list(candidates)


class DiverseFakeVideoSearchService:
    def __init__(self) -> None:
        self.queries = []
        self.assets = [
            MediaAsset(
                id=f"fake:video-{index}",
                provider="fake",
                provider_asset_id=f"video-{index}",
                original_url=f"https://example.com/video-{index}.mp4",
            )
            for index in (1, 2)
        ]

    async def search(self, query: str, max_results: int):
        self.queries.append((query, max_results))
        return list(self.assets)

    async def download(self, asset: MediaAsset) -> MediaAsset:
        return asset.with_local_path(f"/tmp/{asset.provider_asset_id}.mp4")


class FakeRenderPort:
    def __init__(self) -> None:
        self.calls = 0
        self.fail_once = True
        self.last_kwargs = None

    async def render_shorts(self, audio_path, subtitle_ass_path, video_clips, output_path, **kwargs):
        self.calls += 1
        self.last_kwargs = kwargs
        if self.fail_once:
            self.fail_once = False
            raise RuntimeError("temporary render failure")
        return output_path


class FakeCaptionMediaInspector:
    async def inspect(self, video_path):
        del video_path
        return MediaInspection(
            format_names=("mp4",),
            duration_seconds=20.0,
            width=1080,
            height=1920,
            fps=30.0,
            video_codec="h264",
            pixel_format="yuv420p",
            audio_codec="aac",
            audio_sample_rate=48_000,
            audio_bitrate=192_000,
            file_size_bytes=100,
        )

    async def extract_frame(self, video_path, output_path, timestamp_seconds):
        del video_path, timestamp_seconds
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (1080, 1920), "navy").save(destination)


class FakePostRenderQualityService:
    def validate(self, inspection, **kwargs):
        del inspection, kwargs


class FakeScriptService:
    def __init__(self) -> None:
        self.calls = 0

    async def generate(
        self,
        topic: str,
        target_duration_seconds: int,
        *,
        language: str | None = None,
    ) -> Script:
        self.calls += 1
        assert language == "tr"
        return Script.create(
            topic=topic,
            full_text="Octopuses have three hearts. Two pump blood to the gills.",
            target_duration_seconds=target_duration_seconds,
            provider_used="fake-script",
        )


class FakeVoiceService:
    def __init__(self, audio_path: str) -> None:
        self.calls = 0
        self.audio_path = audio_path
        self.last_script = None

    async def generate(self, script: Script) -> VoiceTrack:
        self.calls += 1
        self.last_script = script
        return VoiceTrack.create(
            script_id=script.id,
            duration_seconds=2.0,
            provider="fake-voice",
            voice_name="narrator",
            sample_rate=48_000,
            file_path=self.audio_path,
        )


class FakeScriptRewriter:
    async def rewrite(self, script, fact_check_report):
        del fact_check_report
        return script


class FakeMusicDirectorService:
    def __init__(self, *, unavailable: bool = False) -> None:
        self.calls = 0
        self.unavailable = unavailable

    async def decide(self, **kwargs):
        self.calls += 1
        if self.unavailable:
            raise BackgroundMusicError("Licensed library is empty.")
        assert kwargs["theme_override"] == "mystery"
        assert kwargs["track_override"] == "deep-ocean"
        return MusicSelectionDecision(
            theme="mystery",
            confidence=1.0,
            rationale="Explicit test selection.",
            track=BackgroundTrack(
                "/tmp/deep-ocean.mp3",
                "Deep Ocean",
                "Test Composer",
                "Commercial",
                ["mystery", "ocean"],
            ),
            overridden=True,
        )


class FakeScriptFactCheckService:
    def __init__(self, *, verified: bool = True, rewritten: bool = False) -> None:
        self.calls = 0
        self.verified = verified
        self.rewritten = rewritten

    async def verify_with_rewrites(self, script, rewriter, max_rewrites):
        del rewriter, max_rewrites
        self.calls += 1
        source = FactSource(
            title="Octopus",
            url="https://example.test/octopus",
            extract="Octopuses have three hearts.",
        )
        claim = FactClaim(
            claim="Octopuses have three hearts.",
            verdict="supported" if self.verified else "uncertain",
            explanation="test",
            source_urls=[source.url] if self.verified else [],
            evidence_quote=source.extract if self.verified else "",
        )
        final_report = FactCheckReport.create(
            claims=[claim],
            sources=[source],
            provider_used="fake-fact-check",
        )
        if not self.rewritten:
            return script, [final_report]
        initial_report = FactCheckReport.create(
            claims=[
                FactClaim(
                    claim="Unsupported opening claim.",
                    verdict="uncertain",
                    explanation="rewrite required",
                    source_urls=[],
                    evidence_quote="",
                )
            ],
            sources=[source],
            provider_used="fake-fact-check",
        )
        rewritten_script = Script.create(
            topic=script.topic,
            full_text="Octopuses have three hearts.",
            target_duration_seconds=script.target_duration_seconds,
            provider_used="fake-grounded-rewrite",
        )
        return rewritten_script, [initial_report, final_report]


@pytest.mark.asyncio
async def test_orchestrator_resumes_after_alignment_failure_without_repeating_audio_stage():
    run = PipelineRun.create()
    repository = InMemoryRunRepository(run)
    music = FakeMusicIntelligenceService()
    alignment = FakeWordAlignmentPort()
    orchestrator = PipelineOrchestrator(
        RunExecutor(repository),
        music,
        alignment,
        FakeCuePartitioningService(),
        FakeScenePlanningService(),
    )

    with pytest.raises(RuntimeError, match="temporary alignment failure"):
        await orchestrator.run_factory(run.run_id, "/tmp/song.mp3")

    result = await orchestrator.run_factory(run.run_id, "/tmp/song.mp3")

    assert music.calls == 1
    assert alignment.calls == 2
    assert result["visual_intents"][0].motion_type == "fast-paced"


@pytest.mark.asyncio
async def test_orchestrator_retries_render_without_repeating_visual_downloads(tmp_path):
    run = PipelineRun.create()
    repository = InMemoryRunRepository(run)
    video_search = FakeVideoSearchService()
    vision_scoring = FakeVisionAssetScoringService()
    renderer = FakeRenderPort()
    orchestrator = PipelineOrchestrator(
        RunExecutor(repository),
        FakeMusicIntelligenceService(),
        FakeWordAlignmentPort(fail_once=False),
        FakeCuePartitioningService(),
        FakeScenePlanningService(),
        video_search_service=video_search,
        vision_asset_scoring_service=vision_scoring,
        render_port=renderer,
        premium_subtitle_formatter=PremiumSubtitleFormatter(),
        output_directory=tmp_path,
    )

    with pytest.raises(RuntimeError, match="temporary render failure"):
        await orchestrator.run_factory(run.run_id, "/tmp/song.mp3")

    result = await orchestrator.run_factory(run.run_id, "/tmp/song.mp3")

    assert video_search.search_calls == 1
    assert video_search.download_calls == 1
    assert vision_scoring.calls == 1
    assert renderer.calls == 2
    assert renderer.last_kwargs["clip_durations_seconds"] == [20.0]
    assert renderer.last_kwargs["motion_types"] == ["fast-paced"]
    assert renderer.last_kwargs["shot_types"] == ["macro-close-up"]
    assert renderer.last_kwargs["visual_jobs"] == ["support_context"]
    assert result["output_path"] == str(tmp_path / f"{run.run_id}.mp4")
    assert run.status is PipelineRunStatus.COMPLETED


@pytest.mark.asyncio
async def test_caption_ux_stage_generates_three_multi_size_preview_sets(tmp_path):
    run = PipelineRun.create()
    renderer = FakeRenderPort()
    renderer.fail_once = False
    orchestrator = PipelineOrchestrator(
        RunExecutor(InMemoryRunRepository(run)),
        FakeMusicIntelligenceService(),
        FakeWordAlignmentPort(fail_once=False),
        FakeCuePartitioningService(),
        FakeScenePlanningService(),
        caption_ux_service=CaptionUxService(),
        video_search_service=FakeVideoSearchService(),
        vision_asset_scoring_service=FakeVisionAssetScoringService(),
        render_port=renderer,
        premium_subtitle_formatter=PremiumSubtitleFormatter(),
        media_inspection_port=FakeCaptionMediaInspector(),
        post_render_quality_service=FakePostRenderQualityService(),
        output_directory=tmp_path,
    )

    result = await orchestrator.run_factory(run.run_id, "/tmp/song.mp3")

    assert result["caption_ux"]["score"] == 10.0
    assert result["caption_ux"]["passed"] is True
    assert result["caption_previews"]["sizes"] == ["100%", "75%", "small_phone"]
    assert len(result["caption_previews"]["samples"]) == 3
    preview_paths = [
        path
        for sample in result["caption_previews"]["samples"]
        for path in sample["paths"]
    ]
    assert len(preview_paths) == 9
    assert all(Path(path).is_file() for path in preview_paths)


@pytest.mark.asyncio
async def test_vision_search_uses_subject_queries_and_avoids_adjacent_asset_reuse(tmp_path):
    from core.domain.value_objects.visual_intent import VisualIntent

    run = PipelineRun.create()
    video_search = DiverseFakeVideoSearchService()
    orchestrator = PipelineOrchestrator(
        RunExecutor(InMemoryRunRepository(run)),
        FakeMusicIntelligenceService(),
        FakeWordAlignmentPort(fail_once=False),
        FakeCuePartitioningService(),
        FakeScenePlanningService(),
        video_search_service=video_search,
        vision_asset_scoring_service=FakeVisionAssetScoringService(),
        render_port=FakeRenderPort(),
        premium_subtitle_formatter=PremiumSubtitleFormatter(),
        output_directory=tmp_path,
    )
    intents = [
        VisualIntent(
            "octopus",
            "reflective",
            "steady",
            secondary_keywords=("ocean",),
            start_ms=0,
            end_ms=1_500,
            narrative_role="hook",
            shot_type="macro-close-up",
        ),
        VisualIntent(
            "heart",
            "reflective",
            "steady",
            secondary_keywords=("anatomy",),
            start_ms=1_500,
            end_ms=3_000,
            narrative_role="context",
            shot_type="wide-establishing",
        ),
    ]

    artifact = await orchestrator._run_vision_search(intents)

    assert artifact["video_clips"] == [
        "/tmp/video-1.mp4",
        "/tmp/video-2.mp4",
    ]
    assert video_search.queries == [
        ("octopus", 10),
        ("heart", 10),
    ]


@pytest.mark.asyncio
async def test_vision_search_uses_semantic_query_for_explanatory_beat(tmp_path):
    from core.domain.value_objects.visual_intent import VisualIntent

    run = PipelineRun.create()
    video_search = DiverseFakeVideoSearchService()
    orchestrator = PipelineOrchestrator(
        RunExecutor(InMemoryRunRepository(run)),
        FakeMusicIntelligenceService(),
        FakeWordAlignmentPort(fail_once=False),
        FakeCuePartitioningService(),
        FakeScenePlanningService(),
        video_search_service=video_search,
        vision_asset_scoring_service=FakeVisionAssetScoringService(),
        render_port=FakeRenderPort(),
        premium_subtitle_formatter=PremiumSubtitleFormatter(),
        output_directory=tmp_path,
    )
    intent = VisualIntent(
        "octopus",
        "educational",
        "steady",
        secondary_keywords=("anatomy",),
        required_subjects=("gills",),
        required_actions=("pump blood",),
        explanation_mode="hybrid",
        overlay_labels=("2 HEARTS → GILLS",),
        explanatory_required=True,
        start_ms=0,
        end_ms=2_000,
    )

    await orchestrator._run_vision_search([intent])

    assert video_search.queries[0] == (
        "octopus anatomy gills pump blood medium",
        10,
    )


def test_visual_intent_checkpoint_round_trip_preserves_semantic_contract():
    from core.domain.value_objects.visual_intent import VisualIntent

    intent = VisualIntent(
        "octopus",
        "educational",
        "steady",
        narration_text="İki kalp solungaçlara kan pompalar.",
        visual_job="demonstrate_mechanism",
        required_subjects=("octopus", "gills"),
        required_actions=("pump blood",),
        required_relations=("heart-to-gills",),
        forbidden_dominant_subjects=("stingray",),
        explanation_mode="hybrid",
        overlay_labels=("2 KALP → SOLUNGAÇ",),
        explanatory_required=True,
        start_ms=0,
        end_ms=2_000,
    )

    restored = PipelineOrchestrator._visual_intent_from_dict(
        PipelineOrchestrator._visual_intent_to_dict(intent)
    )

    assert restored == intent


@pytest.mark.asyncio
async def test_vision_search_reuses_verified_non_adjacent_clip_before_weak_unique_clip(tmp_path):
    from core.domain.value_objects.visual_intent import VisualIntent

    class RejectLoneThirdCandidate(FakeVisionAssetScoringService):
        async def score_visual_intent(self, intent, candidates):
            self.calls += 1
            if len(candidates) == 1 and candidates[0].asset.id == "fake:video-3":
                raise LowVisionConfidenceError("weak unused tail")
            return list(candidates)

    video_search = DiverseFakeVideoSearchService()
    video_search.assets.append(
        MediaAsset(
            id="fake:video-3",
            provider="fake",
            provider_asset_id="video-3",
            original_url="https://example.com/video-3.mp4",
        )
    )
    run = PipelineRun.create()
    orchestrator = PipelineOrchestrator(
        RunExecutor(InMemoryRunRepository(run)),
        FakeMusicIntelligenceService(),
        FakeWordAlignmentPort(fail_once=False),
        FakeCuePartitioningService(),
        FakeScenePlanningService(),
        video_search_service=video_search,
        vision_asset_scoring_service=RejectLoneThirdCandidate(),
        render_port=FakeRenderPort(),
        premium_subtitle_formatter=PremiumSubtitleFormatter(),
        output_directory=tmp_path,
    )
    intents = [
        VisualIntent("octopus", "reflective", "steady", start_ms=i * 1000, end_ms=(i + 1) * 1000)
        for i in range(3)
    ]

    artifact = await orchestrator._run_vision_search(intents)

    assert artifact["video_clips"] == [
        "/tmp/video-1.mp4",
        "/tmp/video-2.mp4",
        "/tmp/video-1.mp4",
    ]


@pytest.mark.asyncio
async def test_topic_factory_runs_script_voice_and_alignment_in_one_durable_pipeline(tmp_path):
    run = PipelineRun.create()
    repository = InMemoryRunRepository(run)
    script_service = FakeScriptService()
    fact_check_service = FakeScriptFactCheckService(rewritten=True)
    voice_service = FakeVoiceService(str(tmp_path / "narration.mp3"))
    alignment = FakeWordAlignmentPort(fail_once=False)
    music_director = FakeMusicDirectorService()
    orchestrator = PipelineOrchestrator(
        RunExecutor(repository),
        FakeMusicIntelligenceService(),
        alignment,
        FakeCuePartitioningService(),
        FakeScenePlanningService(),
        script_service=script_service,
        script_fact_check_service=fact_check_service,
        script_rewriter=FakeScriptRewriter(),
        voice_service=voice_service,
        music_director_service=music_director,
    )

    result = await orchestrator.run_topic_factory(
        run.run_id,
        "Why do octopuses have three hearts?",
        target_duration_seconds=30,
        language="tr",
        music_theme="mystery",
        music_track="deep-ocean",
    )

    assert script_service.calls == 1
    assert fact_check_service.calls == 1
    assert voice_service.calls == 1
    assert voice_service.last_script.id == result["script"].id
    assert result["script"].provider_used == "fake-grounded-rewrite"
    assert len(result["fact_check_reports"]) == 2
    assert alignment.last_transcript == result["script"].full_text
    assert result["audio_asset"].language == "tr"
    assert music_director.calls == 1
    assert result["music_selection"]["status"] == "selected"
    assert result["music_selection"]["track_file_path"] == "/tmp/deep-ocean.mp3"
    assert run.has_completed_stage(PipelineOrchestrator.SCRIPT_GENERATION)
    assert run.has_completed_stage(PipelineOrchestrator.FACT_CHECK)
    assert run.has_completed_stage(PipelineOrchestrator.VOICE_GENERATION)
    assert run.has_completed_stage(PipelineOrchestrator.AUDIO_INTELLIGENCE)
    assert run.has_completed_stage(PipelineOrchestrator.MUSIC_SELECTION)


@pytest.mark.asyncio
async def test_topic_factory_applies_brand_signature_after_hook_before_voice(tmp_path):
    run = PipelineRun.create()
    repository = InMemoryRunRepository(run)
    voice_service = FakeVoiceService(str(tmp_path / "narration.mp3"))
    alignment = FakeWordAlignmentPort(fail_once=False)
    orchestrator = PipelineOrchestrator(
        RunExecutor(repository),
        FakeMusicIntelligenceService(),
        alignment,
        FakeCuePartitioningService(),
        FakeScenePlanningService(),
        script_service=FakeScriptService(),
        script_fact_check_service=FakeScriptFactCheckService(),
        script_rewriter=FakeScriptRewriter(),
        brand_narration_service=BrandNarrationService(),
        voice_service=voice_service,
    )

    result = await orchestrator.run_topic_factory(
        run.run_id,
        "Why do octopuses have three hearts?",
        language="tr",
        use_background_music=False,
    )

    expected = (
        "Octopuses have three hearts. Welcome to Strange Things. "
        "Two pump blood to the gills."
    )
    assert result["script"].full_text == expected
    assert voice_service.last_script.full_text == expected
    assert alignment.last_transcript == expected
    assert result["brand_narration"] == {
        "script": PipelineOrchestrator._script_to_dict(result["script"]),
        "signature": "Welcome to Strange Things.",
        "position": "after_hook",
    }
    assert run.has_completed_stage(PipelineOrchestrator.BRAND_NARRATION)
    assert run.has_completed_stage(PipelineOrchestrator.VOICE_GENERATION)


@pytest.mark.asyncio
async def test_music_selection_degrades_safely_when_no_licensed_track_exists(tmp_path):
    run = PipelineRun.create()
    orchestrator = PipelineOrchestrator(
        RunExecutor(InMemoryRunRepository(run)),
        FakeMusicIntelligenceService(),
        FakeWordAlignmentPort(fail_once=False),
        FakeCuePartitioningService(),
        FakeScenePlanningService(),
        script_service=FakeScriptService(),
        script_fact_check_service=FakeScriptFactCheckService(),
        script_rewriter=FakeScriptRewriter(),
        voice_service=FakeVoiceService(str(tmp_path / "narration.mp3")),
        music_director_service=FakeMusicDirectorService(unavailable=True),
    )

    result = await orchestrator.run_topic_factory(
        run.run_id,
        "Octopus mystery",
        language="tr",
        music_theme="mystery",
        music_track="deep-ocean",
    )

    assert result["music_selection"]["status"] == "narration_only"
    assert result["music_selection"]["track_file_path"] is None
    assert "Licensed library is empty" in result["music_selection"]["reason"]


@pytest.mark.asyncio
async def test_topic_factory_blocks_voice_when_claims_remain_unsupported(tmp_path):
    run = PipelineRun.create()
    repository = InMemoryRunRepository(run)
    voice_service = FakeVoiceService(str(tmp_path / "must-not-exist.mp3"))
    orchestrator = PipelineOrchestrator(
        RunExecutor(repository),
        FakeMusicIntelligenceService(),
        FakeWordAlignmentPort(fail_once=False),
        FakeCuePartitioningService(),
        FakeScenePlanningService(),
        script_service=FakeScriptService(),
        script_fact_check_service=FakeScriptFactCheckService(verified=False),
        script_rewriter=FakeScriptRewriter(),
        voice_service=voice_service,
    )

    with pytest.raises(FactCheckError, match="remains unsupported"):
        await orchestrator.run_topic_factory(
            run.run_id,
            "Why do octopuses have three hearts?",
            target_duration_seconds=30,
            language="tr",
        )

    assert voice_service.calls == 0
    assert run.has_completed_stage(PipelineOrchestrator.SCRIPT_GENERATION)
    assert not run.has_completed_stage(PipelineOrchestrator.VOICE_GENERATION)


@pytest.mark.asyncio
async def test_topic_factory_blocks_voice_when_narrative_contract_fails(tmp_path):
    run = PipelineRun.create()
    repository = InMemoryRunRepository(run)
    voice_service = FakeVoiceService(str(tmp_path / "must-not-exist.mp3"))
    orchestrator = PipelineOrchestrator(
        RunExecutor(repository),
        FakeMusicIntelligenceService(),
        FakeWordAlignmentPort(fail_once=False),
        FakeCuePartitioningService(),
        FakeScenePlanningService(),
        script_service=FakeScriptService(),
        script_fact_check_service=FakeScriptFactCheckService(),
        script_rewriter=FakeScriptRewriter(),
        narrative_quality_service=NarrativeQualityService(),
        voice_service=voice_service,
    )

    with pytest.raises(NarrativeQualityError, match="weak_hook"):
        await orchestrator.run_topic_factory(
            run.run_id,
            "Why do octopuses have three hearts?",
            target_duration_seconds=24,
            language="tr",
        )

    assert voice_service.calls == 0
    assert run.has_completed_stage(PipelineOrchestrator.FACT_CHECK)
    assert not run.has_completed_stage(PipelineOrchestrator.NARRATIVE_QUALITY)
    assert not run.has_completed_stage(PipelineOrchestrator.VOICE_GENERATION)
