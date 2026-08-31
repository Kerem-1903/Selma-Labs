import os
import uuid
from typing import Callable, Any
from core.domain.ports.motion_generator_port import MotionGeneratorPort
from core.domain.entities.shot_animation import ShotPlan, ShotMotionClip
from core.domain.value_objects.render_config import RenderConfig
from infrastructure.providers.motion.comfyui_ws_client import ComfyUIWsClient

class ComfyUIMotionAdapter(MotionGeneratorPort):
    def __init__(self, server_address: str, cache_dir: str):
        self.client = ComfyUIWsClient(server_address)
        self.cache_dir = cache_dir
        os.makedirs(self.cache_dir, exist_ok=True)

    async def generate_motion_clip(self, shot_plan: ShotPlan, progress_callback: Callable[[float], None]) -> ShotMotionClip:
        # Example 2-pass logic, this is a placeholder for actual ComfyUI graph generation
        config = RenderConfig(
            width=1080, height=1920, fps=24, seed=12345,
            sampler_name="euler_a", pass1_denoise=0.8, pass2_denoise=0.5
        )
        clip_hash = config.compute_hash(shot_plan.prompt, ["akira"])
        video_filename = f"{shot_plan.id}_{clip_hash}.mp4"
        video_path = os.path.join(self.cache_dir, video_filename)

        if os.path.exists(video_path):
            return ShotMotionClip(video_path=video_path, hash=clip_hash, seed=config.seed, cached=True)

        # Mock implementation of Pass 1 and Pass 2
        # In reality, this would build a ComfyUI prompt JSON and call queue_prompt_and_wait

        # Simulate work
        if progress_callback:
            progress_callback(0.5) # Pass 1 complete
            progress_callback(1.0) # Pass 2 complete

        # Create a dummy file for the result
        with open(video_path, 'w') as f:
            f.write("mock video data")

        return ShotMotionClip(video_path=video_path, hash=clip_hash, seed=config.seed, cached=False)
