from __future__ import annotations

import io

import numpy as np
from PIL import Image

from core.application.services.view_framing_gate import ViewFramingGate


def _png(mask: np.ndarray) -> bytes:
    image = np.zeros((*mask.shape, 3), dtype=np.uint8)
    image[:] = (245, 245, 245)  # light reference background
    image[mask] = (30, 30, 32)  # dark subject
    buffer = io.BytesIO()
    Image.fromarray(image, "RGB").save(buffer, format="PNG")
    return buffer.getvalue()


def _gradient_png(mask: np.ndarray) -> bytes:
    height, width = mask.shape
    image = np.zeros((height, width, 3), dtype=np.uint8)
    for row in range(height):
        shade = round(245 - (70 * row / max(1, height - 1)))
        image[row] = (shade, shade, shade)
    image[mask] = (30, 30, 32)
    buffer = io.BytesIO()
    Image.fromarray(image, "RGB").save(buffer, format="PNG")
    return buffer.getvalue()


def _full_body_mask(height: int = 200, width: int = 120) -> np.ndarray:
    mask = np.zeros((height, width), dtype=bool)
    mask[10:30, 50:70] = True  # head
    mask[28:110, 44:76] = True  # torso
    mask[108:195, 46:58] = True  # left leg
    mask[108:195, 62:74] = True  # right leg
    return mask


def _chest_up_mask(height: int = 200, width: int = 120) -> np.ndarray:
    mask = np.zeros((height, width), dtype=bool)
    mask[10:100, 30:90] = True  # head + torso
    mask[98:200, 24:96] = True  # wide shoulder mass cropped by frame edge
    return mask


def test_full_body_mask_passes_gate():
    report = ViewFramingGate().evaluate(
        image_bytes=_png(_full_body_mask()), view="FULL_BODY"
    )
    assert report.passed, report.reason
    assert report.metrics["runs_lower"] >= 2


def test_full_body_mask_passes_on_soft_gradient_background():
    report = ViewFramingGate().evaluate(
        image_bytes=_gradient_png(_full_body_mask()), view="FULL_BODY"
    )

    assert report.passed, report.reason
    assert report.metrics["runs_lower"] >= 2


def test_chest_up_mask_fails_full_body_contract():
    report = ViewFramingGate().evaluate(
        image_bytes=_png(_chest_up_mask()), view="FULL_BODY"
    )
    assert not report.passed
    assert "leg" in report.reason or "wide" in report.reason


def test_action_view_uses_same_full_body_contract():
    report = ViewFramingGate().evaluate(
        image_bytes=_png(_chest_up_mask()), view="ACTION_RUNNING"
    )
    assert not report.passed


def test_face_closeup_view_is_not_framing_gated():
    report = ViewFramingGate().evaluate(
        image_bytes=_png(_chest_up_mask()), view="FACE_CLOSEUP"
    )
    assert report.passed
    assert report.reason == "view not framing-gated"


def test_three_quarter_full_body_view_rejects_chest_up_crop():
    report = ViewFramingGate().evaluate(
        image_bytes=_png(_chest_up_mask()), view="THREE_QUARTER_LEFT"
    )
    assert not report.passed
