from typing import List, Callable
from core.domain.entities.shot_animation import ShotPlan, ShotMotionClip
from core.domain.ports.motion_generator_port import MotionGeneratorPort
from core.domain.ports.lipsync_port import LipSyncPort
from infrastructure.compositor.layered_compositor import LayeredCompositor

class AnimationOrchestratorService:
    def __init__(
        self,
        motion_generator: MotionGeneratorPort,
        lipsync_generator: LipSyncPort,
        compositor: LayeredCompositor
    ):
        self.motion_generator = motion_generator
        self.lipsync_generator = lipsync_generator
        self.compositor = compositor

    async def orchestrate_shot(self, shot_plan: ShotPlan, background_image_path: str, audio_path: str, output_path: str, progress_callback: Callable[[float], None] = None) -> str:
        # Step 1: 2-Pass Motion Generation
        motion_clip = await self.motion_generator.generate_motion_clip(shot_plan, progress_callback)

        # Step 2: Lip-Sync
        lipsync_video_path = motion_clip.video_path.replace('.mp4', '_lipsync.mp4')
        await self.lipsync_generator.generate_lipsync_clip(motion_clip.video_path, audio_path, lipsync_video_path)

        # Step 3: Layered Composition
        final_video_path = await self.compositor.compose_scene(background_image_path, lipsync_video_path, audio_path, output_path)

        return final_video_path
