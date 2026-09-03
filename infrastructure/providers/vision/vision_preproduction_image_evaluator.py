"""Vision-backed automatic gate for character and background candidates."""

from __future__ import annotations

from core.domain.ports.preproduction_image_evaluator_port import (
    PreproductionImageEvaluatorPort,
)
from core.domain.ports.vision_analysis_port import VisionAnalysisPort
from core.domain.value_objects.preproduction_image_quality import (
    PreproductionImageQuality,
)


class VisionPreproductionImageEvaluator(PreproductionImageEvaluatorPort):
    def __init__(self, vision: VisionAnalysisPort, *, threshold: float = 0.72) -> None:
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("Quality threshold must be between 0 and 1.")
        self._vision = vision
        self._threshold = threshold

    async def evaluate(
        self,
        *,
        image_bytes: bytes,
        reference_bytes: bytes | None,
        context: str,
        subject_policy: str,
    ) -> PreproductionImageQuality:
        frames = [image_bytes]
        if reference_bytes is not None:
            frames.insert(0, reference_bytes)
        analysis = await self._vision.analyze(
            frames,
            context
            + "\nReject identity/geometry drift, malformed anatomy, crop errors, "
            "text, logos and watermarks. Compare the first image as the approved "
            "reference when two images are supplied.",
        )
        issues: list[str] = []
        if analysis.text_present:
            issues.append("text_present")
        if analysis.logo_present:
            issues.append("logo_present")
        if subject_policy == "character_required" and not analysis.people_present:
            issues.append("character_missing")
        if subject_policy == "character_forbidden" and analysis.people_present:
            issues.append("character_present")

        identity_or_geometry = self._clamp(analysis.relevance_score)
        composition = self._clamp(analysis.confidence)
        subject_score = (
            0.0
            if any(
                issue in {"character_missing", "character_present"} for issue in issues
            )
            else 1.0
        )
        score = self._clamp(
            identity_or_geometry * 0.55 + composition * 0.25 + subject_score * 0.20
        )
        return PreproductionImageQuality(
            score=score,
            threshold=self._threshold,
            passed=score >= self._threshold and not issues,
            identity_or_geometry_score=identity_or_geometry,
            composition_score=composition,
            subject_policy_score=subject_score,
            confidence=self._clamp(analysis.confidence),
            issues=tuple(issues),
            provider=self._vision.provider_identity,
        )

    @staticmethod
    def _clamp(value: float) -> float:
        return max(0.0, min(1.0, float(value)))
