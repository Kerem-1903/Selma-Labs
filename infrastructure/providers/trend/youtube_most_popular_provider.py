from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import httpx

from core.domain.exceptions import (
    ProviderAuthError,
    ProviderConnectionError,
    ProviderError,
    ProviderQuotaExceededError,
    ProviderTimeoutError,
)
from core.domain.ports.trend_source_port import TrendSourcePort
from core.domain.value_objects.trend_video import TrendVideo

API_URL = "https://www.googleapis.com/youtube/v3/videos"
SEARCH_API_URL = "https://www.googleapis.com/youtube/v3/search"
DURATION_PATTERN = re.compile(
    r"^P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?$"
)


class YoutubeMostPopularProvider(TrendSourcePort):
    def __init__(
        self,
        api_key: str,
        min_duration_seconds: int = 10,
        max_duration_seconds: int = 180,
        timeout_seconds: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
        search_query: str = "",
        relevance_language: str = "en",
        published_within_days: int = 30,
    ) -> None:
        if not api_key:
            raise ProviderAuthError(
                "YouTube Data API key is missing. Set YOUTUBE_DATA_API_KEY in .env."
            )
        self._api_key = api_key
        self._min_duration_seconds = min_duration_seconds
        self._max_duration_seconds = max_duration_seconds
        self._timeout_seconds = timeout_seconds
        self._transport = transport
        self._search_query = search_query.strip()
        self._relevance_language = relevance_language.strip()
        self._published_within_days = published_within_days

    @property
    def provider_identity(self) -> str:
        return "youtube:mostPopular"

    async def fetch(
        self,
        *,
        region_code: str,
        category_ids: list[str],
        max_results_per_category: int,
    ) -> list[TrendVideo]:
        videos: dict[str, TrendVideo] = {}
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds,
                transport=self._transport,
            ) as client:
                if self._search_query:
                    return await self._search_short_videos(
                        client,
                        region_code=region_code,
                        max_results=max_results_per_category,
                    )
                for category_id in category_ids:
                    response = await client.get(
                        API_URL,
                        params={
                            "part": "snippet,contentDetails,statistics",
                            "chart": "mostPopular",
                            "regionCode": region_code,
                            "videoCategoryId": category_id,
                            "maxResults": max_results_per_category,
                            "key": self._api_key,
                        },
                    )
                    if self._is_unavailable_chart(response):
                        continue
                    self._raise_for_status(response)
                    for item in response.json().get("items", []):
                        video = self._map_video(item)
                        if video is None:
                            continue
                        if video.category_id != category_id:
                            continue
                        if not (
                            self._min_duration_seconds
                            <= video.duration_seconds
                            <= self._max_duration_seconds
                        ):
                            continue
                        videos[video.video_id] = video
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(f"YouTube Data API timed out: {exc}") from exc
        except httpx.RequestError as exc:
            raise ProviderConnectionError(
                f"Could not connect to YouTube Data API: {exc}"
            ) from exc
        except ValueError as exc:
            raise ProviderError("YouTube Data API returned invalid JSON.") from exc
        return sorted(videos.values(), key=lambda video: video.view_count, reverse=True)

    async def _search_short_videos(
        self,
        client: httpx.AsyncClient,
        *,
        region_code: str,
        max_results: int,
    ) -> list[TrendVideo]:
        published_after = datetime.now(timezone.utc) - timedelta(
            days=self._published_within_days
        )
        search_response = await client.get(
            SEARCH_API_URL,
            params={
                "part": "snippet",
                "type": "video",
                "q": self._search_query,
                "order": "viewCount",
                "videoDuration": "short",
                "safeSearch": "strict",
                "regionCode": region_code,
                "relevanceLanguage": self._relevance_language,
                "publishedAfter": published_after.isoformat().replace("+00:00", "Z"),
                "maxResults": min(max_results, 50),
                "key": self._api_key,
            },
        )
        self._raise_for_status(search_response)
        video_ids = [
            str((item.get("id") or {}).get("videoId") or "").strip()
            for item in search_response.json().get("items", [])
        ]
        video_ids = [video_id for video_id in video_ids if video_id]
        if not video_ids:
            return []
        details_response = await client.get(
            API_URL,
            params={
                "part": "snippet,contentDetails,statistics",
                "id": ",".join(video_ids),
                "maxResults": len(video_ids),
                "key": self._api_key,
            },
        )
        self._raise_for_status(details_response)
        videos = []
        for item in details_response.json().get("items", []):
            video = self._map_video(item)
            if video is None:
                continue
            if not (
                self._min_duration_seconds
                <= video.duration_seconds
                <= self._max_duration_seconds
            ):
                continue
            videos.append(video)
        return sorted(videos, key=lambda video: video.view_count, reverse=True)

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if not response.is_error:
            return
        reason = ""
        try:
            errors = response.json().get("error", {}).get("errors", [])
            reason = str(errors[0].get("reason") or "") if errors else ""
        except ValueError:
            pass
        if response.status_code == 429 or reason in {"quotaExceeded", "dailyLimitExceeded"}:
            raise ProviderQuotaExceededError("YouTube Data API quota exceeded.")
        if response.status_code in {400, 401, 403} and reason in {
            "accessNotConfigured",
            "forbidden",
            "ipRefererBlocked",
            "keyInvalid",
        }:
            raise ProviderAuthError(
                f"YouTube Data API rejected the API key or restrictions ({reason})."
            )
        raise ProviderError(
            f"YouTube Data API returned an error (status {response.status_code}, reason {reason or 'unknown'})."
        )

    @staticmethod
    def _is_unavailable_chart(response: httpx.Response) -> bool:
        if response.status_code != 404:
            return False
        try:
            errors = response.json().get("error", {}).get("errors", [])
            return bool(errors and errors[0].get("reason") == "notFound")
        except ValueError:
            return False

    @classmethod
    def _map_video(cls, item: dict) -> TrendVideo | None:
        video_id = str(item.get("id") or "").strip()
        snippet = item.get("snippet") or {}
        duration = cls._parse_duration(
            str((item.get("contentDetails") or {}).get("duration") or "")
        )
        if not video_id or duration is None:
            return None
        statistics = item.get("statistics") or {}
        return TrendVideo(
            video_id=video_id,
            title=str(snippet.get("title") or "").strip(),
            description=str(snippet.get("description") or "").strip(),
            url=f"https://www.youtube.com/watch?v={video_id}",
            channel_title=str(snippet.get("channelTitle") or "").strip(),
            published_at=str(snippet.get("publishedAt") or "").strip(),
            duration_seconds=duration,
            view_count=int(statistics.get("viewCount") or 0),
            like_count=int(statistics.get("likeCount") or 0),
            category_id=str(snippet.get("categoryId") or "").strip(),
        )

    @staticmethod
    def _parse_duration(value: str) -> float | None:
        match = DURATION_PATTERN.fullmatch(value)
        if not match:
            return None
        parts = {name: int(amount or 0) for name, amount in match.groupdict().items()}
        return float(
            parts["days"] * 86400
            + parts["hours"] * 3600
            + parts["minutes"] * 60
            + parts["seconds"]
        )
