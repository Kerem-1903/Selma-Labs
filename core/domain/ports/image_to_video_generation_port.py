from __future__ import annotations

from abc import ABC, abstractmethod

from core.domain.value_objects.generated_video_clip import GeneratedVideoClip
from core.domain.value_objects.image_to_video_request import ImageToVideoRequest


class ImageToVideoGenerationPort(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError
    @abstractmethod
    async def generate_video(self, request: ImageToVideoRequest) -> GeneratedVideoClip:
        raise NotImplementedError
