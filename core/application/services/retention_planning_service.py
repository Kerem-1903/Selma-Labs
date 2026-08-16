"""Build a deterministic, source-grounded retention plan before paid stages."""
from __future__ import annotations

import math
from dataclasses import replace

from core.application.services.hook_variant_scoring_service import (
    HookVariantScoringService,
)
from core.domain.entities.script import Script
from core.domain.exceptions import NarrativeQualityError
from core.domain.value_objects.narrative_contract import NarrativeBeat
from core.domain.value_objects.retention_plan import (
    PatternInterrupt,
    RetentionPlan,
    RetentionSecond,
)
from core.domain.value_objects.youtube_performance import PerformanceGuidance


_ROLE_PURPOSES = {
    "hook": "state_the_promise_and_open_curiosity",
    "context": "give_only_the_context_needed_for_the_answer",
    "evidence": "add_new_evidence_or_show_the_mechanism",
    "payoff": "resolve_the_opening_promise",
}
_VISUAL_CHANGES = {
    "hook": "immediate_hard_cut",
    "context": "subject_establishing_visual",
    "evidence": "explanatory_visual_change",
    "payoff": "payoff_landing_or_mascot_reaction",
}
_INTERRUPT_CYCLE = (
    ("mascot_reaction", "renew_attention_without_changing_the_claim", "surprise"),
    ("diagram", "make_the_current_mechanism_visible", "write-board"),
    ("comparison", "contrast_the_before_and_after_states", "point-right"),
    ("timeline", "reorient_the_viewer_in_the_sequence", "think"),
    ("counter", "turn_a_list_or_scale_into_visible_progress", "speak"),
    ("spatial_reset", "change_camera_scale_or_screen_layout", "approach"),
)


