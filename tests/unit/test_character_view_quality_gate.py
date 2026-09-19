from __future__ import annotations

import io

from PIL import Image, ImageDraw

from core.application.services.character_view_quality_gate import (
    CharacterViewQualityGate,
)
from core.application.services.view_framing_gate import FramingReport
from core.domain.ports.character_view_detector_port import CharacterViewDetectorPort
from core.domain.value_objects.character_creation_brief import CharacterSignatureMark
from core.domain.value_objects.character_view_qc import CharacterViewObservation


class Detector(CharacterViewDetectorPort):
    def __init__(self, observation: CharacterViewObservation) -> None:
        self.observation = observation

    async def inspect(self, *, image_bytes: bytes, expected_view: str):
        del image_bytes, expected_view
        return self.observation


class Framing:
    def __init__(self, passed: bool = True, reason: str | None = None) -> None:
        self.passed = passed
        self.reason = reason

    def evaluate(self, *, image_bytes: bytes, view: str):
        del image_bytes, view
        return FramingReport(
            passed=self.passed,
            reason=self.reason or ("ok" if self.passed else "feet cropped"),
            metrics={"bottom": 0.8},
        )


def observation(**changes) -> CharacterViewObservation:
    values = {
        "person_count": 1,
        "face_count": 1,
        "head_inside_frame": True,
        "feet_inside_frame": True,
        "orientation": "front",
        "confidence": 0.95,
        "provider": "test",
    }
    values.update(changes)
    return CharacterViewObservation(**values)


