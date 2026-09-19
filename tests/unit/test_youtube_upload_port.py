from unittest.mock import MagicMock, patch

import pytest

from infrastructure.providers.publish.google_api_youtube_upload_provider import (
    GoogleApiYoutubeUploadProvider,
)


@pytest.mark.asyncio
async def test_youtube_upload_mock_mode_when_no_credentials():
    with patch("os.path.exists", return_value=False):
        provider = GoogleApiYoutubeUploadProvider()
        result = await provider.upload_video(
            "dummy.mp4", "Test Video", "Test Description", ["test"]
        )
        assert result == "mock_video_id_123"

@pytest.mark.asyncio
async def test_youtube_upload_real_mode_success():
    with patch("os.path.exists", return_value=True), \
         patch("infrastructure.providers.publish.google_api_youtube_upload_provider.Credentials.from_authorized_user_file"), \
         patch("infrastructure.providers.publish.google_api_youtube_upload_provider.build") as mock_build, \
         patch("infrastructure.providers.publish.google_api_youtube_upload_provider.MediaFileUpload"):

        # Mock the googleapiclient response
        mock_youtube = MagicMock()
        mock_build.return_value = mock_youtube
        mock_request = MagicMock()

        # next_chunk() returns (status, response)
        mock_request.next_chunk.return_value = (None, {"id": "real_video_id_789"})
        mock_youtube.videos().insert.return_value = mock_request

        provider = GoogleApiYoutubeUploadProvider()
        result = await provider.upload_video(
            "dummy.mp4", "Test Video", "Test Description", ["test"]
        )
        assert result == "real_video_id_789"
        mock_youtube.videos().insert.assert_called_once()
