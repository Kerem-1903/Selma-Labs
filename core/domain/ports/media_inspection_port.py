from __future__ import annotations

from abc import ABC, abstractmethod

from core.domain.value_objects.media_inspection import MediaInspection


class MediaInspectionPort(ABC):
    @abstractmethod
    async def inspect(self, video_path: str) -> MediaInspection:
        raise NotImplementedError

    @abstractmethod
    async def extract_frame(
        self, video_path: str, output_path: str, timestamp_seconds: float
    ) -> None:
        raise NotImplementedError
