from __future__ import annotations

import asyncio
import io
import threading
from typing import Any

import numpy as np
from PIL import Image

from core.domain.ports.head_region_port import HeadRegionPort
from core.domain.value_objects.head_region import HeadRegion


class InsightFaceHeadRegionProvider(HeadRegionPort):
    """Detect and expand the largest face into a hair-inclusive head region."""

    def __init__(
        self,
        *,
        model_name: str = "buffalo_l",
        model_root: str = "~/.insightface",
        det_size: tuple[int, int] = (640, 640),
        ctx_id: int = 0,
        providers: tuple[str, ...] | None = None,
        hair_pad_top: float = 0.35,
        hair_pad_side: float = 0.15,
    ) -> None:
        if not model_name.strip() or not model_root.strip():
            raise ValueError("InsightFace model name and root must not be empty.")
        if min(det_size) <= 0:
            raise ValueError("InsightFace detection size must be positive.")
        if not 0.0 <= hair_pad_top <= 2.0 or not 0.0 <= hair_pad_side <= 1.0:
            raise ValueError("InsightFace hair padding is invalid.")
        self._model_name = model_name
        self._model_root = model_root
        self._det_size = det_size
        self._ctx_id = ctx_id
        self._providers = providers
        self._pad_top = hair_pad_top
        self._pad_side = hair_pad_side
        self._app: Any | None = None
        self._init_lock = threading.Lock()

    def _ensure_app(self) -> Any:
        if self._app is not None:
            return self._app
        with self._init_lock:
            if self._app is not None:
                return self._app
            try:
                from insightface.app import FaceAnalysis
            except ImportError as error:
                raise RuntimeError(
                    "Structured-mark validation requires the optional "
                    "InsightFace runtime. Install requirements.txt."
                ) from error
            kwargs: dict[str, Any] = {
                "name": self._model_name,
                "root": self._model_root,
            }
            if self._providers:
                kwargs["providers"] = list(self._providers)
            app = FaceAnalysis(**kwargs)
            app.prepare(ctx_id=self._ctx_id, det_size=self._det_size)
            self._app = app
            return app

    async def detect(self, image_bytes: bytes) -> HeadRegion | None:
        if not image_bytes:
            raise ValueError("Head detection requires non-empty image bytes.")

        def run() -> HeadRegion | None:
            with Image.open(io.BytesIO(image_bytes)) as source:
                rgb = np.asarray(source.convert("RGB"))
            # InsightFace follows OpenCV's BGR input convention.
            bgr = np.ascontiguousarray(rgb[..., ::-1])
            faces = self._ensure_app().get(bgr)
            if not faces:
                return None
            face = max(
                faces,
                key=lambda item: float(
                    (item.bbox[2] - item.bbox[0]) * (item.bbox[3] - item.bbox[1])
                ),
            )
            x1, y1, x2, y2 = (float(value) for value in face.bbox)
            face_width = x2 - x1
            face_height = y2 - y1
            image_height, image_width = bgr.shape[:2]
            left = max(0.0, x1 - self._pad_side * face_width)
            top = max(0.0, y1 - self._pad_top * face_height)
            right = min(float(image_width), x2 + self._pad_side * face_width)
            bottom = min(float(image_height), y2)
            return HeadRegion(
                bbox=(left, top, right, bottom),
                source=f"insightface:{self._model_name}",
            )

        return await asyncio.to_thread(run)
