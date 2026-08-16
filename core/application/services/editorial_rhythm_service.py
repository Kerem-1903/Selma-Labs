"""Fail-closed rhythm checks for a time-coded semantic storyboard."""
from __future__ import annotations

from collections.abc import Sequence

from core.domain.exceptions import EditorialRhythmError
from core.domain.value_objects.asset_diversity import AssetUsage, EditorialRhythmReport
from core.domain.value_objects.subtitle_cue import SubtitleCue
from core.domain.value_objects.visual_intent import VisualIntent


class EditorialRhythmService:
    """Validate hard-cut timing, information changes, and low-motion holds."""

    def __init__(self, *, alignment_tolerance_ms: int = 120, maximum_low_motion_ms: int = 2_800) -> None:
        if alignment_tolerance_ms < 0 or maximum_low_motion_ms <= 0:
            raise ValueError("Editorial rhythm thresholds are invalid.")
        self._alignment_tolerance_ms = alignment_tolerance_ms
        self._maximum_low_motion_ms = maximum_low_motion_ms

    def validate(
        self,
        intents: Sequence[VisualIntent],
        cues: Sequence[SubtitleCue],
        usages: Sequence[AssetUsage],
    ) -> EditorialRhythmReport:
        if not intents or len(intents) != len(usages):
            raise EditorialRhythmError(
                "Editorial rhythm requires one selected usage per visual intent."
            )
        cue_boundaries = {
            boundary
            for cue in cues
            for boundary in (
                cue.start_ms,
                cue.end_ms,
                *(word.end_ms for word in cue.words),
            )
        }
        beat_aligned = all(
            any(abs(intent.end_ms - boundary) <= self._alignment_tolerance_ms for boundary in cue_boundaries)
            for intent in intents[:-1]
        )
        continuous = all(
            current.end_ms == following.start_ms
            for current, following in zip(intents, intents[1:])
        )
        # The storyboard may use absolute source-audio timestamps. The render
        # contract starts its first selected segment immediately with a hard
        # cut, so a positive first segment is the portable invariant here.
        immediate_opening = intents[0].duration_ms > 0
        unresolved: list[int] = []
        exceptions: list[int] = []
        for index, (intent, usage) in enumerate(zip(intents, usages)):
            long_low_motion = (
                intent.duration_ms > self._maximum_low_motion_ms
                and usage.motion_energy < 0.35
            )
            if not long_low_motion:
                continue
            if intent.explanatory_required and intent.overlay_labels:
                exceptions.append(index)
            else:
                unresolved.append(index)
        semantic_transitions = sum(
            current.visual_job != following.visual_job
            or current.narrative_role != following.narrative_role
            for current, following in zip(intents, intents[1:])
        )
        report = EditorialRhythmReport(
            beat_aligned=beat_aligned and continuous,
            immediate_opening=immediate_opening,
            semantic_transitions=semantic_transitions,
            explanatory_interrupts=sum(intent.explanatory_required for intent in intents),
            low_motion_exceptions=tuple(exceptions),
            unresolved_low_motion=tuple(unresolved),
            loop_closure_ready=intents[-1].narrative_role == "payoff",
        )
        if not report.passed:
            raise EditorialRhythmError(
                "Editorial rhythm gate failed: "
                f"beat_aligned={report.beat_aligned}, "
                f"immediate_opening={report.immediate_opening}, "
                f"unresolved_low_motion={list(report.unresolved_low_motion)}."
            )
        return report
