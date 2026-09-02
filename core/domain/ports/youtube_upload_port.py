from abc import ABC, abstractmethod

class YoutubeUploadPort(ABC):
    """
    Contract for uploading finished video packages to YouTube.
    """

    @abstractmethod
    async def upload_video(
        self,
        video_path: str,
        title: str,
        description: str,
        tags: list[str],
        privacy_status: str = "unlisted"
    ) -> str:
        """
        Uploads a video to YouTube and returns the YouTube Video ID.

        Args:
            video_path: The local filesystem path to the compiled .mp4 video.
            title: The title of the YouTube video.
            description: The description of the video.
            tags: A list of tags for SEO.
            privacy_status: Options include "public", "private", or "unlisted".

        Returns:
            The YouTube Video ID (e.g., dQw4w9WgXcQ).

        Raises:
            Exception if the upload fails.
        """
        raise NotImplementedError
