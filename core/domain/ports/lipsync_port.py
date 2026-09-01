from __future__ import annotations

from abc import ABC, abstractmethod


class LipSyncPort(ABC):
    @property
    def name(self) -> str:
        return self.__class__.__name__

    @abstractmethod
    async def generate_lipsync_clip(
        self,
        source_image_or_video_path: str,
        audio_path: str,
        output_video_path: str,
    ) -> str:
        """Return a portable storage key for an audio-driven character clip."""
        raise NotImplementedError
