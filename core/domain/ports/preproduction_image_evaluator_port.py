from __future__ import annotations

from abc import ABC, abstractmethod

from core.domain.value_objects.preproduction_image_quality import (
    PreproductionImageQuality,
)


class PreproductionImageEvaluatorPort(ABC):
    """Evaluate a generated still without granting human approval."""

    @abstractmethod
    async def evaluate(
        self,
        *,
        image_bytes: bytes,
        reference_bytes: bytes | None,
        context: str,
        subject_policy: str,
    ) -> PreproductionImageQuality:
        raise NotImplementedError
