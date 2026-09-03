from __future__ import annotations

import io
from dataclasses import replace

from PIL import Image

from core.application.services.structured_mark_validation_service import (
    StructuredMarkValidationService,
    project_anchor,
)
from core.domain.entities.character_bible import CharacterBible
from core.domain.entities.character_golden_set import (
    GoldenCandidateResult,
    GoldenTestCase,
)
from core.domain.entities.direction_bible import VisualStyleBible
from core.domain.exceptions import GoldenSetValidationError
from core.domain.ports.golden_set_evaluator_port import GoldenSetEvaluatorPort
from core.domain.ports.head_region_port import HeadRegionPort
from core.domain.ports.storage_port import StoragePort


class GuardedGoldenSetEvaluator(GoldenSetEvaluatorPort):
    """Add deterministic identity-mark gates to a human/vision evaluator."""

    def __init__(
        self,
        *,
        human_evaluator: GoldenSetEvaluatorPort,
        storage: StoragePort,
        head_region_provider: HeadRegionPort,
        mark_validator: StructuredMarkValidationService,
    ) -> None:
        self._human = human_evaluator
        self._storage = storage
        self._head = head_region_provider
        self._mark_validator = mark_validator

    async def evaluate(
        self,
        *,
        character: CharacterBible,
        style: VisualStyleBible,
        test_case: GoldenTestCase,
        storage_key: str,
    ) -> GoldenCandidateResult:
        result = await self._human.evaluate(
            character=character,
            style=style,
            test_case=test_case,
            storage_key=storage_key,
        )
        marks = tuple(character.identity_constraints.structured_marks)
        if not marks or not test_case.marker_validation_required:
            return replace(
                result,
                critical=test_case.critical,
                marker_gate_passed=True,
                structured_mark_reports=(),
            )

        image_bytes = await self._storage.load(storage_key)
        head = await self._head.detect(image_bytes)
        if head is None:
            raise GoldenSetValidationError(
                f"No head region detected for {storage_key}; "
                "structured-mark gate is fail-closed."
            )
        with Image.open(io.BytesIO(image_bytes)) as source:
            image = source.convert("RGB").copy()

        reports = []
        blocked = False
        for mark in marks:
            if mark.anchor is None:
                continue
            root = project_anchor(mark.anchor, head.bbox)
            report = self._mark_validator.validate(image, mark, head.bbox, root)
            reports.append(report)
            if mark.enforcement in {"seal", "both"} and not report.passed:
                blocked = True
        return replace(
            result,
            critical=test_case.critical,
            structured_mark_reports=tuple(reports),
            marker_gate_passed=not blocked,
        )
