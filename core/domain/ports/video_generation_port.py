from abc import ABC, abstractmethod
from core.domain.entities.media_asset import MediaAsset

class VideoGenerationPort(ABC):
    """
    Contract for Text-to-Video AI providers (e.g., Luma, Kling, Runway Gen-3).
    These generate a completely new video asset from a highly detailed cinematic prompt.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the generation provider."""
        raise NotImplementedError

    @abstractmethod
    async def generate_video(self, prompt: str, duration_seconds: float = 5.0) -> MediaAsset:
        """
        Generates a video based on the cinematic prompt.

        Args:
            prompt: Detailed cinematic description.
            duration_seconds: Desired length of the video.

        Returns:
            A MediaAsset representing the generated video, which could initially be a remote URL or ID.
        """
        raise NotImplementedError
