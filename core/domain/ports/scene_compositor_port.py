from __future__ import annotations

from abc import ABC, abstractmethod


class SceneCompositorPort(ABC):
    @abstractmethod
    async def compose_scene(
        self,
        background_image_path: str,
        character_video_path: str,
        audio_path: str,
        output_video_path: str,
    ) -> str:
        """Return the portable storage key of the composited scene."""
        raise NotImplementedError
