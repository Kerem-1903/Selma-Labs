from __future__ import annotations

from abc import ABC, abstractmethod

from core.domain.value_objects.trend_video import TrendVideo


class TrendSourcePort(ABC):
    @property
    @abstractmethod
    def provider_identity(self) -> str:
        raise NotImplementedError

    @abstractmethod
    async def fetch(
        self,
        *,
        region_code: str,
        category_ids: list[str],
        max_results_per_category: int,
    ) -> list[TrendVideo]:
        raise NotImplementedError
