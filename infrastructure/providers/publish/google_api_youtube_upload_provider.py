import asyncio
import logging
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials

from core.domain.ports.youtube_upload_port import YoutubeUploadPort

logger = logging.getLogger(__name__)

class GoogleApiYoutubeUploadProvider(YoutubeUploadPort):
    def __init__(self, client_secrets_file: str = "client_secret.json", credentials_file: str = "token.json"):
        self.client_secrets_file = client_secrets_file
        self.credentials_file = credentials_file

    def _get_authenticated_service(self):
        # Assumes the user has already completed the OAuth 2.0 flow and saved token.json
        import os
        if not os.path.exists(self.credentials_file):
            logger.warning(f"OAuth credentials file {self.credentials_file} not found. Operating in MOCK mode.")
            return None

        credentials = Credentials.from_authorized_user_file(self.credentials_file, ['https://www.googleapis.com/auth/youtube.upload'])
        return build('youtube', 'v3', credentials=credentials)

    async def upload_video(
        self,
        video_path: str,
        title: str,
        description: str,
        tags: list[str],
        privacy_status: str = "unlisted"
    ) -> str:
        logger.info(f"Starting YouTube upload for video: {video_path}")

        def _upload_sync() -> str:
            youtube = self._get_authenticated_service()
            if not youtube:
                logger.info(f"MOCK UPLOAD SUCCESS: '{title}' uploaded as {privacy_status}.")
                return "mock_video_id_123"

            body = {
                'snippet': {
                    'title': title,
                    'description': description,
                    'tags': tags,
                    'categoryId': '28' # Science & Technology
                },
                'status': {
                    'privacyStatus': privacy_status,
                    'selfDeclaredMadeForKids': False
                }
            }

            # Uses resumable upload to safely handle large files
            media = MediaFileUpload(video_path, chunksize=-1, resumable=True, mimetype='video/mp4')

            request = youtube.videos().insert(
                part=','.join(body.keys()),
                body=body,
                media_body=media
            )

            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    logger.info(f"Upload progress: {int(status.progress() * 100)}%")

            logger.info(f"Upload Complete! Video ID: {response['id']}")
            return response['id']

        # Offload the blocking network calls to an async thread
        return await asyncio.to_thread(_upload_sync)
