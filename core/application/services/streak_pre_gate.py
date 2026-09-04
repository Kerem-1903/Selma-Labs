"""Deterministic identity pre-gate that runs before the slow vision model.

The vision model (qwen2.5vl on an 8 GB GPU) costs roughly two minutes per
frame. Most identity failures are cheap to detect: a duplicated, mirrored, or
missing red hair streak is a pure color/geometry question that the calibrated
structured-mark validator answers in milliseconds. This gate runs that check
first so defective frames are quarantined without ever waking the model.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image

from core.application.services.structured_mark_validation_service import (
    StructuredMarkValidationService,
    project_anchor,
)
from core.domain.entities.character_bible import CharacterBible
from core.domain.value_objects.structured_mark import StructuredMark
from core.domain.value_objects.structured_mark_report import StructuredMarkReport

# Framings where the anchor's calibrated head zone transfers reliably to a
# generated frame. Live checks showed only true close-ups qualify: FRONT
# recipes render chest-up, so the close-up zone spills onto the torso and the
# deep-red jacket lining reads as extra streak components (7-8 detected) and
# false-rejects good frames. Angled profiles, front/upper-body, full-body,
# back, and action framings are owned by the vision model and human review.
HEAD_DOMINANT_VIEWS = frozenset({"FACE_CLOSEUP"})

BBox = tuple[float, float, float, float]


@dataclass(frozen=True)
class StreakPreGateResult:
    applicable: bool
    passed: bool | None
    reason: str
    report: StructuredMarkReport | None = None


class StreakPreGate:
    """Cheap, deterministic single-streak seal for guarded generation."""

    def __init__(
        self,
        mark_validator: StructuredMarkValidationService | None = None,
    ) -> None:
        self._validator = mark_validator or StructuredMarkValidationService()

    @classmethod
    def applicable_for(cls, view: str) -> bool:
        """Whether the calibrated zone is trustworthy for this framing."""
        return view in HEAD_DOMINANT_VIEWS

    @staticmethod
    def calibrated_mark(character: CharacterBible) -> StructuredMark | None:
        """The first sealed mark that carries a calibrated head bbox."""
        for mark in character.identity_constraints.structured_marks:
            if mark.head_bbox is not None and mark.anchor is not None:
                return mark
        return None

    def evaluate(
        self,
        image_bytes: bytes,
        mark: StructuredMark,
    ) -> StreakPreGateResult:
        if mark.head_bbox is None or mark.anchor is None:
            return StreakPreGateResult(
                applicable=False,
                passed=None,
                reason="structured mark has no calibrated head bbox",
            )
        with Image.open(io.BytesIO(image_bytes)) as opened:
            image = opened.convert("RGB").copy()
        width, height = image.size
        if width <= 0 or height <= 0:
            return StreakPreGateResult(
                applicable=False,
                passed=None,
                reason="generated frame has invalid dimensions",
            )
        left, top, right, bottom = mark.head_bbox
        bbox = (
            max(0, round(left * width)),
            max(0, round(top * height)),
            min(width, round(right * width)),
            min(height, round(bottom * height)),
        )
        if bbox[0] >= bbox[2] or bbox[1] >= bbox[3]:
            return StreakPreGateResult(
                applicable=False,
                passed=None,
                reason="calibrated head zone does not fit the generated frame",
            )
        expected_root = project_anchor(mark.anchor, bbox)
        report = self._validator.validate(
            image=image,
            mark=mark,
            head_bbox=bbox,
            expected_root_xy=expected_root,
        )
        return StreakPreGateResult(
            applicable=True,
            passed=report.passed,
            reason=self._describe(report),
            report=report,
        )

    @staticmethod
    def _describe(report: StructuredMarkReport) -> str:
        if report.passed:
            return (
                "single-streak check passed "
                f"(count {report.detected_count}, {report.actual_side}, "
                f"{report.matched_pixels}px)"
            )
        detail = ", ".join(report.failures) if report.failures else "unknown"
        return (
            "single-streak check failed "
            f"({detail}; detected count {report.detected_count}, "
            f"side {report.actual_side or 'n/a'})"
        )
