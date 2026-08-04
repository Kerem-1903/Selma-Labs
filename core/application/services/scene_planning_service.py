"""
ScenePlanningService — application-layer orchestration for scene planning.

Same division of responsibility as ScriptService/VoiceService/
VideoSearchService: the provider adapter's job is "read narration text and
produce a semantic breakdown into scenes," this service's job is "decide
whether that breakdown is usable, and compute each scene's timing." It
depends only on ScenePlanningPort — never on a concrete provider.

Timing is deliberately NOT asked of the provider. An LLM has no reliable
sense of elapsed seconds; VoiceTrack.duration_seconds is a real, measured
value (VoiceService already validates it's > 0 before a VoiceTrack ever
exists). So this service estimates each scene's start/end time by
allocating VoiceTrack.duration_seconds proportionally to each scene's share
of the total narration word count — "estimating scene timing from
narration," exactly as the sprint brief asks for, using the one number in
this pipeline that IS trustworthy (measured audio duration) rather than a
number the provider would otherwise have to guess. This also means Scene
Planning works whether or not VoiceTrack.segments (per-word timing) is
populated — today no voice provider in this codebase populates it, so
relying on it would make this service unusable right now.

Scope, per Sprint 4's brief: this service only produces a plan. It does not
search Pexels, select assets, or rank anything — that's VideoSearchService
and later sprints, composed on top of this service's output without
changing its public contract.
"""
from __future__ import annotations

import logging

from core.domain.entities.scene_plan import ScenePlan
from core.domain.entities.script import Script
from core.domain.entities.voice_track import VoiceTrack
from core.domain.exceptions import ScenePlanningError
from core.domain.ports.scene_planning_port import ScenePlanningPort
from core.domain.value_objects.scene import Scene

logger = logging.getLogger("selma.scene_planning_service")


class ScenePlanningService:
    """Plans visual scenes for a Script/VoiceTrack pair via an injected
    provider."""

    def __init__(self, provider: ScenePlanningPort) -> None:
        self._provider = provider

    async def plan(self, script: Script, voice_track: VoiceTrack) -> ScenePlan:
        """Produce a validated, timed ScenePlan for ``script``/``voice_track``.

        Args:
            script: The Script whose narration text will be segmented.
            voice_track: The narrated VoiceTrack for ``script`` — its
                ``duration_seconds`` is the authoritative total duration
                used to compute each scene's timing.

        Raises:
            ScenePlanningError: Input was invalid (no narration text, or
                an invalid voice track duration), or the provider's output
                failed validation (empty scene list, or a scene missing
                narration/search_keywords).
            ProviderError (and subclasses): Propagated unchanged from the
                adapter for auth/timeout/connection/quota failures —
                callers need the typed subclass to decide whether to
                retry.
        """
        narration_text = (script.full_text or "").strip()
        if not narration_text:
            raise ScenePlanningError("Script has no narration text to plan scenes for.")

        if voice_track.duration_seconds <= 0:
            raise ScenePlanningError(
                f"VoiceTrack has an invalid duration_seconds: "
                f"{voice_track.duration_seconds}."
            )

        logger.info(
            "scene_planning_started",
            extra={"script_id": script.id, "voice_track_id": voice_track.audio_id},
        )

        raw_scenes = await self._provider.plan_scenes(narration_text=narration_text)

        self._validate_raw_scenes(raw_scenes)

        timed_scenes = self._assign_timing(raw_scenes, voice_track.duration_seconds)

        scene_plan = ScenePlan.create(
            script_id=script.id,
            voice_track_id=voice_track.audio_id,
            total_duration_seconds=voice_track.duration_seconds,
            provider_used=self._provider.provider_identity,
            scenes=timed_scenes,
        )

        logger.info(
            "scene_planning_completed",
            extra={"script_id": script.id, "scene_count": len(timed_scenes)},
        )
        return scene_plan

    @staticmethod
    def _validate_raw_scenes(scenes: list[Scene]) -> None:
        if not scenes:
            raise ScenePlanningError("Provider returned no scenes for this narration.")

        for position, scene in enumerate(scenes):
            if not scene.narration or not scene.narration.strip():
                raise ScenePlanningError(
                    f"Scene at position {position} is missing narration text."
                )
            if not scene.search_keywords:
                raise ScenePlanningError(
                    f"Scene at position {position} has no search_keywords — "
                    "every scene must be searchable by a later Asset Matching step."
                )

    @staticmethod
    def _assign_timing(scenes: list[Scene], total_duration_seconds: float) -> list[Scene]:
        # Proportional allocation by word count. Simple on purpose: this
        # service has no acoustic information (pauses, pacing) to do
        # better than "more words -> more seconds," and that's a
        # reasonable approximation until per-word timing (VoiceTrack.
        # segments) is populated by a future voice provider — see this
        # module's docstring and the README's Future Enhancements section.
        word_counts = [max(len(scene.narration.split()), 1) for scene in scenes]
        total_words = sum(word_counts)
        last_position = len(scenes) - 1

        timed_scenes = []
        cursor = 0.0
        for position, (scene, words) in enumerate(zip(scenes, word_counts)):
            start_time = cursor
            if position == last_position:
                # Snap the final scene's end exactly to the measured total
                # duration, rather than letting proportional rounding drift
                # short or long of it across many scenes.
                end_time = total_duration_seconds
            else:
                end_time = start_time + (total_duration_seconds * words / total_words)

            timed_scenes.append(
                scene.finalize(
                    index=position,
                    start_time=round(start_time, 2),
                    end_time=round(end_time, 2),
                )
            )
            cursor = end_time

        return timed_scenes
