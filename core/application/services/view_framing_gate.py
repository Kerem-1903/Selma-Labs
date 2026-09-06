"""Deterministic framing validation for reference generation.

The vision model proved unable to catch framing collapse: a 23-frame pack
labelled "full body", "back" and "profile" was generated, but every frame was
actually the same chest-up frontal crop because the face-closeup anchor was
used as the img2img base for every view. qwen auto-review scored those frames
0.968 with zero issues.

This gate is a cheap, deterministic silhouette check that runs BEFORE the
vision model. For recipes that demand a full-body framing it verifies the
subject reaches the bottom of the frame with separated leg columns - a chest-up
crop is a single wide blob cut off by the frame edge.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any

import numpy as np
from PIL import Image, UnidentifiedImageError

_FULL_BODY_VIEWS: frozenset[str] = frozenset(
    {
        "FRONT",
        "PROFILE_LEFT",
        "PROFILE_RIGHT",
        "THREE_QUARTER_LEFT",
        "THREE_QUARTER_RIGHT",
        "FULL_BODY",
        "BACK",
        "ACTION_WALKING",
        "ACTION_RUNNING",
        "ACTION_WIND",
        "ACTION_CROUCHED_GUARD",
        "ACTION_LANDING",
        "ACTION_SIGNATURE",
    }
)


@dataclass(frozen=True)
class FramingReport:
    passed: bool
    reason: str
    metrics: dict[str, float | int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "metrics": dict(self.metrics),
        }


class ViewFramingGate:
    """Deterministic, resolution-independent full-body silhouette check."""

    def applicable_for(self, view: str) -> bool:
        return view in _FULL_BODY_VIEWS

    def evaluate(self, *, image_bytes: bytes, view: str) -> FramingReport:
        if not self.applicable_for(view):
            return FramingReport(
                passed=True, reason="view not framing-gated", metrics={}
            )
        try:
            with Image.open(io.BytesIO(image_bytes)) as source:
                array = np.asarray(source.convert("RGB")).astype(np.int16)
        except (UnidentifiedImageError, OSError, ValueError) as error:
            return FramingReport(
                passed=False, reason=f"unreadable image: {error}", metrics={}
            )
        height, width, _ = array.shape
        # Model the background as a bilinear colour surface derived from the
        # four corners. Reference prompts deliberately allow soft studio
        # gradients; comparing the whole frame with one median border colour
        # turns such a gradient into one full-width foreground blob.
        corner_size = max(1, min(height, width, 100) // 10)
        top_left = np.median(
            array[:corner_size, :corner_size].reshape(-1, 3), axis=0
        )
        top_right = np.median(
            array[:corner_size, -corner_size:].reshape(-1, 3), axis=0
        )
        bottom_left = np.median(
            array[-corner_size:, :corner_size].reshape(-1, 3), axis=0
        )
        bottom_right = np.median(
            array[-corner_size:, -corner_size:].reshape(-1, 3), axis=0
        )
        horizontal = np.linspace(0.0, 1.0, width, dtype=np.float32)[None, :, None]
        vertical = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None, None]
        top_surface = top_left + (top_right - top_left) * horizontal
        bottom_surface = bottom_left + (bottom_right - bottom_left) * horizontal
        background = top_surface + (bottom_surface - top_surface) * vertical
        foreground = np.abs(array - background).sum(axis=2) > 90
        rows = np.where(foreground.any(axis=1))[0]
        if rows.size == 0:
            return FramingReport(
                passed=False,
                reason="no subject detected against the background",
                metrics={"top": 1.0, "bottom": 0.0},
            )
        top = float(rows.min()) / height
        bottom = float(rows.max()) / height

        def width_at(fraction: float) -> float:
            start = min(height - 1, int(fraction * height))
            band = foreground[start : start + max(1, int(height * 0.01))]
            if band.size == 0:
                return 0.0
            return float(band.sum()) / (band.shape[0] * width)

        def runs_at(fraction: float) -> int:
            row = foreground[min(height - 1, int(fraction * height))]
            runs = 0
            in_run = False
            for value in row:
                if value and not in_run:
                    runs += 1
                    in_run = True
                elif not value:
                    in_run = False
            return runs

        width_lower = width_at(0.97)
        runs_lower = runs_at(0.97)
        metrics: dict[str, float | int] = {
            "top": round(top, 3),
            "bottom": round(bottom, 3),
            "width_lower": round(width_lower, 3),
            "runs_lower": runs_lower,
        }
        # Calibrated on measured frames: a standing full-body figure reaches the
        # bottom with separated leg columns (runs >= 2) that stay narrow
        # (width_lower < 0.55). Chest-up crops are a single wide blob cut by the
        # frame edge; multi-figure sheets fail the width bound as well.
        if top > 0.22:
            return FramingReport(
                passed=False,
                reason="subject starts too low in the frame; not a full body",
                metrics=metrics,
            )
        if bottom < 0.85:
            return FramingReport(
                passed=False,
                reason="subject does not reach the bottom of the frame; "
                "likely a chest-up crop",
                metrics=metrics,
            )
        if runs_lower < 2:
            return FramingReport(
                passed=False,
                reason="no separated leg columns at the bottom; chest-up crop",
                metrics=metrics,
            )
        if width_lower >= 0.55:
            return FramingReport(
                passed=False,
                reason="bottom silhouette is a single wide mass; chest-up crop "
                "or multi-figure sheet",
                metrics=metrics,
            )
        return FramingReport(
            passed=True,
            reason="separated legs reach the bottom; full-body framing",
            metrics=metrics,
        )
