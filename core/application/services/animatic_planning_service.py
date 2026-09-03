from __future__ import annotations

from core.domain.entities.animatic_project import AnimaticClip, AnimaticProject
from core.domain.entities.episode_production_plan import EpisodeProductionPlan
from core.domain.entities.shot_storyboard import ShotStoryboard
from core.domain.exceptions import AnimaticApprovalError
from core.domain.ports.storage_port import StoragePort


class AnimaticPlanningService:
    def __init__(self, storage: StoragePort) -> None:
        self._storage = storage

    async def build(
        self,
        *,
        plan: EpisodeProductionPlan,
        storyboards: dict[str, ShotStoryboard],
        dialogue_audio_keys: dict[str, str],
    ) -> AnimaticProject:
        clips = []
        start_frame = 0
        for directed in plan.shots:
            shot = directed.plan
            storyboard = storyboards.get(shot.id)
            if storyboard is None or len(storyboard.frames) != 1:
                raise AnimaticApprovalError(
                    f"Shot '{shot.id}' requires exactly one committed storyboard frame."
                )
            frame = storyboard.frames[0]
            if not await self._storage.exists(frame.storage_key):
                raise AnimaticApprovalError(
                    f"Storyboard asset for '{shot.id}' is missing."
                )
            audio_key = dialogue_audio_keys.get(shot.id, "")
            if shot.dialogue and (
                not audio_key or not await self._storage.exists(audio_key)
            ):
                raise AnimaticApprovalError(
                    f"Dialogue audio for '{shot.id}' is missing."
                )
            duration_frames = max(1, round(shot.duration_seconds * 24))
            clips.append(
                AnimaticClip(
                    shot_id=shot.id,
                    start_frame=start_frame,
                    duration_frames=duration_frames,
                    image_storage_key=frame.storage_key,
                    dialogue=shot.dialogue,
                    dialogue_audio_storage_key=audio_key,
                )
            )
            start_frame += duration_frames
        return AnimaticProject.create(production_plan_id=plan.id, clips=tuple(clips))
