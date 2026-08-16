from __future__ import annotations

from core.domain.exceptions import TrendDiscoveryError
from core.domain.ports.topic_selection_port import TopicSelectionPort
from core.domain.ports.trend_source_port import TrendSourcePort
from core.domain.value_objects.trend_topic_selection import TrendTopicSelection


class TrendTopicService:
    def __init__(
        self,
        source_provider: TrendSourcePort,
        selection_provider: TopicSelectionPort,
        candidate_limit: int = 20,
    ) -> None:
        self._source_provider = source_provider
        self._selection_provider = selection_provider
        self._candidate_limit = candidate_limit

    async def discover(
        self,
        *,
        region_code: str,
        category_ids: list[str],
        max_results_per_category: int,
        language: str,
    ) -> TrendTopicSelection:
        videos = await self._source_provider.fetch(
            region_code=region_code,
            category_ids=category_ids,
            max_results_per_category=max_results_per_category,
        )
        if not videos:
            raise TrendDiscoveryError(
                "YouTube returned no short-form trend candidates for the configured filters."
            )
        ranked = sorted(videos, key=lambda video: video.view_count, reverse=True)
        return await self._selection_provider.select(
            candidates=ranked[: self._candidate_limit],
            language=language,
        )
