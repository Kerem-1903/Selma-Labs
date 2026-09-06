"""Fail-closed automatic QC for the seven canonical character views."""

from __future__ import annotations

import io
import re

from PIL import Image

from core.application.services.structured_mark_validation_service import (
    StructuredMarkValidationService,
    project_anchor,
)
from core.application.services.view_framing_gate import ViewFramingGate
from core.domain.ports.character_view_detector_port import CharacterViewDetectorPort
from core.domain.value_objects.character_creation_brief import CharacterSignatureMark
from core.domain.value_objects.character_view_qc import CharacterViewQcReport
from core.domain.value_objects.structured_mark import MarkAnchor, StructuredMark


class CharacterViewQualityGate:
    def __init__(
        self,
        detector: CharacterViewDetectorPort,
        *,
        framing_gate: ViewFramingGate | None = None,
        mark_validator: StructuredMarkValidationService | None = None,
    ) -> None:
        self._detector = detector
        self._framing_gate = framing_gate or ViewFramingGate()
        self._mark_validator = mark_validator or StructuredMarkValidationService(
            anchor_tolerance_ratio=0.45
        )

    async def evaluate(
        self,
        *,
        image_bytes: bytes,
        view: str,
        seed: int,
        signature_marks: tuple[CharacterSignatureMark, ...] = (),
    ) -> CharacterViewQcReport:
        observation = await self._detector.inspect(
            image_bytes=image_bytes, expected_view=view
        )
        reasons: list[str] = []
        if observation.person_count != 1:
            reasons.append(f"person_count_{observation.person_count}")
        if not observation.head_inside_frame:
            reasons.append("head_outside_frame")
        if view != "FACE_CLOSEUP" and not observation.feet_inside_frame:
            reasons.append("feet_outside_frame")

        expected_orientation = {
            "FRONT": "front",
            "FACE_CLOSEUP": "front",
            "PROFILE_LEFT": "profile_left",
            "PROFILE_RIGHT": "profile_right",
            "THREE_QUARTER_LEFT": "three_quarter_left",
            "THREE_QUARTER_RIGHT": "three_quarter_right",
            "BACK": "back",
        }[view]
        if observation.orientation != expected_orientation:
            reasons.append(
                f"orientation_{observation.orientation}_expected_{expected_orientation}"
            )
        if view == "BACK" and observation.face_count > 0:
            reasons.append("face_detected_in_back_view")

        framing = self._framing_gate.evaluate(image_bytes=image_bytes, view=view)
        if not framing.passed:
            reasons.append(f"framing_{self._reason_key(framing.reason)}")
        signature_reasons: list[str] = []
        if view == "FACE_CLOSEUP":
            signature_reasons = self._signature_mark_reasons(
                image_bytes=image_bytes,
                face_bbox=observation.face_bbox,
                marks=signature_marks,
            )
            reasons.extend(signature_reasons)
        return CharacterViewQcReport(
            view=view,
            seed=seed,
            passed=not reasons,
            reasons=tuple(dict.fromkeys(reasons)),
            observation=observation,
            framing_metrics=framing.metrics,
            checks={
                "exactly_one_person": observation.person_count == 1,
                "head_inside_frame": observation.head_inside_frame,
                "feet_inside_frame": (
                    view == "FACE_CLOSEUP" or observation.feet_inside_frame
                ),
                "expected_orientation": observation.orientation
                == expected_orientation,
                "back_view_no_face": view != "BACK" or observation.face_count == 0,
                "signature_mark_face_closeup": (
                    view != "FACE_CLOSEUP" or not signature_reasons
                ),
                "framing": framing.passed,
            },
        )

    async def evaluate_design_candidate(
        self,
        *,
        image_bytes: bytes,
        seed: int,
        signature_marks: tuple[CharacterSignatureMark, ...] = (),
    ) -> CharacterViewQcReport:
        """Reject gross structural failures only; leave design judgment to humans.

        The design-candidate stage is a pre-human selection grid: the operator
        chooses the canonical source among a few candidates, so this gate only
        filters duplicates/collages and unusable crops. Per-pixel fidelity
        checks (signature marks, leg separation, mirror side) are deliberately
        NOT enforced here — they belong to the seven-view QC stage and to the
        signed human acceptance list (view-pack approval), which is where the
        character's identity rules are locked.
        """
        del signature_marks
        observation = await self._detector.inspect(
            image_bytes=image_bytes, expected_view="FRONT"
        )
        reasons: list[str] = []
        if observation.person_count != 1:
            reasons.append(f"person_count_{observation.person_count}")
        if observation.face_count != 1:
            reasons.append(f"face_count_{observation.face_count}")
        if not observation.head_inside_frame:
            reasons.append("head_outside_frame")
        if not observation.feet_inside_frame:
            reasons.append("feet_outside_frame")
        return CharacterViewQcReport(
            view="DESIGN_CANDIDATE",
            seed=seed,
            passed=not reasons,
            reasons=tuple(dict.fromkeys(reasons)),
            observation=observation,
            framing_metrics={},
            checks={
                "exactly_one_person": observation.person_count == 1,
                "exactly_one_face": observation.face_count == 1,
                "head_inside_frame": observation.head_inside_frame,
                "feet_inside_frame": observation.feet_inside_frame,
            },
        )

    def _signature_mark_reasons(
        self,
        *,
        image_bytes: bytes,
        face_bbox: tuple[float, float, float, float] | None,
        marks: tuple[CharacterSignatureMark, ...],
    ) -> list[str]:
        enforceable = [
            mark
            for mark in marks
            if mark.character_side in {"left", "right"}
            and re.fullmatch(r"#[0-9A-Fa-f]{6}", mark.colour)
        ]
        if not enforceable:
            return []
        if face_bbox is None:
            return ["signature_mark_head_not_localized"]
        with Image.open(io.BytesIO(image_bytes)) as opened:
            image = opened.convert("RGB").copy()
        width, height = image.size
        pixel_bbox = (
            max(0, round(face_bbox[0] * width)),
            max(0, round(face_bbox[1] * height)),
            min(width, round(face_bbox[2] * width)),
            min(height, round(face_bbox[3] * height)),
        )
        if pixel_bbox[0] >= pixel_bbox[2] or pixel_bbox[1] >= pixel_bbox[3]:
            return ["signature_mark_head_bbox_invalid"]
        reasons: list[str] = []
        for index, source in enumerate(enforceable, start=1):
            # A character's left is the viewer's right in a front view.
            viewer_side = "viewer_right" if source.character_side == "left" else "viewer_left"
            x_center = 0.72 if viewer_side == "viewer_right" else 0.28
            mark = StructuredMark(
                id=f"brief-mark-{index}",
                label=source.label,
                color_hex=source.colour,
                viewer_side=viewer_side,
                count=source.count,
                color_tolerance_delta_e=24.0,
                anchor=MarkAnchor(
                    region="front-hairline",
                    x_center=x_center,
                    y_root=0.08,
                    extent=0.35,
                ),
                mirror_side="viewer_left" if viewer_side == "viewer_right" else "viewer_right",
            )
            report = self._mark_validator.validate(
                image=image,
                mark=mark,
                head_bbox=pixel_bbox,
                expected_root_xy=project_anchor(mark.anchor, pixel_bbox),
            )
            if not report.passed:
                for failure in report.failures:
                    reasons.append(f"signature_mark_{index}_{failure}")
        return reasons

    @staticmethod
    def _reason_key(reason: str) -> str:
        return "_".join(
            "".join(character for character in word if character.isalnum())
            for word in reason.casefold().split()
        )[:80]
