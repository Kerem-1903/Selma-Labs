from __future__ import annotations

from dataclasses import replace

from core.application.services.visual_edit_planning_service import (
    VisualEditPlanningService,
)
from core.application.services.visual_quality_gate_service import (
    VisualQualityGateService,
)
from core.domain.entities.media_asset import MediaAsset
from core.domain.value_objects.media_quality_signals import MediaQualitySignals
from core.domain.value_objects.visual_edit_plan import VisualEditPlan
from core.domain.value_objects.visual_intent import VisualIntent
from core.domain.value_objects.visual_quality_report import VisualQualityReport


def _intents() -> list[VisualIntent]:
    specs = [
        (0, 1_200, "hook", "establish_question", False),
        (1_200, 3_200, "setup", "establish_subject", False),
        (3_200, 5_400, "development", "locate_part", False),
        (5_400, 7_600, "development", "demonstrate_mechanism", True),
        (7_600, 9_800, "development", "compare_states", True),
        (9_800, 12_000, "payoff", "deliver_payoff", False),
    ]
    return [
        VisualIntent(
            primary_keyword=f"science subject {index}",
            mood="curious",
            motion_type="steady",
            start_ms=start,
            end_ms=end,
            narrative_role=role,
            narration_text=f"Narration target {index}",
            visual_job=job,
            explanation_mode="hybrid" if explanatory else "stock",
            overlay_labels=(f"LABEL {index}",) if explanatory else (),
            explanatory_required=explanatory,
        )
        for index, (start, end, role, job, explanatory) in enumerate(specs)
    ]


def _assets(count: int) -> list[MediaAsset]:
    return [
        MediaAsset(
            id=f"pexels:{index}",
            provider="pexels",
            provider_asset_id=str(index),
            original_url=f"https://www.pexels.com/video/{index}",
            width=1080,
            height=1920,
            attribution=f"Creator {index} / Pexels",
            license="Pexels License",
        )
        for index in range(count)
    ]


def _signals(*, cuts: int = 5, stasis: float = 2.3) -> MediaQualitySignals:
    return MediaQualitySignals(
        opening_black_seconds=0.0,
        total_black_seconds=0.0,
        maximum_freeze_seconds=0.2,
        maximum_silence_seconds=0.3,
        integrated_lufs=-14.0,
        true_peak_dbfs=-1.5,
        scene_change_timestamps_seconds=tuple(
            1.2 + index * 2.2 for index in range(cuts)
        ),
        maximum_visual_stasis_seconds=stasis,
        average_shot_duration_seconds=2.0,
    )


def test_visual_edit_plan_builds_restrained_retention_grammar_and_roundtrips():
    adjusted, plan = VisualEditPlanningService().plan(_intents())

    assert plan.format_name == "shorts"
    assert plan.beats[0].purpose == "promise"
    assert plan.beats[0].pattern_interrupt == "hook_burst"
    assert all(
        left.shot_type != right.shot_type
        for left, right in zip(plan.beats, plan.beats[1:])
    )
    assert sum(beat.transition != "hard" for beat in plan.beats) <= 2
    assert adjusted[3].motion_type == "steady"
    assert VisualEditPlan.from_dict(plan.to_dict()) == plan


def test_visual_quality_gate_approves_objective_nine_of_ten_and_keeps_taste_separate():
    adjusted, plan = VisualEditPlanningService().plan(_intents())
    service = VisualQualityGateService()

    report = service.evaluate(
        plan=plan,
        visual_intents=adjusted,
        source_assets=_assets(len(plan.beats)),
        asset_usages=(),
        quality_signals=_signals(),
    )

    assert report.passed is True
    assert report.automatic_score == 90
    assert report.score == 90
    assert report.score_out_of_ten == 9.0
    assert report.to_dict()["studio_approved"] is False
    assert VisualQualityReport.from_dict(report.to_dict()) == report

    reviewed = service.evaluate(
        plan=plan,
        visual_intents=adjusted,
        source_assets=_assets(len(plan.beats)),
        asset_usages=(),
        quality_signals=_signals(),
        human_taste_score=9,
    )
    assert reviewed.score == 99
    assert reviewed.to_dict()["studio_approved"] is True


def test_visual_quality_gate_blocks_a_render_that_did_not_execute_the_plan():
    adjusted, plan = VisualEditPlanningService().plan(_intents())
    report = VisualQualityGateService().evaluate(
        plan=plan,
        visual_intents=adjusted,
        source_assets=_assets(len(plan.beats)),
        asset_usages=(),
        quality_signals=_signals(cuts=0, stasis=12.0),
    )

    assert report.passed is False
    assert "rendered_visual_change" in report.to_dict()["blocking_failures"]


def test_visual_quality_gate_blocks_adjacent_source_repetition():
    adjusted, plan = VisualEditPlanningService().plan(_intents())
    assets = _assets(len(plan.beats))
    assets[2] = replace(assets[2], id=assets[1].id)
    report = VisualQualityGateService().evaluate(
        plan=plan,
        visual_intents=adjusted,
        source_assets=assets,
        asset_usages=(),
        quality_signals=_signals(),
    )

    assert report.passed is False
    assert "perceptual_source_diversity" in report.to_dict()["blocking_failures"]
