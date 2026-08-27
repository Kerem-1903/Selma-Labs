from abc import ABC, abstractmethod
from typing import Optional

class SocialUploadPort(ABC):
    """
    Unified contract for omnichannel social media video distribution.
    """

    @abstractmethod
    async def upload_video(
        self,
        platform: str,
        video_path: str,
        title: str,
        description: str,
        tags: list[str],
        privacy_status: str = "unlisted"
    ) -> str:
        """
        Uploads a video to the specified platform and returns the Video ID/URL.

        Args:
            platform: Platform name ('youtube', 'tiktok', 'instagram', 'twitter').
            video_path: Local filesystem path to the compiled .mp4 video.
            title: Title of the video.
            description: Description of the video.
            tags: SEO tags.
            privacy_status: Visibility status (e.g., 'public', 'private', 'unlisted').

        Returns:
            The Video ID or URL on the platform.
        """
        raise NotImplementedError
