"""Circuit-breaking fallback for vision-provider availability failures."""
from __future__ import annotations

import asyncio

from core.domain.exceptions import ProviderError
from core.domain.ports.vision_analysis_port import VisionAnalysisPort
from core.domain.value_objects.vision_analysis_result import VisionAnalysisResult


class FallbackVisionProvider(VisionAnalysisPort):
    def __init__(self, primary: VisionAnalysisPort, fallback: VisionAnalysisPort) -> None:
        self._primary = primary
        self._fallback = fallback
        self._primary_unavailable = False
        self._lock = asyncio.Lock()

    @property
    def provider_identity(self) -> str:
        return f"fallback:{self._primary.provider_identity}->{self._fallback.provider_identity}"

    async def analyze(
        self,
        frame_bytes: list[bytes],
        scene_context: str,
    ) -> VisionAnalysisResult:
        async with self._lock:
            use_fallback = self._primary_unavailable
        if not use_fallback:
            try:
                return await self._primary.analyze(frame_bytes, scene_context)
            except ProviderError:
                async with self._lock:
                    self._primary_unavailable = True
        return await self._fallback.analyze(frame_bytes, scene_context)
