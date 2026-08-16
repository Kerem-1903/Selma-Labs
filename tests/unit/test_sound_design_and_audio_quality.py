from __future__ import annotations

from core.application.services.audio_quality_gate_service import AudioQualityGateService
from core.application.services.sound_design_planning_service import SoundDesignPlanningService
from core.domain.value_objects.background_track import BackgroundTrack
from core.domain.value_objects.media_inspection import MediaInspection
from core.domain.value_objects.media_quality_signals import MediaQualitySignals
from core.domain.value_objects.sound_design_plan import SoundDesignPlan
from core.domain.value_objects.visual_intent import VisualIntent


def _intent(start: int, end: int, role: str, job: str, keyword: str = "space") -> VisualIntent:
    return VisualIntent(
        primary_keyword=keyword,
        mood="mystery",
        motion_type="steady",
        start_ms=start,
        end_ms=end,
        narrative_role=role,
        narration_text="A surprising mechanism is revealed.",
        visual_job=job,
    )


def _inspection() -> MediaInspection:
    return MediaInspection(
        format_names=("mp4",), duration_seconds=10.0, width=1080, height=1920,
        fps=30.0, video_codec="h264", pixel_format="yuv420p", audio_codec="aac",
        audio_sample_rate=48_000, audio_bitrate=320_000, file_size_bytes=1_000_000,
        color_primaries="bt709", color_transfer="bt709", color_space="bt709",
        color_range="tv", field_order="progressive", audio_channels=2,
    )


def test_sound_design_plan_is_semantic_sparse_and_roundtrips():
    plan = SoundDesignPlanningService().plan(
        [
            _intent(0, 1_000, "hook", "establish_question"),
            _intent(1_000, 4_000, "explanation", "demonstrate_mechanism"),
            _intent(4_000, 7_000, "reveal", "reveal_answer"),
            _intent(7_000, 10_000, "payoff", "deliver_payoff"),
        ],
        has_music=True,
    )

    assert plan.ambience_profile == "space"
    assert {"hook_impact", "mechanism", "reveal", "payoff"} <= plan.semantic_kinds
    assert len(plan.music_automation) >= 3
    assert SoundDesignPlan.from_dict(plan.to_dict()) == plan


def test_audio_quality_gate_approves_measured_studio_master_at_nine_of_ten():
    plan = SoundDesignPlanningService().plan(
        [
            _intent(0, 2_000, "hook", "establish_question"),
            _intent(2_000, 6_000, "explanation", "demonstrate_mechanism"),
            _intent(6_000, 10_000, "payoff", "deliver_payoff"),
        ],
        has_music=True,
    )
    track = BackgroundTrack(
        "music.mp3", "Original", "SELMA Labs", "Original commercial", ["space"],
        source_url="selma://original", sha256="a" * 64,
        evidence_reference="project master", commercial_use=True, youtube_allowed=True,
        attribution_required=False,
    )
    signals = MediaQualitySignals(
        0.0, 0.0, 0.2, 0.4, -14.0, -1.5,
        loudness_range_lu=5.0, adaptive_silence_threshold_db=-29.0,
    )

    report = AudioQualityGateService().evaluate(
        plan=plan, inspection=_inspection(), signals=signals, music_track=track,
    )

    assert report.passed is True
    assert report.score == 90
    assert report.score_out_of_ten == 9.0

    reviewed = AudioQualityGateService().evaluate(
        plan=plan, inspection=_inspection(), signals=signals, music_track=track,
        voice_naturalness_score=5,
    )
    assert reviewed.score == 100


def test_audio_quality_gate_blocks_clipped_master_even_with_high_total():
    plan = SoundDesignPlanningService().plan(
        [_intent(0, 3_000, "hook", "establish_question"), _intent(3_000, 10_000, "payoff", "deliver_payoff")],
        has_music=False,
    )
    signals = MediaQualitySignals(0.0, 0.0, 0.2, 0.4, -14.0, 0.0, clipping_detected=True)

    report = AudioQualityGateService().evaluate(
        plan=plan, inspection=_inspection(), signals=signals, music_track=None,
    )

    assert report.passed is False
    assert "true_peak_and_clipping" in [check.name for check in report.checks if check.blocking and not check.passed]
