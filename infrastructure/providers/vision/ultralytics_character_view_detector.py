"""Local YOLO person/face/pose detector for canonical character-view QC."""

from __future__ import annotations

import asyncio
import io
from pathlib import Path
from typing import Any

from PIL import Image

from core.domain.ports.character_view_detector_port import CharacterViewDetectorPort
from core.domain.value_objects.character_view_qc import CharacterViewObservation


class UltralyticsCharacterViewDetector(CharacterViewDetectorPort):
    def __init__(
        self,
        *,
        face_model: str,
        pose_model: str,
        confidence: float = 0.35,
    ) -> None:
        if not 0.0 < confidence < 1.0:
            raise ValueError("Character QC confidence must be between 0 and 1.")
        self._model_paths = {
            "face": face_model,
            "pose": pose_model,
        }
        self._confidence = confidence
        self._models: dict[str, Any] = {}

    def _model(self, role: str) -> Any:
        if role in self._models:
            return self._models[role]
        model_path = Path(self._model_paths[role]).expanduser()
        if not model_path.is_file():
            raise RuntimeError(
                f"Character QC {role} model was not found: {model_path}"
            )
        try:
            from ultralytics import YOLO
        except ImportError as error:
            raise RuntimeError(
                "Character view QC requires the ultralytics package."
            ) from error
        self._models[role] = YOLO(str(model_path))
        return self._models[role]

    async def inspect(
        self, *, image_bytes: bytes, expected_view: str
    ) -> CharacterViewObservation:
        del expected_view

        def run() -> CharacterViewObservation:
            with Image.open(io.BytesIO(image_bytes)) as source:
                image = source.convert("RGB")
                width, height = image.size
            pose_result = self._model("pose").predict(
                image, conf=self._confidence, verbose=False
            )[0]
            face_result = self._model("face").predict(
                image, conf=self._confidence, verbose=False
            )[0]
            person_boxes = self._boxes(pose_result)
            face_boxes = self._boxes(face_result)
            face_count = len(face_boxes)
            face_bbox = None
            if face_count == 1:
                face_x1, face_y1, face_x2, face_y2 = face_boxes[0]
                face_width = face_x2 - face_x1
                face_height = face_y2 - face_y1
                # Expand the detected face to a stable hair-and-head region.
                face_bbox = (
                    max(0.0, face_x1 - face_width * 0.30) / width,
                    max(0.0, face_y1 - face_height * 0.75) / height,
                    min(float(width), face_x2 + face_width * 0.30) / width,
                    min(float(height), face_y2 + face_height * 0.10) / height,
                )
            if len(person_boxes) == 1:
                x1, y1, x2, y2 = person_boxes[0]
                head_inside = y1 > height * 0.005 and x1 > width * 0.005 and x2 < width * 0.995
                feet_inside = y2 < height * 0.995
            else:
                head_inside = False
                feet_inside = False
            orientation, pose_confidence = self._orientation(
                pose_result, face_count=face_count
            )
            torso_foreshortening = self._torso_foreshortening(pose_result)
            return CharacterViewObservation(
                person_count=len(person_boxes),
                face_count=face_count,
                head_inside_frame=head_inside,
                feet_inside_frame=feet_inside,
                orientation=orientation,
                confidence=pose_confidence,
                provider="ultralytics:yolo-person+face+pose",
                face_bbox=face_bbox,
                person_bboxes=tuple(
                    (
                        max(0.0, x1 / width),
                        max(0.0, y1 / height),
                        min(1.0, x2 / width),
                        min(1.0, y2 / height),
                    )
                    for x1, y1, x2, y2 in person_boxes
                ),
                torso_foreshortening=torso_foreshortening,
            )

        return await asyncio.to_thread(run)

    @staticmethod
    def _torso_foreshortening(result: Any) -> float | None:
        """Body yaw as foreshortening: torso width over torso height.

        A square-on torso measures wide and a turned one narrows toward zero, so
        this is the one yaw axis that survives stylised anime art -- the facial
        keypoints read a true profile as a three-quarter view, and the face
        detector's box barely changes at all. It is advisory evidence, never a
        gate: the labelled samples we own do not separate cleanly enough for a
        threshold, but a render whose body ignored its pose guide should be
        visible in the record instead of passing silently on framing alone.
        """
        keypoints = getattr(result, "keypoints", None)
        xy = getattr(keypoints, "xy", None)
        confidence = getattr(keypoints, "conf", None)
        if xy is None or confidence is None or len(xy) == 0:
            return None

        def as_list(value: Any) -> Any:
            if isinstance(value, (list, tuple)):
                return value
            return value.cpu().tolist() if hasattr(value, "cpu") else value.tolist()

        coordinates = as_list(xy[0])
        confidences = as_list(confidence[0])
        # COCO order: 5/6 shoulders, 11/12 hips.
        if len(coordinates) < 13 or len(confidences) < 13:
            return None

        def visible(index: int) -> bool:
            return float(confidences[index]) >= 0.25 and len(coordinates[index]) >= 2

        widths = [
            abs(float(coordinates[left][0]) - float(coordinates[right][0]))
            for left, right in ((5, 6), (11, 12))
            if visible(left) and visible(right)
        ]
        heights = [
            float(coordinates[index][1]) for index in (5, 6, 11, 12) if visible(index)
        ]
        if not widths or len(heights) < 2:
            return None
        torso_height = max(heights) - min(heights)
        if torso_height <= 0:
            return None
        return max(widths) / torso_height

    @staticmethod
    def _boxes(result: Any) -> list[tuple[float, float, float, float]]:
        boxes = getattr(getattr(result, "boxes", None), "xyxy", None)
        if boxes is None:
            return []
        values = boxes.cpu().tolist() if hasattr(boxes, "cpu") else boxes.tolist()
        return [tuple(float(value) for value in row[:4]) for row in values]

    @staticmethod
    def _orientation(result: Any, *, face_count: int) -> tuple[str, float]:
        # A strict rear view has no detectable face. Pose models may still
        # hallucinate low-level facial keypoints on hair or garment edges;
        # those coordinates must not overrule the dedicated face detector.
        if face_count == 0:
            return "back", 1.0
        keypoints = getattr(result, "keypoints", None)
        xy = getattr(keypoints, "xy", None)
        confidence = getattr(keypoints, "conf", None)
        if xy is None or confidence is None or len(xy) == 0:
            return "unknown", 0.0

        def as_list(value: Any) -> Any:
            if isinstance(value, (list, tuple)):
                return value
            return value.cpu().tolist() if hasattr(value, "cpu") else value.tolist()

        coordinates = as_list(xy[0])
        confidences = as_list(confidence[0])
        if len(coordinates) < 5 or len(confidences) < 5:
            return "unknown", 0.0

        # COCO pose order: nose, left eye, right eye, left ear, right ear.
        # Orientation must use spatial coordinates; confidence values only say
        # whether a keypoint is visible and must never be treated as position.
        visible = [
            index
            for index in range(5)
            if float(confidences[index]) >= 0.25
            and len(coordinates[index]) >= 2
        ]
        if not visible:
            return "unknown", 0.0
        nose_x = float(coordinates[0][0])
        facial_points = [
            float(coordinates[index][0])
            for index in (1, 2, 3, 4)
            if index in visible
        ]
        if not facial_points:
            return "unknown", 0.0

        facial_center_x = sum(facial_points) / len(facial_points)
        direction_delta = nose_x - facial_center_x
        coordinate_scale = max(
            1.0,
            max(float(point[0]) for point in coordinates[:5])
            - min(float(point[0]) for point in coordinates[:5]),
        )
        normalized_delta = abs(direction_delta) / coordinate_scale
        side = "right" if direction_delta > 0 else "left"
        eye_count = sum(index in visible for index in (1, 2))
        ear_count = sum(index in visible for index in (3, 4))
        visible_face_points = eye_count + ear_count
        confidence = min(
            1.0,
            sum(float(confidences[index]) for index in visible) / len(visible),
        )
        # One visible eye/ear and a clearly displaced nose is a strict profile;
        # two visible eyes indicate a three-quarter view. A near-centred nose is
        # front-facing even when one auxiliary keypoint is weak.
        if normalized_delta < 0.08:
            return "front", confidence
        if visible_face_points <= 2 and eye_count <= 1:
            return f"profile_{side}", confidence
        if normalized_delta >= 0.08:
            return f"three_quarter_{side}", confidence
        return "unknown", confidence
