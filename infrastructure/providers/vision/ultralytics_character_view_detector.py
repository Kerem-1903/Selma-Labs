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
            return CharacterViewObservation(
                person_count=len(person_boxes),
                face_count=face_count,
                head_inside_frame=head_inside,
                feet_inside_frame=feet_inside,
                orientation=orientation,
                confidence=pose_confidence,
                provider="ultralytics:yolo-person+face+pose",
                face_bbox=face_bbox,
            )

        return await asyncio.to_thread(run)

    @staticmethod
    def _boxes(result: Any) -> list[tuple[float, float, float, float]]:
        boxes = getattr(getattr(result, "boxes", None), "xyxy", None)
        if boxes is None:
            return []
        values = boxes.cpu().tolist() if hasattr(boxes, "cpu") else boxes.tolist()
        return [tuple(float(value) for value in row[:4]) for row in values]

    @staticmethod
    def _orientation(result: Any, *, face_count: int) -> tuple[str, float]:
        keypoints = getattr(getattr(result, "keypoints", None), "conf", None)
        if keypoints is None or len(keypoints) == 0:
            return ("back", 1.0) if face_count == 0 else ("unknown", 0.0)
        values = keypoints[0].cpu().tolist() if hasattr(keypoints[0], "cpu") else keypoints[0].tolist()
        if len(values) < 5:
            return ("back", 1.0) if face_count == 0 else ("unknown", 0.0)
        nose = float(values[0])
        left = (float(values[1]) + float(values[3])) / 2.0
        right = (float(values[2]) + float(values[4])) / 2.0
        if face_count == 0 and max(nose, left, right) < 0.25:
            return "back", 1.0 - max(nose, left, right)
        stronger = max(left, right)
        weaker = max(0.01, min(left, right))
        ratio = stronger / weaker
        side = "left" if left > right else "right"
        if ratio >= 2.0:
            return f"profile_{side}", min(1.0, stronger)
        if ratio >= 1.25:
            return f"three_quarter_{side}", min(1.0, stronger)
        return "front", min(1.0, max(nose, left, right))
