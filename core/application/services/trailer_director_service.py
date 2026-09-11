"""Deterministic trailer director over an existing Episode Director plan."""

from __future__ import annotations

from collections.abc import Sequence

from core.domain.exceptions import PreProductionValidationError
from core.domain.value_objects.episode_director_plan import EpisodeDirectorPlan
from core.domain.value_objects.trailer_brief import TrailerBrief
from core.domain.value_objects.trailer_plan import TrailerPlan, TrailerShot
from core.domain.value_objects.trailer_timeline import TrailerTimeline


class TrailerDirectorService:
    """Build a reviewable trailer draft without inventing untraceable story beats."""

    _BEAT_PURPOSES = {
        "normal-world": "Establish normal life and the first perceptual disturbance.",
        "perceptual-collapse": "Expose the FHD-80/LIMEN mystery without revealing its cause.",
        "action-threat": "Escalate the pursuit and make the LIMEN threat legible.",
        "silence-hook": "Land the emotional fracture, then end on the title hook.",
    }

    def plan(self, episode: EpisodeDirectorPlan, brief: TrailerBrief) -> TrailerPlan:
        if not episode.scenes:
            raise PreProductionValidationError("Trailer requires a source episode with scenes.")
        timeline = TrailerTimeline.from_brief(brief)
        source_shots = [shot for scene in episode.scenes for shot in scene.shots]
        scene_locations = {scene.scene_id: scene.location_id for scene in episode.scenes}
        if not source_shots:
            raise PreProductionValidationError("Trailer requires source episode shots.")
        lengths = (912, 1152, 1560, 696)
        shots: list[TrailerShot] = []
        cursor = 0
        for beat, length in zip(timeline.beats, lengths):
            candidates = self._candidates(source_shots, beat.beat_id)
            beat_shots = self._allocate(candidates, length, beat.beat_id)
            local_cursor = beat.start_frame
            for index, source in enumerate(beat_shots, start=1):
                duration = self._shot_duration(length, len(beat_shots), index)
                shot_id = f"{brief.trailer_id}-{beat.beat_id}-{index:02d}"
                shots.append(
                    TrailerShot(
                        shot_id=shot_id,
                        beat_id=beat.beat_id,
                        source_scene_id=source.scene_id,
                        source_shot_id=source.shot_id,
                        purpose=self._BEAT_PURPOSES[beat.beat_id],
                        start_frame=local_cursor,
                        end_frame=local_cursor + duration,
                        character_id=source.character_id,
                        pose_id=source.character_pose_id,
                        location_id=scene_locations.get(source.scene_id, source.scene_id),
                        dialogue=source.dialogue if beat.beat_id != "action-threat" else "",
                        system_voice=("MNEMOS" if beat.beat_id == "perceptual-collapse" and index == 1 else ""),
                        music_cue=self._music_cue(beat.beat_id),
                        sfx_cue=("rain, monitor-beep" if beat.beat_id == "normal-world" else ""),
                        spoiler_level="ALLOWED_REVEAL" if beat.beat_id == "perceptual-collapse" else "SAFE",
                        production_method="STORYBOARD",
                    )
                )
                local_cursor += duration
            cursor = beat.end_frame
        if cursor != timeline.duration_frames:
            raise PreProductionValidationError("Trailer director did not cover the exact frame budget.")
        return TrailerPlan(
            schema_version=1,
            brief=brief.to_dict(),
            timeline=timeline,
            shots=tuple(shots),
            source_episode_id=episode.episode_id,
            warnings=("Draft uses deterministic source-shot selection; human editorial review is required.",),
        )

    @staticmethod
    def _candidates(source_shots: Sequence, beat_id: str) -> list:
        if beat_id == "normal-world":
            preferred = [shot for shot in source_shots if shot.story_beat in {"setup", "context"}]
        elif beat_id == "perceptual-collapse":
            preferred = [shot for shot in source_shots if shot.story_beat in {"reveal", "reaction"}]
        elif beat_id == "action-threat":
            preferred = [shot for shot in source_shots if shot.story_beat == "conflict" or shot.character_action]
        else:
            preferred = [shot for shot in source_shots if shot.story_beat in {"reaction", "payoff"} or shot.dialogue]
        return preferred or list(source_shots)

    @staticmethod
    def _allocate(candidates: Sequence, length: int, beat_id: str) -> tuple:
        count = {"normal-world": 10, "perceptual-collapse": 12, "action-threat": 22, "silence-hook": 10}[beat_id]
        return tuple(candidates[index % len(candidates)] for index in range(count))

    @staticmethod
    def _shot_duration(length: int, count: int, index: int) -> int:
        base, remainder = divmod(length, count)
        return base + (1 if index <= remainder else 0)

    @staticmethod
    def _music_cue(beat_id: str) -> str:
        return {
            "normal-world": "rain-and-three-note-motif",
            "perceptual-collapse": "low-electronic-pulse",
            "action-threat": "strings-ostinato-heavy-percussion",
            "silence-hook": "music-cut-then-title-strike",
        }[beat_id]
