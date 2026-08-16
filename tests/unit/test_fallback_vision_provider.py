from __future__ import annotations

import pytest

from core.domain.exceptions import ProviderError
from core.domain.value_objects.vision_analysis_result import VisionAnalysisResult
from infrastructure.providers.vision.fallback_vision_provider import (
    FallbackVisionProvider,
)


class _Vision:
    def __init__(self, identity: str, *, fail: bool = False) -> None:
        self.provider_identity = identity
        self.fail = fail
        self.calls = 0

    async def analyze(self, frame_bytes, scene_context):
        del frame_bytes, scene_context
        self.calls += 1
        if self.fail:
            raise ProviderError("quota exhausted")
        return VisionAnalysisResult(
            relevance_score=0.9,
            scene_type="ocean",
            lighting="natural",
            dominant_colors=["blue"],
            indoors=False,
            outdoors=True,
            camera_motion="steady",
            people_present=False,
            vehicles_present=False,
            confidence=0.9,
        )


@pytest.mark.asyncio
async def test_fallback_vision_trips_circuit_after_primary_failure():
    primary = _Vision("primary", fail=True)
    fallback = _Vision("fallback")
    provider = FallbackVisionProvider(primary, fallback)

    await provider.analyze([b"frame"], "first")
    await provider.analyze([b"frame"], "second")

    assert primary.calls == 1
    assert fallback.calls == 2
