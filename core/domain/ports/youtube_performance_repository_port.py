"""Persistence boundary for post-publish YouTube performance records."""
from __future__ import annotations

from abc import ABC, abstractmethod

from core.domain.value_objects.youtube_performance import YoutubePerformanceRecord


class YoutubePerformanceRepositoryPort(ABC):
    @abstractmethod
    async def list_records(self) -> tuple[YoutubePerformanceRecord, ...]:
        raise NotImplementedError

    @abstractmethod
    async def save(self, record: YoutubePerformanceRecord) -> None:
        raise NotImplementedError
