from __future__ import annotations

from types import SimpleNamespace

import pytest

from infrastructure.providers.vision.ultralytics_character_view_detector import (
    UltralyticsCharacterViewDetector,
)


def _pose_result(
    *,
    nose_x: float,
    eye_x: tuple[float, float],
    ear_x: tuple[float, float],
    confidences: tuple[float, float, float, float, float] = (
        0.95,
        0.90,
        0.90,
        0.85,
        0.85,
    ),
):
    coordinates = [
        [nose_x, 20.0],
        [eye_x[0], 25.0],
        [eye_x[1], 25.0],
        [ear_x[0], 30.0],
        [ear_x[1], 30.0],
    ]
    confidences = [list(confidences)]
    return SimpleNamespace(
        keypoints=SimpleNamespace(xy=[coordinates], conf=confidences)
    )


def test_orientation_uses_keypoint_coordinates_for_right_profile():
    result = _pose_result(
        nose_x=80.0,
        eye_x=(50.0, 55.0),
        ear_x=(42.0, 46.0),
        confidences=(0.95, 0.90, 0.10, 0.85, 0.10),
    )

    orientation, confidence = UltralyticsCharacterViewDetector._orientation(
        result, face_count=1
    )

    assert orientation == "profile_right"
    assert confidence > 0.8


def test_orientation_uses_keypoint_coordinates_for_left_profile():
    result = _pose_result(
        nose_x=20.0,
        eye_x=(45.0, 50.0),
        ear_x=(54.0, 58.0),
        confidences=(0.95, 0.10, 0.90, 0.10, 0.85),
    )

    orientation, _confidence = UltralyticsCharacterViewDetector._orientation(
        result, face_count=1
    )

    assert orientation == "profile_left"


def test_orientation_does_not_treat_confidence_values_as_coordinates():
    result = _pose_result(
        nose_x=50.0,
        eye_x=(48.0, 52.0),
        ear_x=(47.0, 53.0),
    )

    orientation, _confidence = UltralyticsCharacterViewDetector._orientation(
        result, face_count=1
    )

    assert orientation == "front"


def test_missing_face_detection_overrides_hallucinated_pose_face_keypoints():
    result = _pose_result(
        nose_x=80.0,
        eye_x=(50.0, 55.0),
        ear_x=(42.0, 46.0),
    )

    orientation, confidence = UltralyticsCharacterViewDetector._orientation(
        result, face_count=0
    )

    assert orientation == "back"
    assert confidence == 1.0


def _torso_result(
    *, shoulder_width: float, hip_width: float, torso_height: float
) -> SimpleNamespace:
    """A full 17-keypoint COCO result; only shoulders and hips are occupied."""
    centre = 500.0
    coordinates = [[centre, 200.0] for _ in range(17)]
    coordinates[5] = [centre - shoulder_width / 2, 200.0]
    coordinates[6] = [centre + shoulder_width / 2, 200.0]
    coordinates[11] = [centre - hip_width / 2, 200.0 + torso_height]
    coordinates[12] = [centre + hip_width / 2, 200.0 + torso_height]
    confidences = [0.0] * 17
    for index in (5, 6, 11, 12):
        confidences[index] = 0.9
    return SimpleNamespace(
        keypoints=SimpleNamespace(xy=[coordinates], conf=[confidences])
    )


def test_torso_foreshortening_reports_body_yaw_as_a_ratio():
    """Facial keypoints read a true profile as a three-quarter view, so body
    foreshortening is the only yaw axis this art style leaves measurable."""
    frontal = UltralyticsCharacterViewDetector._torso_foreshortening(
        _torso_result(shoulder_width=140.0, hip_width=100.0, torso_height=250.0)
    )
    turned = UltralyticsCharacterViewDetector._torso_foreshortening(
        _torso_result(shoulder_width=40.0, hip_width=30.0, torso_height=250.0)
    )

    assert frontal == pytest.approx(140.0 / 250.0)
    assert turned == pytest.approx(40.0 / 250.0)
    assert turned < frontal


def test_torso_foreshortening_declines_rather_than_guessing():
    """Unmeasurable frames must report nothing: a missing value is honest
    evidence, a fabricated one would be read as a clean measurement."""
    weak = _torso_result(shoulder_width=140.0, hip_width=100.0, torso_height=250.0)
    weak.keypoints.conf = [[0.1] * 17]
    shoulders_overlapping = _torso_result(
        shoulder_width=140.0, hip_width=100.0, torso_height=0.0
    )
    face_only = _pose_result(nose_x=80.0, eye_x=(50.0, 55.0), ear_x=(42.0, 46.0))

    assert UltralyticsCharacterViewDetector._torso_foreshortening(weak) is None
    assert (
        UltralyticsCharacterViewDetector._torso_foreshortening(shoulders_overlapping)
        is None
    )
    assert UltralyticsCharacterViewDetector._torso_foreshortening(face_only) is None
