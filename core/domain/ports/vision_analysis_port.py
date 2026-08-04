from abc import ABC, abstractmethod
from typing import List

from core.domain.value_objects.vision_analysis_result import VisionAnalysisResult


class VisionAnalysisPort(ABC):
    @abstractmethod
    async def analyze(self, frame_bytes: List[bytes], scene_context: str) -> VisionAnalysisResult:
        pass

    @property
    @abstractmethod
    def provider_identity(self) -> str:
        pass
