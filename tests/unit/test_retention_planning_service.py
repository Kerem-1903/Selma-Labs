from __future__ import annotations

import pytest

from core.application.services.narrative_quality_service import NarrativeQualityService
from core.application.services.retention_planning_service import RetentionPlanningService
from core.domain.entities.script import Script
from core.domain.exceptions import NarrativeQualityError
from core.domain.value_objects.retention_plan import RetentionPlan
from core.domain.value_objects.youtube_performance import PerformanceGuidance


def _validated_script(*, duration: int = 24) -> Script:
    script = Script.create(
        topic="Ahtapotların neden üç kalbi var?",
        full_text=(
            "Ahtapotun üç kalbi olması tesadüf değil. "
            "Çünkü iki kalp kanı solungaçlara gönderirken üçüncü kalp vücudu besliyor. "
            "Bu düzen, oksijenin bütün vücuda taşınmasını sürdürüyor."
        ),
        target_duration_seconds=duration,
        provider_used="test",
    )
    return NarrativeQualityService().validate(script, language="tr")[0]


def test_short_plan_has_three_hooks_and_every_opening_second_has_a_job():
    plan = RetentionPlanningService().build(_validated_script(), language="tr")

    assert plan.passed is True
    assert plan.content_format == "short"
    assert len(plan.hook_experiment.ranked_variants) == 3
    assert plan.production_hook == "Ahtapotun üç kalbi olması tesadüf değil."
    assert [item.second for item in plan.first_30_seconds] == list(range(24))
    assert all(item.purpose and item.visual_change for item in plan.first_30_seconds)
    assert plan.pattern_interrupts == ()
    assert plan.comment_question.endswith("şaşırtan neydi?")
    assert RetentionPlan.from_dict(plan.to_dict()) == plan


def test_long_plan_schedules_a_purposeful_change_at_least_every_30_seconds():
    plan = RetentionPlanningService().build(
        _validated_script(duration=125),
        language="tr",
    )

    assert plan.content_format == "long"
    assert len(plan.first_30_seconds) == 30
    assert [item.timestamp_seconds for item in plan.pattern_interrupts] == [
        25,
        50,
        75,
        100,
    ]
    assert all(item.mascot_action for item in plan.pattern_interrupts)


def test_unvalidated_script_cannot_reach_retention_planning():
    script = Script.create(
        topic="Ahtapotlar",
        full_text="Ahtapotlar ilginçtir.",
        target_duration_seconds=24,
        provider_used="test",
    )

    with pytest.raises(NarrativeQualityError, match="validated"):
        RetentionPlanningService().build(script, language="tr")


def test_channel_guidance_changes_long_form_interrupts_and_comment_prompt():
    guidance = PerformanceGuidance(
        content_format="long_form",
        sample_size=12,
        preferred_hook_type="question",
        recommended_pattern_interval_seconds=20,
        common_drop_timestamp_seconds=22.0,
        successful_comment_question="Sence hangi açıklama daha ikna ediciydi?",
        average_first_3_second_retention=81.0,
        average_first_30_second_retention=63.0,
    )

    plan = RetentionPlanningService().build(
        _validated_script(duration=125),
        language="tr",
        performance_guidance=guidance,
    )

    assert plan.hook_experiment.selected.hook_type == "question"
    assert [item.timestamp_seconds for item in plan.pattern_interrupts] == [
        20,
        40,
        60,
        80,
        100,
        120,
    ]
    assert plan.comment_question == "Sence hangi açıklama daha ikna ediciydi?"
    assert RetentionPlan.from_dict(plan.to_dict()).performance_guidance == guidance
