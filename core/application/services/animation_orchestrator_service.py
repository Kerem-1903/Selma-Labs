from __future__ import annotations

from collections.abc import Callable
from pathlib import PurePosixPath

from core.domain.entities.shot_animation import ShotPlan
from core.domain.exceptions import MotionGenerationError
from core.domain.ports.lipsync_port import LipSyncPort
from core.domain.ports.motion_generator_port import MotionGeneratorPort
from core.domain.ports.scene_compositor_port import SceneCompositorPort


class AnimationOrchestratorService:
    """Coordinate approved keyframe motion, lip sync, and final composition."""

    def __init__(
        self,
        motion_generator: MotionGeneratorPort,
        lipsync_generator: LipSyncPort,
        compositor: SceneCompositorPort,
    ) -> None:
        self._motion_generator = motion_generator
        self._lipsync_generator = lipsync_generator
        self._compositor = compositor

    async def orchestrate_shot(
        self,
        shot_plan: ShotPlan,
        background_image_path: str,
        audio_path: str,
        output_path: str,
        progress_callback: Callable[[float], None] | None = None,
    ) -> str:
        if not shot_plan.keyframe_approved:
            raise MotionGenerationError(
                "Animation orchestration cannot bypass the human keyframe approval gate."
            )
        self._validate_output_key(output_path)
        last_progress = 0.0

        def publish(value: float) -> None:
            nonlocal last_progress
            if progress_callback is None:
                return
            bounded = max(last_progress, min(1.0, max(0.0, value)))
            last_progress = bounded
            progress_callback(bounded)

        motion = await self._motion_generator.generate_motion_clip(
            shot_plan,
            lambda value: publish(value * 0.65),
        )
        publish(0.65)
        source_suffix = PurePosixPath(motion.video_path).suffix.casefold()
        lipsync_key = f"lipsync/{shot_plan.id}/{motion.hash}{source_suffix}"
        lipsync_video = await self._lipsync_generator.generate_lipsync_clip(
            motion.video_path,
            audio_path,
            lipsync_key,
        )
        publish(0.85)
        final_key = await self._compositor.compose_scene(
            background_image_path,
            lipsync_video,
            audio_path,
            output_path,
        )
        publish(1.0)
        return final_key

    @staticmethod
    def _validate_output_key(value: str) -> None:
        normalized = value.replace("\\", "/")
        path = PurePosixPath(normalized)
        if (
            not normalized.strip()
            or path.is_absolute()
            or ".." in path.parts
            or ":" in value
            or path.suffix.casefold() != ".mp4"
        ):
            raise ValueError("Animation output must be a portable .mp4 storage key.")
