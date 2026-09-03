from __future__ import annotations

import asyncio

from core.domain.value_objects.vision_analysis_result import VisionAnalysisResult
from infrastructure.providers.vision.vision_preproduction_image_evaluator import (
    VisionPreproductionImageEvaluator,
)


class _Vision:
    provider_identity = "fake:vision"

    def __init__(self, *, people_present: bool) -> None:
        self.people_present = people_present

    async def analyze(self, _frames, _context):
        return VisionAnalysisResult(
            relevance_score=0.9,
            scene_type="anime environment",
            lighting="cinematic",
            dominant_colors=["blue"],
            indoors=False,
            outdoors=True,
            camera_motion="static",
            people_present=self.people_present,
            vehicles_present=False,
            confidence=0.9,
        )


def test_background_policy_rejects_people():
    evaluator = VisionPreproductionImageEvaluator(_Vision(people_present=True))

    result = asyncio.run(
        evaluator.evaluate(
            image_bytes=b"image",
            reference_bytes=None,
            context="empty location",
            subject_policy="character_forbidden",
        )
    )

    assert result.passed is False
    assert result.issues == ("character_present",)
