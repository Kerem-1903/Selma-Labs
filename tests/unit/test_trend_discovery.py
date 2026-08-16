from __future__ import annotations

import json

import httpx
import pytest

from core.application.services.trend_topic_service import TrendTopicService
from core.domain.exceptions import ProviderAuthError, TrendDiscoveryError
from core.domain.ports.topic_selection_port import TopicSelectionPort
from core.domain.ports.trend_source_port import TrendSourcePort
from core.domain.value_objects.trend_topic_selection import TrendTopicSelection
from core.domain.value_objects.trend_video import TrendVideo
from infrastructure.providers.topic_selection.nvidia_topic_selection_provider import (
    NvidiaTopicSelectionProvider,
)
from infrastructure.providers.trend.youtube_most_popular_provider import (
    YoutubeMostPopularProvider,
)


def make_video(video_id: str = "video-1", views: int = 100) -> TrendVideo:
    return TrendVideo(
        video_id=video_id,
        title=f"Trend {video_id}",
        description="Science short",
        url=f"https://youtube.test/{video_id}",
        channel_title="Channel",
        published_at="2026-01-01T00:00:00Z",
        duration_seconds=45.0,
        view_count=views,
        like_count=10,
        category_id="28",
    )


class FakeTrendSource(TrendSourcePort):
    def __init__(self, videos: list[TrendVideo]) -> None:
        self.videos = videos

    @property
    def provider_identity(self) -> str:
        return "fake:trends"

    async def fetch(self, **kwargs: object) -> list[TrendVideo]:
        return self.videos


class FakeSelector(TopicSelectionPort):
    @property
    def provider_identity(self) -> str:
        return "fake:selector"

    async def select(
        self,
        *,
        candidates: list[TrendVideo],
        language: str,
    ) -> TrendTopicSelection:
        return TrendTopicSelection(
            topic="Why animals glow",
            angle=language,
            rationale="High demand",
            source_video_ids=[candidates[0].video_id],
            candidates=candidates,
            provider_used=self.provider_identity,
        )


class FakeChatClient:
    def __init__(self, response: str) -> None:
        self.response = response

    async def complete(self, **kwargs: object) -> str:
        return self.response


def test_youtube_provider_requires_api_key():
    with pytest.raises(ProviderAuthError):
        YoutubeMostPopularProvider(api_key="")


def test_youtube_duration_parser():
    assert YoutubeMostPopularProvider._parse_duration("PT2M15S") == 135.0
    assert YoutubeMostPopularProvider._parse_duration("PT45S") == 45.0
    assert YoutubeMostPopularProvider._parse_duration("invalid") is None


@pytest.mark.asyncio
async def test_youtube_provider_filters_long_videos_and_sorts_views():
    async def handler(request: httpx.Request) -> httpx.Response:
        category_id = request.url.params["videoCategoryId"]
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": f"short-{category_id}",
                        "snippet": {
                            "title": "Short science",
                            "description": "Description",
                            "channelTitle": "Channel",
                            "publishedAt": "2026-01-01T00:00:00Z",
                            "categoryId": category_id,
                        },
                        "contentDetails": {"duration": "PT45S"},
                        "statistics": {
                            "viewCount": "1000",
                            "likeCount": "100",
                        },
                    },
                    {
                        "id": f"long-{category_id}",
                        "snippet": {"title": "Long", "categoryId": category_id},
                        "contentDetails": {"duration": "PT10M"},
                        "statistics": {"viewCount": "999999"},
                    },
                ]
            },
        )

    provider = YoutubeMostPopularProvider(
        api_key="test-key",
        transport=httpx.MockTransport(handler),
    )
    videos = await provider.fetch(
        region_code="US",
        category_ids=["15", "28"],
        max_results_per_category=10,
    )
    assert [video.video_id for video in videos] == ["short-15", "short-28"]


