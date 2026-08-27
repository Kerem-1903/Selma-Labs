import asyncio
import logging
import os
from typing import Optional
from core.domain.ports.social_upload_port import SocialUploadPort
from infrastructure.providers.publish.google_api_youtube_upload_provider import GoogleApiYoutubeUploadProvider

logger = logging.getLogger(__name__)

class OmnichannelUploadProvider(SocialUploadPort):
    def __init__(self):
        self.youtube_provider = GoogleApiYoutubeUploadProvider()
        # In a real app, initialize TikTok/Instagram API clients here

    async def upload_video(
        self,
        platform: str,
        video_path: str,
        title: str,
        description: str,
        tags: list[str],
        privacy_status: str = "unlisted"
    ) -> str:
        platform_normalized = platform.lower().strip()
        logger.info(f"Starting Omnichannel upload to {platform_normalized} for video: {video_path}")

        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found for upload: {video_path}")

        if platform_normalized == "youtube":
            return await self.youtube_provider.upload_video(video_path, title, description, tags, privacy_status)
        elif platform_normalized in ["tiktok", "instagram_reels", "twitter"]:
            # Mocking other platforms since we don't have their API credentials set up locally
            logger.info(f"MOCK UPLOAD SUCCESS: '{title}' uploaded to {platform_normalized} as {privacy_status}.")
            return f"mock_{platform_normalized}_id_987654321"
        else:
            raise ValueError(f"Unsupported distribution platform: {platform}")
