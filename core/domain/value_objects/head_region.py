from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class HeadRegion:
    bbox: tuple[float, float, float, float]
    source: str = "unknown"

    def __post_init__(self) -> None:
        left, top, right, bottom = self.bbox
        if not all(math.isfinite(value) for value in self.bbox):
            raise ValueError("Head region coordinates must be finite.")
        if left < 0.0 or top < 0.0 or right <= left or bottom <= top:
            raise ValueError("Head region bounding box is invalid.")
        if not self.source.strip():
            raise ValueError("Head region source must not be empty.")

    @property
    def midline_x(self) -> float:
        return (self.bbox[0] + self.bbox[2]) / 2.0

    @property
    def width(self) -> float:
        return self.bbox[2] - self.bbox[0]

    @property
    def height(self) -> float:
        return self.bbox[3] - self.bbox[1]

    def to_dict(self) -> dict[str, Any]:
        return {"bbox": list(self.bbox), "source": self.source}
