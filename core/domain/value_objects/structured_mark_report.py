from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StructuredMarkReport:
    mark_id: str
    passed: bool
    expected_count: int
    detected_count: int
    matched_pixels: int
    mean_delta_e: float | None
    max_delta_e: float | None
    anchor_distance_px: float | None
    detected_root_x: float | None
    detected_root_y: float | None
    expected_side: str
    actual_side: str | None
    checks: tuple[tuple[str, bool], ...]

    @property
    def failures(self) -> tuple[str, ...]:
        return tuple(name for name, ok in self.checks if not ok)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mark_id": self.mark_id,
            "passed": self.passed,
            "expected_count": self.expected_count,
            "detected_count": self.detected_count,
            "matched_pixels": self.matched_pixels,
            "mean_delta_e": self.mean_delta_e,
            "max_delta_e": self.max_delta_e,
            "anchor_distance_px": self.anchor_distance_px,
            "detected_root_x": self.detected_root_x,
            "detected_root_y": self.detected_root_y,
            "expected_side": self.expected_side,
            "actual_side": self.actual_side,
            "checks": [list(check) for check in self.checks],
            "failures": list(self.failures),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> StructuredMarkReport:
        def optional_float(name: str) -> float | None:
            value = data.get(name)
            return float(value) if value is not None else None

        return cls(
            mark_id=str(data["mark_id"]),
            passed=bool(data["passed"]),
            expected_count=int(data["expected_count"]),
            detected_count=int(data["detected_count"]),
            matched_pixels=int(data["matched_pixels"]),
            mean_delta_e=optional_float("mean_delta_e"),
            max_delta_e=optional_float("max_delta_e"),
            anchor_distance_px=optional_float("anchor_distance_px"),
            detected_root_x=optional_float("detected_root_x"),
            detected_root_y=optional_float("detected_root_y"),
            expected_side=str(data["expected_side"]),
            actual_side=(
                str(data["actual_side"])
                if data.get("actual_side") is not None
                else None
            ),
            checks=tuple((str(name), bool(ok)) for name, ok in data["checks"]),
        )
