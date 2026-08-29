from __future__ import annotations

from abc import ABC, abstractmethod

from core.domain.value_objects.generated_keyframe import GeneratedKeyframe
from core.domain.value_objects.keyframe_generation_request import KeyframeGenerationRequest


class KeyframeGenerationPort(ABC):
    """Boundary for local or remote still-image generation engines."""

    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError
    @abstractmethod
    async def generate_keyframe(
        self, request: KeyframeGenerationRequest
    ) -> GeneratedKeyframe:
        raise NotImplementedError
