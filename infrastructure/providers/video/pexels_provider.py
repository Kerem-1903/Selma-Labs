"""
PexelsProvider — concrete VideoSourcePort adapter backed by the Pexels
Video API.

This is the only file in the codebase that knows the Pexels API exists, or
what its response JSON looks like. VideoSearchService and everything above
it depends on VideoSourcePort, never on this class directly.

Called directly via httpx, the same choice made for ElevenLabsVoiceProvider
in Sprint 2: a plain REST call keeps error-to-exception mapping fully under
this codebase's control instead of depending on how a third-party SDK
wraps errors.

Reference: https://www.pexels.com/api/documentation/#videos-search
Response shape relied on here (if Pexels changes their API, only this file
needs to change):

    {
      "videos": [
        {
          "id": 2499611,
          "width": 1080,
          "height": 1920,
          "duration": 10,
          "tags": [],
          "url": "https://www.pexels.com/video/a-ship-2499611/",
          "image": "https://images.pexels.com/videos/2499611/thumb.jpeg",
          "user": {"name": "Ruvim Miksanskiy", "url": "..."},
          "video_files": [
            {"quality": "hd", "file_type": "video/mp4", "width": 1080,
             "height": 1920, "fps": 25.0, "link": "https://...hd.mp4"},
            ...
          ]
        }
      ]
    }

Pexels' video objects don't reliably carry descriptive tags (usually an
empty list); when that's the case we fall back to the search query itself
as the asset's tag, since "what was this found with" is still useful
metadata for a future scene-matching sprint.
"""
from __future__ import annotations

from typing import Optional

import httpx

from core.domain.entities.media_asset import MediaAsset
from core.domain.exceptions import (
    AssetDownloadError,
    ProviderAuthError,
    ProviderConnectionError,
    ProviderError,
    ProviderQuotaExceededError,
    ProviderTimeoutError,
)
from core.domain.ports.video_source_port import VideoSourcePort

API_BASE_URL = "https://api.pexels.com/videos"
REQUEST_TIMEOUT_SECONDS = 30.0

# Preference order when a video offers multiple encoded files. Pexels
# always offers at least one "sd" mp4; "hd" is preferred when present.
PREFERRED_QUALITY_ORDER = ("hd", "sd")


class PexelsProvider(VideoSourcePort):
    """Searches for and downloads stock video footage via the Pexels API."""

    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ProviderAuthError(
                "Pexels API key is missing. Set PEXELS_API_KEY in your .env file."
            )
        self._api_key = api_key

    async def search(self, query: str, max_results: int) -> list[MediaAsset]:
        url = f"{API_BASE_URL}/search"

        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    url,
                    headers={"Authorization": self._api_key},
                    params={"query": query, "per_page": max_results},
                )
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(f"Pexels API timed out: {exc}") from exc
        except httpx.ConnectError as exc:
            raise ProviderConnectionError(f"Could not connect to Pexels API: {exc}") from exc
        except httpx.RequestError as exc:
            raise ProviderConnectionError(f"Pexels API request failed: {exc}") from exc

        self._raise_for_status(response)

        payload = response.json()
        return [self._map_video(item, query) for item in payload.get("videos", [])]

    async def download(self, asset: MediaAsset) -> bytes:
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
                response = await client.get(asset.original_url)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(f"Pexels download timed out: {exc}") from exc
        except httpx.ConnectError as exc:
            raise ProviderConnectionError(
                f"Could not connect to download '{asset.original_url}': {exc}"
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderConnectionError(f"Pexels download request failed: {exc}") from exc

        if response.status_code != 200:
            raise AssetDownloadError(
                f"Failed to download asset '{asset.id}' from "
                f"'{asset.original_url}' (status {response.status_code})."
            )

        return response.content

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.status_code == 200:
            return
        if response.status_code == 401:
            raise ProviderAuthError(f"Pexels API rejected the API key: {response.text}")
        if response.status_code == 429:
            raise ProviderQuotaExceededError(
                f"Pexels API rate limit or quota exceeded: {response.text}"
            )
        raise ProviderError(
            f"Pexels API returned an error (status {response.status_code}): {response.text}"
        )

    @classmethod
    def _map_video(cls, item: dict, query: str) -> MediaAsset:
        """Translate one raw Pexels video JSON object into a
        provider-independent MediaAsset. This is the only place in the
        codebase that reads Pexels' response shape."""
        video_file = cls._select_video_file(item.get("video_files") or [])
        user = item.get("user") or {}
        tags = item.get("tags") or [query]

        return MediaAsset(
            id=f"pexels:{item['id']}",
            provider="pexels",
            provider_asset_id=str(item["id"]),
            media_type="video",
            original_url=(video_file or {}).get("link") or item.get("url", ""),
            thumbnail_url=item.get("image"),
            width=(video_file or {}).get("width") or item.get("width"),
            height=(video_file or {}).get("height") or item.get("height"),
            duration_seconds=(
                float(item["duration"]) if item.get("duration") is not None else None
            ),
            fps=(video_file or {}).get("fps"),
            tags=list(tags),
            attribution=f"Video by {user.get('name', 'unknown')} on Pexels",
            license="Pexels License (https://www.pexels.com/license/)",
            # metadata intentionally left empty (default {}) — Pexels'
            # search response carries none of the AI-Vision-style
            # attributes (dominant_colors, motion_level, etc.) planned for
            # a later scene-matching sprint.
        )

    @staticmethod
    def _select_video_file(video_files: list[dict]) -> Optional[dict]:
        """Pick the best available encoded file: prefer mp4 files, then
        prefer 'hd' quality over 'sd'. Falls back to the first available
        file if nothing matches the preferred type/quality — still usable,
        just not the adapter's first choice."""
        mp4_files = [f for f in video_files if f.get("file_type") == "video/mp4"]
        candidates = mp4_files or video_files
        if not candidates:
            return None

        for quality in PREFERRED_QUALITY_ORDER:
            for f in candidates:
                if f.get("quality") == quality:
                    return f
        return candidates[0]