@pytest.mark.asyncio
async def test_youtube_provider_skips_unavailable_category_chart():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            json={
                "error": {
                    "errors": [{"reason": "notFound"}],
                    "message": "Requested entity was not found.",
                }
            },
        )

    provider = YoutubeMostPopularProvider(
        api_key="test-key",
        transport=httpx.MockTransport(handler),
    )
    videos = await provider.fetch(
        region_code="US",
        category_ids=["27"],
        max_results_per_category=10,
    )
    assert videos == []


@pytest.mark.asyncio
async def test_youtube_provider_searches_relevant_short_videos():
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/search"):
            assert request.url.params["order"] == "viewCount"
            assert request.url.params["videoDuration"] == "short"
            return httpx.Response(
                200,
                json={"items": [{"id": {"videoId": "science-1"}}]},
            )
        assert request.url.path.endswith("/videos")
        assert request.url.params["id"] == "science-1"
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "science-1",
                        "snippet": {
                            "title": "Why animals glow",
                            "description": "Bioluminescence",
                            "channelTitle": "Science",
                            "publishedAt": "2026-01-01T00:00:00Z",
                            "categoryId": "28",
                        },
                        "contentDetails": {"duration": "PT40S"},
                        "statistics": {"viewCount": "5000", "likeCount": "500"},
                    }
                ]
            },
        )

    provider = YoutubeMostPopularProvider(
        api_key="test-key",
        search_query="science facts|animal facts",
        transport=httpx.MockTransport(handler),
    )
    videos = await provider.fetch(
        region_code="US",
        category_ids=["28"],
        max_results_per_category=20,
    )
    assert [video.video_id for video in videos] == ["science-1"]


@pytest.mark.asyncio
async def test_topic_selector_returns_original_supported_topic():
    candidates = [make_video()]
    response = json.dumps(
        {
            "topic": "Why deep sea animals glow",
            "angle": "Bioluminescence in darkness",
            "rationale": "Strong science interest",
            "source_video_ids": ["video-1"],
        }
    )
    provider = NvidiaTopicSelectionProvider(
        api_key="test-key",
        model="test-model",
        client=FakeChatClient(response),
        audit_enabled=False,
    )
    selection = await provider.select(candidates=candidates, language="en")
    assert selection.topic == "Why deep sea animals glow"
    assert selection.source_video_ids == ["video-1"]


@pytest.mark.asyncio
async def test_topic_selector_audits_unrelated_sources_with_second_model():
    candidates = [make_video("relevant"), make_video("unrelated")]

    class SequenceChatClient:
        def __init__(self) -> None:
            self.models: list[str] = []
            self.responses = [
                json.dumps(
                    {
                        "topic": "Why deep sea animals glow",
                        "angle": "Bioluminescence",
                        "rationale": "Strong interest",
                        "source_video_ids": ["relevant", "unrelated"],
                    }
                ),
                json.dumps({"relevant_source_video_ids": ["relevant"]}),
            ]

        async def complete(self, **kwargs: object) -> str:
            self.models.append(str(kwargs["model"]))
            return self.responses.pop(0)

    client = SequenceChatClient()
    provider = NvidiaTopicSelectionProvider(
        api_key="test-key",
        model="text-model",
        audit_model="audit-model",
        client=client,
    )
    selection = await provider.select(candidates=candidates, language="en")
    assert selection.source_video_ids == ["relevant"]
    assert client.models == ["text-model", "audit-model"]


@pytest.mark.asyncio
async def test_trend_service_ranks_by_views():
    service = TrendTopicService(
        FakeTrendSource([make_video("low", 1), make_video("high", 10)]),
        FakeSelector(),
        candidate_limit=2,
    )
    selection = await service.discover(
        region_code="US",
        category_ids=["28"],
        max_results_per_category=10,
        language="en",
    )
    assert selection.source_video_ids == ["high"]


@pytest.mark.asyncio
async def test_trend_service_rejects_empty_results():
    service = TrendTopicService(FakeTrendSource([]), FakeSelector())
    with pytest.raises(TrendDiscoveryError, match="no short-form trend candidates"):
        await service.discover(
            region_code="US",
            category_ids=["28"],
            max_results_per_category=10,
            language="en",
        )
