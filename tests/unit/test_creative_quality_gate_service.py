from dataclasses import replace

from core.application.services.creative_quality_gate_service import (
    CreativeQualityGateService,
)
from core.application.services.narrative_quality_service import NarrativeQualityService
from core.application.services.retention_planning_service import RetentionPlanningService
from core.domain.entities.media_asset import MediaAsset
from core.domain.entities.script import Script
from core.domain.value_objects.media_inspection import MediaInspection
from core.domain.value_objects.media_quality_signals import MediaQualitySignals
from core.domain.value_objects.subtitle_cue import SubtitleCue
from core.domain.value_objects.visual_intent import VisualIntent
from core.domain.value_objects.voice_direction import VoiceDirection


def _narrative_report():
    script = Script.create(
        topic="Why can self-healing materials repair cracks?",
        full_text=(
            "How can a material repair its own crack? "
            "Because damage releases a healing agent into the gap. "
            "The hardened bond stops the crack from spreading."
        ),
        target_duration_seconds=24,
        provider_used="test",
    )
    return NarrativeQualityService().validate(script, language="en")[1]


def _retention_plan(*, passed: bool = True):
    script = Script.create(
        topic="Why can self-healing materials repair cracks?",
        full_text=(
            "How can a material repair its own crack? "
            "Because damage releases a healing agent into the gap. "
            "The hardened bond stops the crack from spreading."
        ),
        target_duration_seconds=24,
        provider_used="test",
    )
    enriched = NarrativeQualityService().validate(script, language="en")[0]
    plan = RetentionPlanningService().build(enriched, language="en")
    return plan if passed else replace(
        plan,
        passed=False,
        issues=("first_30_seconds_not_fully_assigned",),
    )


def _intents():
    roles = ["hook", "context", "evidence", "evidence", "evidence", "payoff"]
    return [
        VisualIntent(
            primary_keyword="material",
            mood="curious",
            motion_type="steady",
            start_ms=index * 1_200,
            end_ms=(index + 1) * 1_200,
            narrative_role=role,
            narration_text="A concrete narration beat.",
            visual_job="demonstrate_mechanism",
        )
        for index, role in enumerate(roles)
    ]


def _assets(*, rights: bool = True):
    return [
        MediaAsset(
            id=f"asset-{index}",
            provider="test",
            provider_asset_id=str(index),
            original_url=f"https://example.test/{index}",
            width=1080,
            height=1920,
            attribution="Test creator" if rights else "",
            license="Commercial use" if rights else "",
        )
        for index in range(6)
    ]


def _inspection():
    return MediaInspection(
        format_names=("mp4",),
        duration_seconds=24.0,
        width=1080,
        height=1920,
        fps=30.0,
        video_codec="h264",
        pixel_format="yuv420p",
        audio_codec="aac",
        audio_sample_rate=48000,
        audio_bitrate=256000,
        file_size_bytes=10_000_000,
    )


def _signals():
    return MediaQualitySignals(
        opening_black_seconds=0.0,
        total_black_seconds=0.0,
        maximum_freeze_seconds=0.0,
        maximum_silence_seconds=0.4,
        integrated_lufs=-14.0,
        true_peak_dbfs=-2.0,
    )


def _cues():
    return [
        SubtitleCue(index + 1, index, index * 1.2, (index + 1) * 1.2, "short clear caption")
        for index in range(6)
    ]


def test_creative_gate_reaches_ready_without_hiding_pending_human_review():
    report = CreativeQualityGateService().evaluate(
        narrative_report=_narrative_report(),
        visual_intents=_intents(),
        subtitle_cues=_cues(),
        source_assets=_assets(),
        inspection=_inspection(),
        quality_signals=_signals(),
        fact_check_passed=True,
        caption_ux_passed=True,
        visual_relevance_passed=True,
        sound_design_mode="procedural",
    )

    assert report.score >= 90
    assert report.ready_to_upload is True
    assert report.premium_approved is False
    assert report.blocking_failures == ()
    assert sum(check.maximum_points for check in report.checks) == 100


def test_mandatory_rights_failure_blocks_even_when_total_score_is_high():
    report = CreativeQualityGateService().evaluate(
        narrative_report=_narrative_report(),
        visual_intents=_intents(),
        subtitle_cues=_cues(),
        source_assets=_assets(rights=False),
        inspection=_inspection(),
        quality_signals=_signals(),
        fact_check_passed=True,
        caption_ux_passed=True,
        visual_relevance_passed=True,
        sound_design_mode="licensed_music",
        human_creative_approval=True,
        voice_naturalness_score=5,
    )

    assert report.score >= 90
    assert report.ready_to_upload is False
    assert "rights_metadata" in {check.name for check in report.blocking_failures}


def test_human_voice_and_creative_review_unlock_premium_approval():
    report = CreativeQualityGateService().evaluate(
        narrative_report=_narrative_report(),
        visual_intents=_intents(),
        subtitle_cues=_cues(),
        source_assets=_assets(),
        inspection=_inspection(),
        quality_signals=_signals(),
        fact_check_passed=True,
        caption_ux_passed=True,
        visual_relevance_passed=True,
        sound_design_mode="licensed_music",
        human_creative_approval=True,
        voice_naturalness_score=4,
    )

    assert report.premium_approved is True


def test_failed_retention_contract_blocks_an_otherwise_strong_video():
    report = CreativeQualityGateService().evaluate(
        narrative_report=_narrative_report(),
        visual_intents=_intents(),
        subtitle_cues=_cues(),
        source_assets=_assets(),
        inspection=_inspection(),
        quality_signals=_signals(),
        fact_check_passed=True,
        caption_ux_passed=True,
        visual_relevance_passed=True,
        sound_design_mode="licensed_music",
        retention_plan=_retention_plan(passed=False),
    )

    assert report.ready_to_upload is False
    assert "retention_contract" in {
        check.name for check in report.blocking_failures
    }


def test_low_resolution_source_blocks_an_otherwise_strong_video():
    assets = _assets()
    assets[2] = MediaAsset(
        **{**assets[2].__dict__, "width": 360, "height": 640}
    )
    report = CreativeQualityGateService().evaluate(
        narrative_report=_narrative_report(),
        visual_intents=_intents(),
        subtitle_cues=_cues(),
        source_assets=assets,
        inspection=_inspection(),
        quality_signals=_signals(),
        fact_check_passed=True,
        caption_ux_passed=True,
        visual_relevance_passed=True,
        sound_design_mode="licensed_music",
        retention_plan=_retention_plan(),
    )

    assert report.ready_to_upload is False
    assert "source_resolution" in {
        check.name for check in report.blocking_failures
    }


def test_voice_profile_pause_budget_blocks_artificial_gap():
    direction = VoiceDirection(
        profile="energy",
        speed=1.07,
        stability=0.32,
        style=0.55,
        maximum_pause_ms=450,
        hook_delivery="urgent_but_controlled",
        explanation_delivery="fast_clear_and_precise",
        payoff_delivery="confident_short_landing",
    )
    report = CreativeQualityGateService().evaluate(
        narrative_report=_narrative_report(),
        visual_intents=_intents(),
        subtitle_cues=_cues(),
        source_assets=_assets(),
        inspection=_inspection(),
        quality_signals=replace(_signals(), maximum_silence_seconds=0.50),
        fact_check_passed=True,
        caption_ux_passed=True,
        visual_relevance_passed=True,
        sound_design_mode="licensed_music",
        retention_plan=_retention_plan(),
        voice_direction=direction,
    )

    assert report.ready_to_upload is False
    assert "narration_pause_budget" in {
        check.name for check in report.blocking_failures
    }
