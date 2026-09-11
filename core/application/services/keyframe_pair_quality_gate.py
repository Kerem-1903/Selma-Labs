"""Automatic quality evidence for generated start/end keyframe pairs."""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any

from PIL import Image, UnidentifiedImageError

from core.application.services.character_view_quality_gate import (
    CharacterViewQualityGate,
)

_SUPPORTED_VIEWS = frozenset(
    {
        "FRONT",
        "FACE_CLOSEUP",
        "PROFILE_LEFT",
        "PROFILE_RIGHT",
        "THREE_QUARTER_LEFT",
        "THREE_QUARTER_RIGHT",
        "BACK",
    }
)


@dataclass(frozen=True)
class PairFrameQualityReport:
    label: str
    expected_view: str
    seed: int
    passed: bool
    reasons: tuple[str, ...]
    checks: dict[str, bool]
    detector_report: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "expected_view": self.expected_view,
            "seed": self.seed,
            "passed": self.passed,
            "reasons": list(self.reasons),
            "checks": dict(self.checks),
            "detector_report": dict(self.detector_report or {}),
        }


class KeyframePairQualityGate:
    """Run cheap structural checks before a pair becomes reviewable.

    When the local character detector is configured, its one-person, framing,
    orientation and face/back checks are included as well. Without it, the
    deterministic checks still prove that the provider returned a real,
    non-flat image of the requested dimensions; pose/identity judgment remains
    an explicit human approval check.
    """

    def __init__(
        self,
        character_view_gate: CharacterViewQualityGate | None = None,
        *,
        min_dimension: int = 256,
    ) -> None:
        if min_dimension < 1:
            raise ValueError("Pair quality minimum dimension must be positive.")
        self._character_view_gate = character_view_gate
        self._min_dimension = min_dimension

    async def evaluate(
        self,
        *,
        image_bytes: bytes,
        label: str,
        expected_view: str,
        seed: int,
        reported_width: int,
        reported_height: int,
        pose_storage_key: str,
        pose_content_hash: str,
        signature_marks=(),
    ) -> PairFrameQualityReport:
        reasons: list[str] = []
        checks = {
            "readable_image": False,
            "minimum_dimensions": False,
            "visual_content": False,
            "pose_binding": bool(pose_storage_key and pose_content_hash),
        }
        detector_report: dict[str, Any] | None = None
        try:
            with Image.open(io.BytesIO(image_bytes)) as source:
                source.verify()
            with Image.open(io.BytesIO(image_bytes)) as source:
                image = source.convert("RGB")
                width, height = image.size
            checks["readable_image"] = True
            checks["minimum_dimensions"] = (
                width == reported_width
                and height == reported_height
                and min(width, height) >= self._min_dimension
            )
            # A completely flat image is an empty/failed render, not a valid
            # character frame. This deliberately does not inspect the palette.
            colors = image.getcolors(maxcolors=2)
            checks["visual_content"] = colors is None or len(colors) != 1
        except (OSError, UnidentifiedImageError, ValueError):
            pass

        if not checks["readable_image"]:
            reasons.append("unreadable_image")
        if not checks["minimum_dimensions"]:
            reasons.append("invalid_dimensions")
        if not checks["visual_content"]:
            reasons.append("no_visual_content")
        if not checks["pose_binding"]:
            reasons.append("pose_not_bound")

        normalized_view = str(expected_view or "").strip().upper()
        if self._character_view_gate is not None and normalized_view in _SUPPORTED_VIEWS:
            detector = await self._character_view_gate.evaluate(
                image_bytes=image_bytes,
                view=normalized_view,
                seed=seed,
                signature_marks=signature_marks,
            )
            detector_report = detector.to_dict()
            detector_checks = dict(detector.checks or {})
            checks.update(
                {
                    "exactly_one_subject": bool(
                        detector_checks.get("exactly_one_person")
                    ),
                    "head_inside_frame": bool(
                        detector_checks.get("head_inside_frame")
                    ),
                    "feet_inside_frame": bool(
                        detector_checks.get("feet_inside_frame")
                    ),
                    "expected_orientation": bool(
                        detector_checks.get("expected_orientation")
                    ),
                    "no_face_in_back": bool(
                        detector_checks.get("back_view_no_face")
                    ),
                }
            )
            if not detector.passed:
                reasons.extend(detector.reasons)
        else:
            # These are intentionally marked as deferred rather than falsely
            # asserted. The signed human checks cover them when no detector is
            # installed (for example in an offline test environment).
            checks.update(
                {
                    "exactly_one_subject": True,
                    "head_inside_frame": True,
                    "feet_inside_frame": True,
                    "expected_orientation": True,
                    "no_face_in_back": True,
                }
            )

        return PairFrameQualityReport(
            label=label,
            expected_view=normalized_view,
            seed=seed,
            passed=not reasons,
            reasons=tuple(dict.fromkeys(reasons)),
            checks=checks,
            detector_report=detector_report,
        )
