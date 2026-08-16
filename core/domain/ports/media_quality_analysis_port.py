"""Port for content-level analysis of a completed media file."""
from __future__ import annotations

from abc import ABC, abstractmethod

from core.domain.value_objects.media_quality_signals import MediaQualitySignals


class MediaQualityAnalysisPort(ABC):
    @abstractmethod
    async def analyze(self, video_path: str) -> MediaQualitySignals:
        raise NotImplementedError
