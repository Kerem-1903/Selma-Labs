from __future__ import annotations

from abc import ABC, abstractmethod

from core.domain.value_objects.trend_topic_selection import TrendTopicSelection
from core.domain.value_objects.trend_video import TrendVideo


class TopicSelectionPort(ABC):
    @property
    @abstractmethod
    def provider_identity(self) -> str:
        raise NotImplementedError

    @abstractmethod
    async def select(
        self,
        *,
        candidates: list[TrendVideo],
        language: str,
    ) -> TrendTopicSelection:
        raise NotImplementedError