class RetentionPlanningService:
    """Create three hook options and a second-resolved opening plan."""

    def __init__(self, hook_scoring: HookVariantScoringService | None = None) -> None:
        self._hook_scoring = hook_scoring or HookVariantScoringService()

    def build(
        self,
        script: Script,
        *,
        language: str = "und",
        performance_guidance: PerformanceGuidance | None = None,
    ) -> RetentionPlan:
        if len(script.narrative_beats) < 3:
            raise NarrativeQualityError(
                "Retention planning requires validated hook, evidence, and payoff beats."
            )

        hook_candidates = self._hook_candidates(script, language)
        experiment = self._hook_scoring.prepare_experiment(
            topic=script.topic,
            variants=hook_candidates,
            control_index=0,
        )
        if (
            performance_guidance is not None
            and performance_guidance.sample_size >= 10
            and performance_guidance.preferred_hook_type
        ):
            preferred = next(
                (
                    variant
                    for variant in experiment.ranked_variants
                    if variant.hook_type == performance_guidance.preferred_hook_type
                    and variant.score >= self._hook_scoring.minimum_publishable_score
                ),
                None,
            )
            if preferred is not None:
                experiment = replace(experiment, selected=preferred)
        opening_seconds = min(30, script.target_duration_seconds)
        second_plan = self._build_second_plan(
            script.narrative_beats,
            opening_seconds=opening_seconds,
            total_duration_seconds=script.target_duration_seconds,
        )
        pattern_interrupts = self._build_pattern_interrupts(
            script.target_duration_seconds,
            interval_seconds=(
                performance_guidance.recommended_pattern_interval_seconds
                if performance_guidance is not None
                and performance_guidance.sample_size >= 10
                else 25
            ),
        )
        issues = self._validate_plan(
            hook_count=len(experiment.ranked_variants),
            second_plan=second_plan,
            opening_seconds=opening_seconds,
            pattern_interrupts=pattern_interrupts,
            total_duration_seconds=script.target_duration_seconds,
        )
        plan = RetentionPlan(
            content_format="short" if script.target_duration_seconds <= 60 else "long",
            target_duration_seconds=script.target_duration_seconds,
            hook_experiment=experiment,
            production_hook=script.narrative_beats[0].text,
            first_30_seconds=second_plan,
            pattern_interrupts=pattern_interrupts,
            comment_question=(
                performance_guidance.successful_comment_question
                if performance_guidance is not None
                and performance_guidance.sample_size >= 10
                and performance_guidance.successful_comment_question
                else self._comment_question(script.topic, language)
            ),
            passed=not issues,
            performance_guidance=performance_guidance,
            issues=issues,
        )
        if not plan.passed:
            raise NarrativeQualityError(
                "Retention contract failed: " + "; ".join(plan.issues)
            )
        return plan

    @staticmethod
    def _hook_candidates(script: Script, language: str) -> tuple[str, str, str]:
        beats = script.narrative_beats
        topic = " ".join(script.topic.split()).rstrip(".!?")
        normalized_language = language.strip().lower()
        topic_question = (
            f"{topic}?"
            if "?" in script.topic
            else (
                f"{topic} gerçekte nasıl çalışıyor?"
                if normalized_language.startswith("tr")
                else f"How does {topic} actually work?"
            )
        )
        candidates: list[str] = []
        for text in (beats[0].text, topic_question, beats[-1].text, *(b.text for b in beats[1:-1])):
            cleaned = " ".join(text.split())
            if cleaned and cleaned not in candidates:
                candidates.append(cleaned)
            if len(candidates) == 3:
                break
        if len(candidates) != 3:
            raise NarrativeQualityError(
                "Retention planning could not derive three distinct source-grounded hooks."
            )
        return candidates[0], candidates[1], candidates[2]

    @staticmethod
    def _build_second_plan(
        beats: tuple[NarrativeBeat, ...],
        *,
        opening_seconds: int,
        total_duration_seconds: int,
    ) -> tuple[RetentionSecond, ...]:
        word_counts = [max(1, len(beat.text.split())) for beat in beats]
        total_words = sum(word_counts)
        beat_end_seconds: list[int] = []
        cumulative_words = 0
        for word_count in word_counts:
            cumulative_words += word_count
            beat_end_seconds.append(
                max(1, math.ceil(cumulative_words / total_words * total_duration_seconds))
            )

        result: list[RetentionSecond] = []
        beat_index = 0
        for second in range(opening_seconds):
            while (
                beat_index < len(beats) - 1
                and second >= beat_end_seconds[beat_index]
            ):
                beat_index += 1
            beat = beats[beat_index]
            result.append(
                RetentionSecond(
                    second=second,
                    beat_index=beat.index,
                    narrative_role=beat.role,
                    purpose=_ROLE_PURPOSES.get(beat.role, "advance_the_story"),
                    visual_change=_VISUAL_CHANGES.get(
                        beat.role, "purposeful_visual_change"
                    ),
                )
            )
        return tuple(result)

    @staticmethod
    def _build_pattern_interrupts(
        total_duration_seconds: int,
        *,
        interval_seconds: int = 25,
    ) -> tuple[PatternInterrupt, ...]:
        if total_duration_seconds <= 30:
            return ()
        interrupts: list[PatternInterrupt] = []
        bounded_interval = min(30, max(20, interval_seconds))
        for index, timestamp in enumerate(
            range(bounded_interval, total_duration_seconds, bounded_interval)
        ):
            change_type, purpose, mascot_action = _INTERRUPT_CYCLE[
                index % len(_INTERRUPT_CYCLE)
            ]
            interrupts.append(
                PatternInterrupt(
                    timestamp_seconds=timestamp,
                    change_type=change_type,
                    purpose=purpose,
                    mascot_action=mascot_action,
                )
            )
        return tuple(interrupts)

    @staticmethod
    def _validate_plan(
        *,
        hook_count: int,
        second_plan: tuple[RetentionSecond, ...],
        opening_seconds: int,
        pattern_interrupts: tuple[PatternInterrupt, ...],
        total_duration_seconds: int,
    ) -> tuple[str, ...]:
        issues: list[str] = []
        if hook_count != 3:
            issues.append("exactly_three_hook_variants_required")
        if [item.second for item in second_plan] != list(range(opening_seconds)):
            issues.append("first_30_seconds_not_fully_assigned")
        if total_duration_seconds > 30:
            timestamps = [0, *(item.timestamp_seconds for item in pattern_interrupts)]
            if not pattern_interrupts or any(
                right - left > 30 for left, right in zip(timestamps, timestamps[1:])
            ):
                issues.append("pattern_interrupt_gap_exceeds_30_seconds")
        return tuple(issues)

    @staticmethod
    def _comment_question(topic: str, language: str) -> str:
        if language.strip().lower().startswith("tr"):
            return f"{topic.rstrip('?! .')} konusunda seni en çok şaşırtan neydi?"
        return f"What surprised you most about {topic.rstrip('?! .')}?"
