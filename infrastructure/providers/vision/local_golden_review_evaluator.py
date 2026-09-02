"""Human-reviewed JSON scores for deterministic Golden Set locking."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from core.domain.entities.character_golden_set import (
    GoldenCandidateResult,
    GoldenTestCase,
)
from core.domain.exceptions import GoldenSetValidationError
from core.domain.ports.golden_set_evaluator_port import GoldenSetEvaluatorPort


class LocalGoldenReviewEvaluator(GoldenSetEvaluatorPort):
    def __init__(self, review_manifest: str | Path) -> None:
        self._manifest = Path(review_manifest)

    async def evaluate(
        self, *, character, style, test_case: GoldenTestCase, storage_key: str
    ) -> GoldenCandidateResult:
        del character, style
        try:
            payload = await asyncio.to_thread(
                lambda: json.loads(self._manifest.read_text(encoding="utf-8"))
            )
            review = dict(payload["reviews"][test_case.scenario.value])
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
            KeyError,
            TypeError,
        ) as error:
            raise GoldenSetValidationError(
                f"Golden review for {test_case.scenario.value} is missing or invalid."
            ) from error
        return GoldenCandidateResult(
            scenario=test_case.scenario,
            storage_key=storage_key,
            identity_score=float(review["identity_score"]),
            style_score=float(review["style_score"]),
            anatomy_score=float(review["anatomy_score"]),
            human_approved=bool(review["human_approved"]),
            notes=str(review.get("notes", "")),
        )
