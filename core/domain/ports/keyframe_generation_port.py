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

    @property
    def edit_contract(self) -> str:
        """Source-led edit contract this engine implements, or ``''``.

        Declared rather than inferred. Two things need it: a capability router
        must know an engine cannot serve a source-led edit workload, and a
        tournament must know every variant implements the *same* prompt
        contract before it compares their numbers. Engines that do not do
        source-led editing inherit the empty default and are unaffected.
        """
        return ""

    @abstractmethod
    async def generate_keyframe(
        self, request: KeyframeGenerationRequest
    ) -> GeneratedKeyframe:
        raise NotImplementedError
