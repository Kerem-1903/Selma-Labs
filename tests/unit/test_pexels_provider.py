"""
Unit tests for PexelsProvider.

No network involved. ``_map_video`` and ``_select_video_file`` are pure
functions tested directly against sample data shaped like Pexels'
documented response; ``_raise_for_status`` is tested against manually
constructed httpx.Response objects, which requires no network access.
"""
from __future__ import annotations

import httpx
import pytest

from core.domain.exceptions import (
    ProviderAuthError,
    ProviderError,
    ProviderQuotaExceededError,
)
from infrastructure.providers.video.pexels_provider import PexelsProvider


def _sample_video(**overrides) -> dict:
    video = {
        "id": 2499611,
        "width": 1080,
        "height": 1920,
        "duration": 10,
        "tags": [],
        "url": "https://www.pexels.com/video/a-ship-2499611/",
        "image": "https://images.pexels.com/videos/2499611/thumb.jpeg",
        "user": {"name": "Ruvim Miksanskiy", "url": "https://pexels.com/@ruvim"},
        "video_files": [
            {
                "quality": "sd", "file_type": "video/mp4", "width": 640,
                "height": 1138, "fps": 25.0, "link": "https://videos.pexels.com/sd.mp4",
            },
            {
                "quality": "hd", "file_type": "video/mp4", "width": 1080,
                "height": 1920, "fps": 25.0, "link": "https://videos.pexels.com/hd.mp4",
            },
        ],
    }
    video.update(overrides)
    return video


def test_map_video_prefers_hd_mp4_file():
    asset = PexelsProvider._map_video(_sample_video(), query="ship")

    assert asset.id == "pexels:2499611"
    assert asset.provider == "pexels"
    assert asset.provider_asset_id == "2499611"
    assert asset.media_type == "video"
    assert asset.original_url == "https://videos.pexels.com/hd.mp4"
    assert asset.width == 1080
    assert asset.height == 1920
    assert asset.fps == 25.0
    assert asset.duration_seconds == 10.0
    assert asset.local_path is None
    assert asset.metadata == {}


def test_map_video_falls_back_to_search_query_when_no_tags():
    asset = PexelsProvider._map_video(_sample_video(tags=[]), query="Titanic ship")
    assert asset.tags == ["Titanic ship"]


def test_map_video_uses_provider_tags_when_present():
    asset = PexelsProvider._map_video(_sample_video(tags=["ocean", "boat"]), query="ship")
    assert asset.tags == ["ocean", "boat"]


def test_map_video_builds_attribution_from_user_name():
    asset = PexelsProvider._map_video(_sample_video(), query="ship")
    assert asset.attribution == "Video by Ruvim Miksanskiy on Pexels"


def test_map_video_falls_back_to_page_url_when_no_video_files():
    asset = PexelsProvider._map_video(_sample_video(video_files=[]), query="ship")
    assert asset.original_url == "https://www.pexels.com/video/a-ship-2499611/"


def test_select_video_file_prefers_hd_over_sd():
    files = [
        {"quality": "sd", "file_type": "video/mp4", "link": "sd.mp4"},
        {"quality": "hd", "file_type": "video/mp4", "link": "hd.mp4"},
    ]
    chosen = PexelsProvider._select_video_file(files)
    assert chosen["link"] == "hd.mp4"


def test_select_video_file_prefers_highest_resolution_premium_portrait():
    files = [
        {
            "quality": "hd",
            "file_type": "video/mp4",
            "width": 1080,
            "height": 1920,
            "fps": 30,
            "link": "1080.mp4",
        },
        {
            "quality": "hd",
            "file_type": "video/mp4",
            "width": 2160,
            "height": 3840,
            "fps": 30,
            "link": "4k.mp4",
        },
        {
            "quality": "hd",
            "file_type": "video/mp4",
            "width": 3840,
            "height": 2160,
            "fps": 60,
            "link": "landscape.mp4",
        },
    ]
    assert PexelsProvider._select_video_file(files)["link"] == "4k.mp4"


def test_select_video_file_falls_back_to_first_when_no_preferred_quality():
    files = [{"quality": "4k", "file_type": "video/mp4", "link": "4k.mp4"}]
    chosen = PexelsProvider._select_video_file(files)
    assert chosen["link"] == "4k.mp4"


def test_select_video_file_returns_none_for_empty_list():
    assert PexelsProvider._select_video_file([]) is None


def test_raise_for_status_ok_does_nothing():
    response = httpx.Response(status_code=200, request=httpx.Request("GET", "https://x"))
    PexelsProvider._raise_for_status(response)  # should not raise


def test_raise_for_status_401_raises_auth_error():
    response = httpx.Response(
        status_code=401, text="unauthorized", request=httpx.Request("GET", "https://x")
    )
    with pytest.raises(ProviderAuthError):
        PexelsProvider._raise_for_status(response)


def test_raise_for_status_429_raises_quota_error():
    response = httpx.Response(
        status_code=429, text="rate limited", request=httpx.Request("GET", "https://x")
    )
    with pytest.raises(ProviderQuotaExceededError):
        PexelsProvider._raise_for_status(response)


def test_raise_for_status_other_error_raises_provider_error():
    response = httpx.Response(
        status_code=500, text="server error", request=httpx.Request("GET", "https://x")
    )
    with pytest.raises(ProviderError):
        PexelsProvider._raise_for_status(response)


def test_constructor_requires_api_key():
    with pytest.raises(ProviderAuthError):
        PexelsProvider(api_key="")
