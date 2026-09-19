from abc import ABC, abstractmethod

from core.domain.entities.media_asset import MediaAsset


class FrameExtractionPort(ABC):
    @abstractmethod
    async def extract_frames(self, asset: MediaAsset, count: int) -> list[bytes]:
        pass
