"""Advisory, deterministic drift measurement for a character turnaround.

This service deliberately cannot approve anything. ``CharacterViewConsistencyReportService``
already fixes the rule that automatic evidence never replaces visual human
approval, so a drift number is a place to *look*, not a verdict.

It exists because two defects kept reaching human review unnoticed: the single
messenger bag grew and was re-read as blue on the back view, and the single
cobalt hair streak vanished on the side views -- or worse, appeared mirrored on
the wrong one. Both are measurable without a second model. The streak is a
sparse saturated colour inside the head region; the bag is why the accent
fraction of the whole subject moves.

Everything here is deterministic pixel statistics over bytes, so the service
needs no filesystem, works behind any ``StoragePort``, and any report can be
recomputed from the same bytes and asserted in a test.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, UnidentifiedImageError

#: A standing full-body turnaround keeps the head in roughly the top fifth of
#: the subject box. This service has no face detector by design -- the QC gate
#: owns that -- so the head region is approximated, not detected.
HEAD_REGION_HEIGHT_RATIO = 0.18

#: Colour quantization for the palette histogram: 4 levels per channel.
_PALETTE_LEVELS = 4

#: Foreground separation threshold, summed over the three channels. Matches
#: ``ViewFramingGate``: the QC gate and this service must agree about what "the
#: subject" is, or the two report different characters from the same bytes.
_FOREGROUND_DISTANCE = 90

#: A row or column whose foreground coverage is this low is stray noise, not the
#: subject. Without this trim a single anti-aliased edge pixel at the frame
#: border makes the subject box span the whole image.
_MIN_AXIS_COVERAGE = 0.01

#: Below this share of head pixels the reference carries too little accent for a
#: ratio to mean anything: anti-aliasing noise dominates it. The streak is a
#: deliberate design element, not a handful of pixels, so the honest answer for a
#: reference this sparse is "not measurable", never a verdict either way.
_MIN_MEASURABLE_HEAD_ACCENT = 2.0e-4

#: Relative aspect-ratio difference above which source and view are no longer
#: comparable. The box metrics are normalized by frame size, so a square source
#: measured against a portrait frame is off by the aspect difference alone before
#: any character difference exists. Measured on the v6 pack: source 1024x1024,
#: views 768x1152, absolute subject heights agreed (1024 px vs 1002-1060 px)
#: while the normalized ratios diverged by 0.08-0.13 -- a flag that was pure
#: frame arithmetic. Naming it is the difference between a reviewer re-running
#: the pack and a reviewer chasing a defect that is not there.
_CANVAS_ASPECT_TOLERANCE = 0.02

_MARK_SIDES = frozenset({"", "left", "right"})


@dataclass(frozen=True)
class DriftThresholds:
    """Tolerance band for one turnaround against its approved source."""

    subject_height_ratio_delta: float = 0.06
    subject_width_ratio_delta: float = 0.08
    palette_distance: float = 0.22
    accent_fraction_delta: float = 0.012
    mark_presence_ratio: float = 0.35
    mark_mirror_ratio: float = 0.45
    line_density_ratio_delta: float = 0.35

    def to_dict(self) -> dict[str, float]:
        return {
            "subject_height_ratio_delta": self.subject_height_ratio_delta,
            "subject_width_ratio_delta": self.subject_width_ratio_delta,
            "palette_distance": self.palette_distance,
            "accent_fraction_delta": self.accent_fraction_delta,
            "mark_presence_ratio": self.mark_presence_ratio,
            "mark_mirror_ratio": self.mark_mirror_ratio,
            "line_density_ratio_delta": self.line_density_ratio_delta,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DriftThresholds":
        defaults = cls().to_dict()
        return cls(
            **{
                name: float(data.get(name, default))
                for name, default in defaults.items()
            }
        )


def load_drift_thresholds(
    path: str | Path,
) -> tuple[DriftThresholds, dict[str, str]]:
    """Load a calibrated band together with its tamper-evident provenance.

    A band that has been calibrated once must not quietly lose to the built-in
    defaults: those are deliberately looser, so a silent fallback would report
    "within tolerance" for renders the calibrated band already flags. The
    returned provenance travels into ``drift-report.json`` so a reviewer can
    tell which band produced a verdict, and from which bytes.
    """
    source = Path(path)
    try:
        raw_bytes = source.read_bytes()
    except OSError as error:
        raise ValueError(f"Drift thresholds file is unreadable: {source}") from error
    try:
        payload = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(
            f"Drift thresholds file is not valid JSON: {source}"
        ) from error
    if not isinstance(payload, Mapping):
        raise TypeError(f"Drift thresholds file must contain an object: {source}")
    calibration = payload.get("calibration")
    method = (
        str(calibration.get("method", "")) if isinstance(calibration, Mapping) else ""
    )
    return (
        DriftThresholds.from_dict(payload),
        {
            "path": source.as_posix(),
            "sha256": hashlib.sha256(raw_bytes).hexdigest(),
            "character_id": str(payload.get("character_id", "")),
            "character_version": str(payload.get("character_version", "")),
            "calibration_method": method,
        },
    )


@dataclass(frozen=True)
class _Measurement:
    """Pure pixel statistics for one image."""

    pixels: np.ndarray  # (N, 3) uint8, subject only
    height_ratio: float
    width_ratio: float
    line_density: float
    head_accent_density: float
    canvas_width: int = 0
    canvas_height: int = 0

    def deltas(self, source: "_Measurement") -> dict[str, float]:
        return {
            "subject_height_ratio": self.height_ratio,
            "subject_width_ratio": self.width_ratio,
            "subject_height_ratio_delta": self.height_ratio - source.height_ratio,
            "subject_width_ratio_delta": self.width_ratio - source.width_ratio,
            "line_density": self.line_density,
            "line_density_ratio_delta": self.line_density
            / max(source.line_density, 1e-9)
            - 1.0,
        }


class CharacterTurnaroundDriftService:
    """Measure how far each generated view drifted from the approved source."""

    #: Which body side faces the camera in each single-side view.
    _SIDE_FACING_VIEW: dict[str, str] = {
        "PROFILE_LEFT": "left",
        "THREE_QUARTER_LEFT": "left",
        "PROFILE_RIGHT": "right",
        "THREE_QUARTER_RIGHT": "right",
    }

    #: Floors for calibrated bands. An edit model that only rotates the camera
    #: can reproduce the subject box exactly, and a zero-width band would turn
    #: single-pixel noise into a drift verdict.
    _CALIBRATION_FLOOR: dict[str, float] = {
        "subject_height_ratio_delta": 0.02,
        "subject_width_ratio_delta": 0.03,
        "palette_distance": 0.05,
        "accent_fraction_delta": 0.004,
        "line_density_ratio_delta": 0.10,
    }

    def __init__(
        self,
        *,
        accent_colour: str = "",
        accent_tolerance: float = 60.0,
        mark_side: str = "",
        thresholds: DriftThresholds | None = None,
        threshold_source: Mapping[str, str] | None = None,
    ) -> None:
        side = mark_side.strip().casefold()
        if side not in _MARK_SIDES:
            raise ValueError("mark_side must be empty, 'left' or 'right'.")
        if not 0.0 < accent_tolerance <= 441.7:
            raise ValueError("accent_tolerance must be within RGB distance bounds.")
        self._mark_side = side
        self._accent = self._parse_colour(accent_colour) if accent_colour else None
        if accent_colour and self._accent is None:
            # Fail loudly: silently dropping the accent would disable exactly the
            # two metrics that catch the known defects.
            raise ValueError("accent_colour must be a #RRGGBB value.")
        self._accent_tolerance = float(accent_tolerance)
        self._thresholds = thresholds
        self._threshold_source = dict(threshold_source or {})

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def for_character(
        self, *, accent_colour: str, mark_side: str = ""
    ) -> "CharacterTurnaroundDriftService":
        """Re-aim the measurement at one character's own signature mark.

        The configured accent colour is a single deployment-wide value, so a
        character whose signature mark is a different colour was measured with
        the wrong one: its accent fraction came out as ``0.0`` and every drawn
        view was flagged, which is an alarm the bytes cannot support. The brief
        already declares the colour and the side, so the measurement is derived
        from the character instead of from the deployment. Everything else --
        tolerance, calibrated band, threshold source -- is carried over so the
        verdict stays comparable with previous reports.
        """
        return type(self)(
            accent_colour=accent_colour,
            accent_tolerance=self._accent_tolerance,
            mark_side=mark_side,
            thresholds=self._thresholds,
            threshold_source=self._threshold_source,
        )

    def evaluate(
        self,
        *,
        source_bytes: bytes,
        views: Mapping[str, bytes],
        thresholds: DriftThresholds | None = None,
        labels: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        band = thresholds or self._thresholds or DriftThresholds()
        if not views:
            raise ValueError("Drift evaluation requires at least one view.")
        source = self._measure(source_bytes, "source")
        reports = [
            self._evaluate_view(
                view=view,
                data=data,
                label=(labels or {}).get(view, view),
                source=source,
                band=band,
            )
            for view, data in sorted(views.items())
        ]
        flagged = [
            item["view"]
            for item in reports
            if item["status"] != "WITHIN_TOLERANCE"
        ]
        return {
            "schema_version": 1,
            "report_type": "character_turnaround_drift",
            "advisory_only": True,
            "approval_policy": (
                "Drift metrics never approve or reject a view; they only point "
                "the human reviewer at one specific measurable difference."
            ),
            "source_label": (labels or {}).get("source", "source"),
            "source_metrics": {
                "subject_height_ratio": source.height_ratio,
                "subject_width_ratio": source.width_ratio,
                "line_density": source.line_density,
                "head_accent_density": source.head_accent_density,
                "subject_pixel_count": int(source.pixels.shape[0]),
                "canvas": [source.canvas_width, source.canvas_height],
                "mark_measurable": (
                    source.head_accent_density > _MIN_MEASURABLE_HEAD_ACCENT
                ),
            },
            "thresholds": band.to_dict(),
            # Which band produced this verdict, and from which bytes. Empty when
            # the caller did not configure a calibrated file.
            "threshold_source": dict(self._threshold_source),
            "mark_side": self._mark_side,
            "accent_colour": (
                "#%02X%02X%02X" % tuple(int(value) for value in self._accent)
                if self._accent is not None
                else ""
            ),
            "views": reports,
            "summary": {
                "view_count": len(reports),
                "flagged_view_count": len(flagged),
                "flagged_views": flagged,
                "canvas_comparable": all(
                    item["canvas_comparable"] for item in reports
                ),
                "mark_measurable": any(item["mark_measurable"] for item in reports),
            },
            "status": "WITHIN_TOLERANCE" if not flagged else "DRIFT_FLAGGED",
        }

    def calibrate(
        self,
        *,
        source_bytes: bytes,
        views: Mapping[str, bytes],
        margin: float = 1.35,
    ) -> DriftThresholds:
        """Derive the tolerance band from an accepted pack instead of inventing it.

        The accepted pack defines "good enough"; ``margin`` widens the observed
        spread so ordinary per-seed noise is not reported as drift. Only the
        tolerance band is calibrated -- signature-mark thresholds stay fixed,
        because a reference pack may itself be where the mark was lost.
        """
        if margin < 1.0:
            raise ValueError("Calibration margin must be at least 1.0.")
        if not views:
            raise ValueError("Calibration requires at least one accepted view.")
        source = self._measure(source_bytes, "source")
        measurements = [
            self._measure(data, view) for view, data in sorted(views.items())
        ]
        observed: list[dict[str, float]] = []
        for item in measurements:
            row = item.deltas(source)
            row["palette_distance"] = self._palette_distance(source, item)
            row["accent_fraction_delta"] = self._accent_delta(source, item)
            observed.append(row)
        return DriftThresholds(
            subject_height_ratio_delta=self._widest(
                observed, "subject_height_ratio_delta", margin
            ),
            subject_width_ratio_delta=self._widest(
                observed, "subject_width_ratio_delta", margin
            ),
            line_density_ratio_delta=self._widest(
                observed, "line_density_ratio_delta", margin
            ),
            palette_distance=self._widest(observed, "palette_distance", margin),
            accent_fraction_delta=self._widest(
                observed, "accent_fraction_delta", margin
            ),
        )

    def evaluate_paths(
        self,
        *,
        source_path: str | Path,
        views: Mapping[str, str | Path],
        thresholds: DriftThresholds | None = None,
    ) -> dict[str, Any]:
        """Filesystem convenience wrapper around :meth:`evaluate`."""
        return self.evaluate(
            source_bytes=Path(source_path).read_bytes(),
            views={view: Path(path).read_bytes() for view, path in views.items()},
            thresholds=thresholds,
            labels={
                "source": Path(source_path).as_posix(),
                **{view: Path(path).as_posix() for view, path in views.items()},
            },
        )

    def calibrate_paths(
        self,
        *,
        source_path: str | Path,
        views: Mapping[str, str | Path],
        margin: float = 1.35,
    ) -> DriftThresholds:
        """Filesystem convenience wrapper around :meth:`calibrate`."""
        return self.calibrate(
            source_bytes=Path(source_path).read_bytes(),
            views={view: Path(path).read_bytes() for view, path in views.items()},
            margin=margin,
        )

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------
    def _evaluate_view(
        self,
        *,
        view: str,
        data: bytes,
        label: str,
        source: _Measurement,
        band: DriftThresholds,
    ) -> dict[str, Any]:
        measured = self._measure(data, view)
        metrics = dict(measured.deltas(source))
        metrics["palette_distance"] = self._palette_distance(source, measured)
        metrics["accent_fraction"] = self._accent_fraction(measured.pixels)
        metrics["accent_fraction_delta"] = self._accent_delta(source, measured)
        metrics["head_accent_ratio"] = self._head_accent_ratio(source, measured)

        comparable = self._canvases_match(source, measured)
        reasons: list[str] = []
        if not comparable:
            # First, because it invalidates the rest: a reviewer must not read a
            # box or palette delta as character drift when the two frames do not
            # share an aspect ratio.
            reasons.append("canvas_aspect_mismatch")
        if abs(metrics["subject_height_ratio_delta"]) > band.subject_height_ratio_delta:
            reasons.append("subject_height_drift")
        if abs(metrics["subject_width_ratio_delta"]) > band.subject_width_ratio_delta:
            reasons.append("subject_width_drift")
        if metrics["palette_distance"] > band.palette_distance:
            reasons.append("palette_drift")
        if abs(metrics["accent_fraction_delta"]) > band.accent_fraction_delta:
            reasons.append("accent_fraction_drift")
        if abs(metrics["line_density_ratio_delta"]) > band.line_density_ratio_delta:
            reasons.append("line_density_drift")

        expectation = self._mark_expectation(view)
        measurable = source.head_accent_density > _MIN_MEASURABLE_HEAD_ACCENT
        if measurable and expectation == "visible" and metrics["head_accent_ratio"] < (
            1.0 - band.mark_presence_ratio
        ):
            reasons.append("signature_mark_missing_or_hidden")
        elif measurable and expectation == "hidden" and (
            metrics["head_accent_ratio"] > band.mark_mirror_ratio
        ):
            reasons.append("signature_mark_mirrored_onto_visible_side")

        return {
            "view": view,
            "label": label,
            "status": "WITHIN_TOLERANCE" if not reasons else "DRIFT_FLAGGED",
            "reasons": reasons,
            "mark_expectation": expectation,
            # False means the mark metrics were not applied at all: the source
            # carries too few accent pixels for a ratio to mean anything. A
            # reviewer must be able to tell "measured and clean" from "not
            # measured", or a silent metric looks like a passing one.
            "mark_measurable": measurable,
            "canvas_comparable": comparable,
            "canvas": [measured.canvas_width, measured.canvas_height],
            "metrics": {
                name: round(float(value), 6) for name, value in metrics.items()
            },
        }

    def _mark_expectation(self, view: str) -> str | None:
        """Return 'visible', 'hidden', or None when the mark side is unknown.

        A turnaround marks its signature colour in the *front* hair, so the
        realistic defect pair is: the mark must survive every view that can see
        the front of the head, and it must never be conjured onto a view that
        cannot (the far-side profile, or the back of the head).
        """
        if not self._mark_side:
            return None
        if view == "BACK":
            return "hidden"
        facing = self._SIDE_FACING_VIEW.get(view)
        if facing is None:
            return "visible"
        return "visible" if facing == self._mark_side else "hidden"

    @staticmethod
    def _canvases_match(source: "_Measurement", measured: "_Measurement") -> bool:
        """True when both frames share an aspect ratio closely enough to compare."""
        if source.canvas_width <= 0 or source.canvas_height <= 0:
            return True
        if measured.canvas_width <= 0 or measured.canvas_height <= 0:
            return True
        source_aspect = source.canvas_width / source.canvas_height
        view_aspect = measured.canvas_width / measured.canvas_height
        return (
            abs(view_aspect - source_aspect) / source_aspect
            <= _CANVAS_ASPECT_TOLERANCE
        )

    @classmethod
    def _widest(
        cls, measured: list[dict[str, float]], name: str, margin: float
    ) -> float:
        widest = max(abs(item[name]) for item in measured) * margin
        return float(max(widest, cls._CALIBRATION_FLOOR.get(name, 0.0)))

    # ------------------------------------------------------------------
    # Measurement
    # ------------------------------------------------------------------
    def _measure(self, data: bytes, label: str) -> _Measurement:
        array = self._load_rgb(data, label)
        mask = self._subject_mask(array, label)
        rows = np.flatnonzero(mask.any(axis=1))
        columns = np.flatnonzero(mask.any(axis=0))
        height, width = mask.shape
        gray = array.astype(np.float32).mean(axis=2)
        gradient = np.zeros_like(gray)
        gradient[:, :-1] += np.abs(np.diff(gray, axis=1))
        gradient[:-1, :] += np.abs(np.diff(gray, axis=0))
        head_end = rows[0] + max(
            1, int((rows[-1] - rows[0] + 1) * HEAD_REGION_HEIGHT_RATIO)
        )
        # Restrict to subject pixels: the bounding-box rectangle would be mostly
        # background, and a light studio background reads as a blue-ish colour.
        head_mask = mask[rows[0] : head_end, :]
        head_pixels = array[rows[0] : head_end, :, :][head_mask]
        return _Measurement(
            pixels=array[mask],
            height_ratio=float((rows[-1] - rows[0] + 1) / height),
            width_ratio=float((columns[-1] - columns[0] + 1) / width),
            line_density=float(gradient[mask].mean() / 255.0),
            head_accent_density=self._accent_fraction(head_pixels),
            canvas_width=int(width),
            canvas_height=int(height),
        )

    @staticmethod
    def _load_rgb(data: bytes, label: str) -> np.ndarray:
        try:
            with Image.open(io.BytesIO(data)) as opened:
                image = opened.convert("RGB").copy()
        except (UnidentifiedImageError, OSError) as error:
            raise ValueError(f"Drift input is not a readable image: {label}") from error
        return np.asarray(image, dtype=np.uint8)

    @staticmethod
    def _subject_mask(array: np.ndarray, label: str) -> np.ndarray:
        """Separate the character from the studio backdrop.

        The backdrop is not one flat colour: the canonical Kaito reference (and
        every faithful turnaround of it) carries a soft blue-to-light gradient.
        A single median border colour is therefore tens of units away from both
        the top and the bottom of the frame, and every pixel counts as subject --
        measured at 74% frame fill, with the subject box pinned to the full
        frame so the height and width ratios could never move.

        So the background is modelled as a bilinear surface through the four
        corner patches, exactly as ``ViewFramingGate`` does, and stray rows and
        columns below a minimum coverage are dropped so the subject box is the
        character rather than the frame.
        """
        height, width, _ = array.shape
        corner = max(1, min(height, width, 100) // 10)
        top_left = np.median(array[:corner, :corner].reshape(-1, 3), axis=0)
        top_right = np.median(array[:corner, -corner:].reshape(-1, 3), axis=0)
        bottom_left = np.median(array[-corner:, :corner].reshape(-1, 3), axis=0)
        bottom_right = np.median(array[-corner:, -corner:].reshape(-1, 3), axis=0)
        horizontal = np.linspace(0.0, 1.0, width, dtype=np.float32)[None, :, None]
        vertical = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None, None]
        top_surface = top_left + (top_right - top_left) * horizontal
        bottom_surface = bottom_left + (bottom_right - bottom_left) * horizontal
        background = top_surface + (bottom_surface - top_surface) * vertical
        mask = (
            np.abs(array.astype(np.float32) - background).sum(axis=2)
            > _FOREGROUND_DISTANCE
        )
        if not mask.any():
            raise ValueError(
                f"Subject mask is empty for {label}; check the input framing."
            )
        row_coverage = mask.sum(axis=1) / width
        column_coverage = mask.sum(axis=0) / height
        mask[row_coverage < _MIN_AXIS_COVERAGE, :] = False
        mask[:, column_coverage < _MIN_AXIS_COVERAGE] = False
        if mask.sum() < 16:
            raise ValueError(
                f"Subject mask is empty for {label}; check the input framing."
            )
        return mask

    def _palette_distance(
        self, source: _Measurement, measured: _Measurement
    ) -> float:
        return float(
            np.abs(
                self._histogram(source.pixels) - self._histogram(measured.pixels)
            ).sum()
            / 2.0
        )

    @staticmethod
    def _histogram(pixels: np.ndarray) -> np.ndarray:
        quantized = (pixels.astype(np.uint16) * _PALETTE_LEVELS) // 256
        flat = (
            quantized[:, 0] * _PALETTE_LEVELS * _PALETTE_LEVELS
            + quantized[:, 1] * _PALETTE_LEVELS
            + quantized[:, 2]
        )
        counts = np.bincount(flat, minlength=_PALETTE_LEVELS**3).astype(np.float64)
        total = counts.sum()
        return counts / total if total else counts

    def _accent_fraction(self, pixels: np.ndarray) -> float:
        if self._accent is None or pixels.size == 0:
            return 0.0
        distance = np.sqrt(
            np.sum(
                (pixels.astype(np.float32) - self._accent.astype(np.float32)) ** 2,
                axis=1,
            )
        )
        return float((distance <= self._accent_tolerance).mean())

    def _accent_delta(
        self, source: _Measurement, measured: _Measurement
    ) -> float:
        return self._accent_fraction(
            measured.pixels
        ) - self._accent_fraction(source.pixels)

    def _head_accent_ratio(
        self, source: _Measurement, measured: _Measurement
    ) -> float:
        if source.head_accent_density <= _MIN_MEASURABLE_HEAD_ACCENT:
            # The source head carries too little accent for a ratio to mean
            # anything: anti-aliasing along the silhouette edge dominates it.
            # Report neutral instead of raising an alarm the pixels cannot
            # support, and let ``mark_measurable`` say the check was skipped.
            return 1.0
        return measured.head_accent_density / source.head_accent_density

    @staticmethod
    def _parse_colour(value: str) -> np.ndarray | None:
        text = value.strip()
        if not re.fullmatch(r"#[0-9A-Fa-f]{6}", text):
            return None
        return np.array(
            [int(text[index : index + 2], 16) for index in (1, 3, 5)],
            dtype=np.uint8,
        )


__all__ = [
    "CharacterTurnaroundDriftService",
    "DriftThresholds",
    "load_drift_thresholds",
]
