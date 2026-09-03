from __future__ import annotations

from abc import ABC, abstractmethod

from core.domain.value_objects.head_region import HeadRegion


class HeadRegionPort(ABC):
    @abstractmethod
    async def detect(self, image_bytes: bytes) -> HeadRegion | None:
        """Return the primary character head region, or None when absent."""
        raise NotImplementedError
