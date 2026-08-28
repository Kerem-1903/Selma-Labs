from abc import ABC, abstractmethod
from core.domain.entities.media_asset import MediaAsset
from core.domain.value_objects.video_generation_request import VideoGenerationRequest

class VideoGenerationPort(ABC):
    """
    Contract for AI video generation providers.
    It takes a fully structured Request containing references, constraints, and constraints
    rather than a generic text prompt.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the generation provider."""
        raise NotImplementedError

    @abstractmethod
    async def generate_video(self, request: VideoGenerationRequest) -> MediaAsset:
        """
        Generates a video based on the provided request.

        Args:
            request: The generation request object containing constraints, IDs, and references.

        Returns:
            A MediaAsset representing the generated video, which could initially be a remote URL or ID.
        """
        raise NotImplementedError