def marked_image(*, duplicate: bool = False) -> bytes:
    image = Image.new("RGB", (100, 100), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((60, 8, 66, 30), fill="#0047AB")
    if duplicate:
        draw.rectangle((34, 8, 40, 30), fill="#0047AB")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


async def test_gate_rejects_multiple_characters():
    gate = CharacterViewQualityGate(
        Detector(observation(person_count=2)), framing_gate=Framing()
    )

    report = await gate.evaluate(image_bytes=b"png", view="FRONT", seed=10)

    assert not report.passed
    assert "person_count_2" in report.reasons


async def test_gate_rejects_wrong_profile_orientation():
    gate = CharacterViewQualityGate(
        Detector(observation(orientation="front")), framing_gate=Framing()
    )

    report = await gate.evaluate(
        image_bytes=b"png", view="PROFILE_LEFT", seed=10
    )

    assert not report.passed
    assert "orientation_front_expected_profile_left" in report.reasons


async def test_same_side_three_quarter_reading_is_advisory_for_a_profile():
    # The detector cannot separate a strict anime side view from a
    # three-quarter view: it reads human-confirmed profiles as three_quarter.
    # That reading is evidence for the operator, not a rejection.
    gate = CharacterViewQualityGate(
        Detector(observation(orientation="three_quarter_left")),
        framing_gate=Framing(),
    )

    report = await gate.evaluate(
        image_bytes=b"png", view="PROFILE_LEFT", seed=10
    )

    assert report.passed
    assert report.reasons == ()
    assert report.checks["expected_orientation"] is True
    assert report.checks["profile_orientation_advisory"] is True


async def test_a_profile_read_as_the_opposite_side_still_fails():
    gate = CharacterViewQualityGate(
        Detector(observation(orientation="three_quarter_right")),
        framing_gate=Framing(),
    )

    report = await gate.evaluate(
        image_bytes=b"png", view="PROFILE_LEFT", seed=10
    )

    assert not report.passed
    assert "orientation_three_quarter_right_expected_profile_left" in report.reasons
    assert report.checks["profile_orientation_advisory"] is False


async def test_a_three_quarter_view_read_as_a_profile_still_fails():
    gate = CharacterViewQualityGate(
        Detector(observation(orientation="profile_left")),
        framing_gate=Framing(),
    )

    report = await gate.evaluate(
        image_bytes=b"png", view="THREE_QUARTER_LEFT", seed=10
    )

    assert not report.passed
    assert "orientation_profile_left_expected_three_quarter_left" in report.reasons


async def test_gate_rejects_any_face_in_back_view():
    gate = CharacterViewQualityGate(
        Detector(observation(face_count=1, orientation="back")),
        framing_gate=Framing(),
    )

    report = await gate.evaluate(image_bytes=b"png", view="BACK", seed=10)

    assert not report.passed
    assert "face_detected_in_back_view" in report.reasons


async def test_gate_requires_full_body_framing():
    gate = CharacterViewQualityGate(
        Detector(observation()), framing_gate=Framing(passed=False)
    )

    report = await gate.evaluate(image_bytes=b"png", view="FRONT", seed=10)

    assert not report.passed
    assert any(reason.startswith("framing_") for reason in report.reasons)


async def test_gate_reports_feet_outside_frame_not_feet_inside_frame():
    gate = CharacterViewQualityGate(
        Detector(observation(feet_inside_frame=False)), framing_gate=Framing()
    )

    report = await gate.evaluate(image_bytes=b"png", view="FRONT", seed=10)

    assert not report.passed
    assert "feet_outside_frame" in report.reasons
    assert "feet_inside_frame" not in report.reasons
    assert report.to_dict()["feet_inside_frame"] is False


async def test_back_view_ignores_wide_floor_artifact_when_all_detectors_pass():
    gate = CharacterViewQualityGate(
        Detector(observation(face_count=0, orientation="back")),
        framing_gate=Framing(
            passed=False,
            reason="bottom silhouette is a single wide mass; floor reflection",
        ),
    )

    report = await gate.evaluate(image_bytes=b"png", view="BACK", seed=10)

    assert report.passed
    assert report.checks["framing"] is True


async def test_directional_view_ignores_wide_background_when_detectors_pass():
    gate = CharacterViewQualityGate(
        Detector(observation(orientation="three_quarter_right")),
        framing_gate=Framing(
            passed=False,
            reason="bottom silhouette is a single wide mass; studio gradient",
        ),
    )

    report = await gate.evaluate(
        image_bytes=b"png", view="THREE_QUARTER_RIGHT", seed=10
    )

    assert report.passed
    assert report.checks["framing"] is True


async def test_design_gate_accepts_one_signature_mark_on_character_left():
    gate = CharacterViewQualityGate(
        Detector(observation(face_bbox=(0.2, 0.05, 0.8, 0.55))),
        framing_gate=Framing(),
    )

    report = await gate.evaluate_design_candidate(
        image_bytes=marked_image(),
        seed=10,
        signature_marks=(
            CharacterSignatureMark(
                "single cobalt streak",
                count=1,
                character_side="left",
                colour="#0047AB",
            ),
        ),
    )

    assert report.passed


async def test_design_gate_defers_signature_mark_fidelity_to_human_review():
    # The design-candidate stage is a pre-human selection grid; mark fidelity
    # (duplicate streak, mirror side) is enforced by the signed human
    # acceptance list at view-pack approval, not by this structural gate.
    gate = CharacterViewQualityGate(
        Detector(observation(face_bbox=(0.2, 0.05, 0.8, 0.55))),
        framing_gate=Framing(),
    )

    report = await gate.evaluate_design_candidate(
        image_bytes=marked_image(duplicate=True),
        seed=10,
        signature_marks=(
            CharacterSignatureMark(
                "single cobalt streak",
                count=1,
                character_side="left",
                colour="#0047AB",
            ),
        ),
    )

    assert report.passed
    assert not any(
        reason.startswith("signature_mark_") for reason in report.reasons
    )


async def test_design_gate_rejects_duplicate_faces_as_collage():
    gate = CharacterViewQualityGate(
        Detector(observation(face_count=2)),
        framing_gate=Framing(),
    )

    report = await gate.evaluate_design_candidate(
        image_bytes=marked_image(duplicate=True),
        seed=10,
        signature_marks=(
            CharacterSignatureMark(
                "single cobalt streak",
                count=1,
                character_side="left",
                colour="#0047AB",
            ),
        ),
    )

    assert not report.passed
    assert "face_count_2" in report.reasons


async def test_face_closeup_rejects_duplicated_signature_mark():
    gate = CharacterViewQualityGate(
        Detector(observation(face_bbox=(0.2, 0.05, 0.8, 0.55))),
        framing_gate=Framing(),
    )

    report = await gate.evaluate(
        image_bytes=marked_image(duplicate=True),
        view="FACE_CLOSEUP",
        seed=10,
        signature_marks=(
            CharacterSignatureMark(
                "single cobalt streak",
                count=1,
                character_side="left",
                colour="#0047AB",
            ),
        ),
    )

    assert not report.passed
    assert "signature_mark_1_component_count" in report.reasons
