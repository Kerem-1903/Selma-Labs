from __future__ import annotations

from abc import ABC, abstractmethod

from core.domain.value_objects.generated_depth_map import GeneratedDepthMap


class DepthMapGeneratorPort(ABC):
    """Boundary for a real monocular-depth or segmentation provider."""

    @abstractmethod
    async def generate_depth_map(self, image_bytes: bytes) -> GeneratedDepthMap:
        raise NotImplementedError
