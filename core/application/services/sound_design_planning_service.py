"""Turn editorial intent into sparse, semantic and rights-safe sound design."""
from __future__ import annotations

from collections.abc import Sequence

from core.domain.value_objects.sound_design_plan import (
    AudioCue,
    MusicAutomationPoint,
    SoundDesignPlan,
)
from core.domain.value_objects.visual_intent import VisualIntent


class SoundDesignPlanningService:
    """Creates an explainable plan; render providers only execute it."""

    def __init__(self, *, minimum_cue_gap_ms: int = 650) -> None:
        if minimum_cue_gap_ms < 400:
            raise ValueError("minimum_cue_gap_ms must be at least 400.")
        self._minimum_gap_ms = minimum_cue_gap_ms

    def plan(
        self,
        visual_intents: Sequence[VisualIntent],
        *,
        has_music: bool,
    ) -> SoundDesignPlan:
        if not visual_intents:
            raise ValueError("Sound design requires at least one visual intent.")
        duration_ms = max(intent.end_ms for intent in visual_intents)
        if duration_ms <= 0:
            raise ValueError("Sound design requires time-coded visual intents.")

        candidates: list[AudioCue] = [
            AudioCue(0, "hook_impact", min(420, duration_ms), -18.0, "Mark the opening promise."),
        ]
        for intent in visual_intents[1:]:
            kind = self._cue_kind(intent)
            if kind is None:
                continue
            remaining = duration_ms - intent.start_ms
            if remaining < 80:
                continue
            candidates.append(
                AudioCue(
                    timestamp_ms=intent.start_ms,
                    kind=kind,
                    duration_ms=min(self._duration_for(kind), remaining),
                    gain_db=self._gain_for(kind),
                    rationale=self._rationale_for(kind, intent),
                )
            )
        cues = self._space_cues(candidates)
        if "payoff" not in {cue.kind for cue in cues} and duration_ms >= 2_000:
            payoff_at = max(0, duration_ms - 550)
            payoff = AudioCue(
                payoff_at,
                "payoff",
                min(500, duration_ms - payoff_at),
                -21.0,
                "Give the final answer a restrained sonic full stop.",
            )
            cues = self._space_cues([*cues, payoff])

        music_points: tuple[MusicAutomationPoint, ...] = ()
        if has_music:
            points = [MusicAutomationPoint(0, -2.0, "Leave headroom for the hook.")]
            for intent in visual_intents[1:]:
                if intent.narrative_role in {"reveal", "payoff"} or intent.visual_job == "deliver_payoff":
                    points.append(
                        MusicAutomationPoint(intent.start_ms, 0.0, "Lift the reveal without masking speech.")
                    )
                elif intent.narrative_role in {"context", "explanation", "development"}:
                    points.append(
                        MusicAutomationPoint(intent.start_ms, -3.0, "Create space for dense explanation.")
                    )
            fade_at = max(0, duration_ms - 1_200)
            points.append(MusicAutomationPoint(fade_at, -8.0, "Clear the final spoken line."))
            music_points = self._deduplicate_music_points(points, duration_ms)

        return SoundDesignPlan(
            duration_ms=duration_ms,
            ambience_profile=self._ambience_profile(visual_intents),
            cues=cues,
            music_automation=music_points,
            minimum_cue_gap_ms=self._minimum_gap_ms,
        )

    def _space_cues(self, candidates: Sequence[AudioCue]) -> tuple[AudioCue, ...]:
        priority = {"hook_impact": 6, "payoff": 5, "reveal": 4, "mechanism": 3, "warning": 2, "transition": 1}
        accepted: list[AudioCue] = []
        for cue in sorted(candidates, key=lambda item: (item.timestamp_ms, -priority[item.kind])):
            conflict = next(
                (existing for existing in accepted if abs(existing.timestamp_ms - cue.timestamp_ms) < self._minimum_gap_ms),
                None,
            )
            if conflict is None:
                accepted.append(cue)
            elif priority[cue.kind] > priority[conflict.kind]:
                accepted.remove(conflict)
                accepted.append(cue)
        return tuple(sorted(accepted, key=lambda item: item.timestamp_ms))

    @staticmethod
    def _cue_kind(intent: VisualIntent) -> str | None:
        role = intent.narrative_role
        job = intent.visual_job
        if role == "payoff" or job == "deliver_payoff":
            return "payoff"
        if role == "reveal" or job in {"reveal_answer", "show_consequence"}:
            return "reveal"
        if job in {"demonstrate_mechanism", "compare_scale", "explain_process"}:
            return "mechanism"
        if any(token in intent.narration_text.casefold() for token in ("danger", "risk", "tehlike", "uyarı")):
            return "warning"
        if intent.motion_type in {"whip", "push", "snap", "fast"}:
            return "transition"
        return None

    @staticmethod
    def _duration_for(kind: str) -> int:
        return {"transition": 260, "mechanism": 320, "reveal": 520, "payoff": 500, "warning": 440}.get(kind, 350)

    @staticmethod
    def _gain_for(kind: str) -> float:
        return {"transition": -26.0, "mechanism": -24.0, "reveal": -20.0, "payoff": -21.0, "warning": -23.0}.get(kind, -24.0)

    @staticmethod
    def _rationale_for(kind: str, intent: VisualIntent) -> str:
        return f"Support {intent.narrative_role}/{intent.visual_job} with a restrained {kind} cue."

    @staticmethod
    def _ambience_profile(intents: Sequence[VisualIntent]) -> str:
        corpus = " ".join(
            f"{intent.primary_keyword} {intent.mood} {intent.narration_text}"
            for intent in intents
        ).casefold()
        if any(token in corpus for token in ("space", "planet", "venus", "uzay", "gezegen")):
            return "space"
        if any(token in corpus for token in ("forest", "ocean", "animal", "doğa", "orman", "okyanus")):
            return "nature"
        if any(token in corpus for token in ("danger", "dark", "mystery", "tehlike", "karanlık", "gizem")):
            return "tension"
        return "laboratory"

    @staticmethod
    def _deduplicate_music_points(
        points: Sequence[MusicAutomationPoint],
        duration_ms: int,
    ) -> tuple[MusicAutomationPoint, ...]:
        by_timestamp: dict[int, MusicAutomationPoint] = {}
        for point in points:
            if point.timestamp_ms <= duration_ms:
                by_timestamp[point.timestamp_ms] = point
        return tuple(by_timestamp[key] for key in sorted(by_timestamp))
