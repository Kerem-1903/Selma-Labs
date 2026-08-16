"""Measured content-level signals from a fully rendered video."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MediaQualitySignals:
    opening_black_seconds: float
    total_black_seconds: float
    maximum_freeze_seconds: float
    maximum_silence_seconds: float
    integrated_lufs: float | None
    true_peak_dbfs: float | None
    loudness_range_lu: float | None = None
    adaptive_silence_threshold_db: float | None = None
    leading_silence_seconds: float = 0.0
    trailing_silence_seconds: float = 0.0
    clipping_detected: bool = False
    scene_change_timestamps_seconds: tuple[float, ...] = ()
    maximum_visual_stasis_seconds: float = 0.0
    average_shot_duration_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "opening_black_seconds": self.opening_black_seconds,
            "total_black_seconds": self.total_black_seconds,
            "maximum_freeze_seconds": self.maximum_freeze_seconds,
            "maximum_silence_seconds": self.maximum_silence_seconds,
            "integrated_lufs": self.integrated_lufs,
            "true_peak_dbfs": self.true_peak_dbfs,
            "loudness_range_lu": self.loudness_range_lu,
            "adaptive_silence_threshold_db": self.adaptive_silence_threshold_db,
            "leading_silence_seconds": self.leading_silence_seconds,
            "trailing_silence_seconds": self.trailing_silence_seconds,
            "clipping_detected": self.clipping_detected,
            "scene_change_timestamps_seconds": list(
                self.scene_change_timestamps_seconds
            ),
            "detected_scene_changes": len(self.scene_change_timestamps_seconds),
            "maximum_visual_stasis_seconds": self.maximum_visual_stasis_seconds,
            "average_shot_duration_seconds": self.average_shot_duration_seconds,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "MediaQualitySignals":
        return MediaQualitySignals(
            opening_black_seconds=float(data["opening_black_seconds"]),
            total_black_seconds=float(data["total_black_seconds"]),
            maximum_freeze_seconds=float(data["maximum_freeze_seconds"]),
            maximum_silence_seconds=float(data["maximum_silence_seconds"]),
            integrated_lufs=(
                float(data["integrated_lufs"])
                if data.get("integrated_lufs") is not None
                else None
            ),
            true_peak_dbfs=(
                float(data["true_peak_dbfs"])
                if data.get("true_peak_dbfs") is not None
                else None
            ),
            loudness_range_lu=(
                float(data["loudness_range_lu"])
                if data.get("loudness_range_lu") is not None
                else None
            ),
            adaptive_silence_threshold_db=(
                float(data["adaptive_silence_threshold_db"])
                if data.get("adaptive_silence_threshold_db") is not None
                else None
            ),
            leading_silence_seconds=float(data.get("leading_silence_seconds", 0.0)),
            trailing_silence_seconds=float(data.get("trailing_silence_seconds", 0.0)),
            clipping_detected=bool(data.get("clipping_detected", False)),
            scene_change_timestamps_seconds=tuple(
                float(value)
                for value in data.get("scene_change_timestamps_seconds", [])
            ),
            maximum_visual_stasis_seconds=float(
                data.get("maximum_visual_stasis_seconds", 0.0)
            ),
            average_shot_duration_seconds=float(
                data.get("average_shot_duration_seconds", 0.0)
            ),
        )
