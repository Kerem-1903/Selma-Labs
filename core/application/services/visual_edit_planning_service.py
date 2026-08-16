"""Turn semantic visual intents into a restrained retention-first edit grammar."""
from __future__ import annotations

import math
from dataclasses import replace
from typing import Sequence

from core.domain.value_objects.visual_edit_plan import VisualEditBeat, VisualEditPlan
from core.domain.value_objects.visual_intent import VisualIntent


class VisualEditPlanningService:
    """Plan purposeful variation without adding arbitrary effects."""

    _SHOT_CYCLE = (
        "macro-close-up",
        "wide-establishing",
        "detail-insert",
        "tracking-medium",
        "overhead-wide",
        "low-angle-medium",
    )

    def plan(
        self,
        intents: Sequence[VisualIntent],
    ) -> tuple[list[VisualIntent], VisualEditPlan]:
        if not intents:
            raise ValueError("Visual edit planning requires visual intents.")
        if any(intent.duration_ms <= 0 for intent in intents):
            raise ValueError("Visual edit planning requires positive beat durations.")
        if any(
            current.end_ms != following.start_ms
            for current, following in zip(intents, intents[1:])
        ):
            raise ValueError("Visual edit planning requires a continuous storyboard.")

        duration_ms = intents[-1].end_ms - intents[0].start_ms
        short_form = duration_ms <= 180_000
        maximum_hold_ms = 2_800 if short_form else 6_000
        interrupt_gap_ms = 6_500 if short_form else 25_000
        transition_budget = min(
            max(0, len(intents) - 1),
            math.ceil(max(0, len(intents) - 1) * 0.25),
        )

        adjusted: list[VisualIntent] = []
        beats: list[VisualEditBeat] = []
        previous_shot = ""
        motion_run = 0
        previous_motion = ""
        transitions_used = 0
        last_transition_index = -99
        last_interrupt_ms = intents[0].start_ms

        for index, intent in enumerate(intents):
            shot_type = self._shot_type(intent, index, previous_shot)
            motion_type = self._motion_type(intent, index)
            if motion_type == previous_motion:
                motion_run += 1
            else:
                motion_run = 1
            if motion_run >= 3:
                motion_type = "slow-motion" if motion_type == "fast-paced" else "fast-paced"
                motion_run = 1
            transition = "hard"
            candidate = self._transition_candidate(intent, index)
            if (
                candidate != "hard"
                and transitions_used < transition_budget
                and index - last_transition_index >= 3
            ):
                transition = candidate
                transitions_used += 1
                last_transition_index = index

            interrupt = self._pattern_interrupt(
                intent,
                index=index,
                since_ms=intent.start_ms - last_interrupt_ms,
                gap_ms=interrupt_gap_ms,
                is_final=index == len(intents) - 1,
            )
            if interrupt != "none":
                last_interrupt_ms = intent.start_ms

            purpose = self._purpose(intent)
            adjusted_intent = replace(
                intent,
                shot_type=shot_type,
                motion_type=motion_type,
            )
            adjusted.append(adjusted_intent)
            beats.append(
                VisualEditBeat(
                    index=index,
                    start_ms=intent.start_ms,
                    end_ms=intent.end_ms,
                    purpose=purpose,
                    shot_type=shot_type,
                    motion_type=motion_type,
                    transition=transition,
                    pattern_interrupt=interrupt,
                    explanation_mode=intent.explanation_mode,
                )
            )
            previous_shot = shot_type
            previous_motion = motion_type

        return adjusted, VisualEditPlan(
            beats=tuple(beats),
            format_name="shorts" if short_form else "long_form",
            maximum_visual_hold_ms=maximum_hold_ms,
            maximum_pattern_interrupt_gap_ms=interrupt_gap_ms,
            expected_cut_count=max(0, len(beats) - 1),
            non_hard_transition_budget=transition_budget,
        )

    @classmethod
    def _shot_type(cls, intent: VisualIntent, index: int, previous: str) -> str:
        preferred = {
            "establish_question": "macro-close-up",
            "establish_subject": "wide-establishing",
            "locate_part": "detail-insert",
            "demonstrate_mechanism": "macro-close-up",
            "compare_states": "overhead-wide",
            "show_consequence": "low-angle-medium",
            "deliver_payoff": "tracking-medium",
        }.get(intent.visual_job, intent.shot_type)
        if preferred != previous:
            return preferred
        for offset in range(len(cls._SHOT_CYCLE)):
            candidate = cls._SHOT_CYCLE[(index + offset) % len(cls._SHOT_CYCLE)]
            if candidate != previous:
                return candidate
        return preferred

    @staticmethod
    def _motion_type(intent: VisualIntent, index: int) -> str:
        if index == 0 or intent.narrative_role == "hook":
            return "fast-paced"
        if intent.visual_job == "demonstrate_mechanism":
            return "steady"
        if intent.visual_job == "compare_states":
            return "slow-motion"
        if intent.visual_job in {"locate_part", "show_consequence"}:
            return "fast-paced"
        if intent.explanatory_required:
            return "steady"
        if intent.narrative_role == "payoff":
            return "slow-motion"
        return intent.motion_type

    @staticmethod
    def _transition_candidate(intent: VisualIntent, index: int) -> str:
        if index == 0:
            return "hard"
        return {
            "locate_part": "push",
            "demonstrate_mechanism": "match_zoom",
            "compare_states": "mask_reveal",
            "show_consequence": "impact_flash",
            "deliver_payoff": "mask_reveal",
        }.get(intent.visual_job, "hard")

    @staticmethod
    def _pattern_interrupt(
        intent: VisualIntent,
        *,
        index: int,
        since_ms: int,
        gap_ms: int,
        is_final: bool,
    ) -> str:
        if index == 0:
            return "hook_burst"
        if intent.explanatory_required:
            return "diagram" if intent.explanation_mode == "diagram" else "callout"
        if is_final or intent.narrative_role == "payoff":
            return "payoff_card"
        if since_ms >= gap_ms:
            return "scale_or_layout_change"
        return "none"

    @staticmethod
    def _purpose(intent: VisualIntent) -> str:
        return {
            "hook": "promise",
            "setup": "orient",
            "development": "explain",
            "proof": "prove",
            "payoff": "reward",
        }.get(intent.narrative_role, intent.visual_job)
