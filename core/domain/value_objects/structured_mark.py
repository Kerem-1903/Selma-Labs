from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, cast

ViewerSide = Literal["viewer_left", "viewer_right"]
MirrorSide = Literal["none", "viewer_left", "viewer_right"]
MarkEnforcement = Literal["steer", "seal", "both"]

_HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


@dataclass(frozen=True)
class MarkAnchor:
    region: str
    x_center: float
    y_root: float
    extent: float
    sweep_deg: float = 0.0

    def __post_init__(self) -> None:
        if not self.region.strip():
            raise ValueError("Mark anchor region must not be empty.")
        values = (self.x_center, self.y_root, self.extent, self.sweep_deg)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Mark anchor values must be finite.")
        if not 0.0 <= self.x_center <= 1.0 or not 0.0 <= self.y_root <= 1.0:
            raise ValueError("Mark anchor coordinates must be normalized.")
        if not 0.0 < self.extent <= 1.0:
            raise ValueError("Mark anchor extent must be between 0 and 1.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "region": self.region,
            "x_center": self.x_center,
            "y_root": self.y_root,
            "extent": self.extent,
            "sweep_deg": self.sweep_deg,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> MarkAnchor:
        return cls(
            region=str(data["region"]),
            x_center=float(data["x_center"]),
            y_root=float(data["y_root"]),
            extent=float(data["extent"]),
            sweep_deg=float(data.get("sweep_deg", 0.0)),
        )


@dataclass(frozen=True)
class StructuredMark:
    id: str
    label: str
    color_hex: str
    viewer_side: ViewerSide
    count: int = 1
    color_tolerance_delta_e: float = 6.0
    anchor: MarkAnchor | None = None
    mirror_side: MirrorSide = "none"
    shape_grammar: str = ""
    enforcement: MarkEnforcement = "both"

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.label.strip():
            raise ValueError("Structured mark ID and label must not be empty.")
        if not _HEX_COLOR.fullmatch(self.color_hex):
            raise ValueError("Structured mark color must be a #RRGGBB value.")
        if self.viewer_side not in {"viewer_left", "viewer_right"}:
            raise ValueError("Structured mark viewer side is invalid.")
        if self.count < 1:
            raise ValueError("Structured mark count must be at least 1.")
        if (
            not math.isfinite(self.color_tolerance_delta_e)
            or self.color_tolerance_delta_e <= 0.0
        ):
            raise ValueError("Structured mark color tolerance must be positive.")
        if self.mirror_side not in {"none", "viewer_left", "viewer_right"}:
            raise ValueError("Structured mark mirror side is invalid.")
        if self.enforcement not in {"steer", "seal", "both"}:
            raise ValueError("Structured mark enforcement is invalid.")
        if self.enforcement in {"seal", "both"} and self.anchor is None:
            raise ValueError("Sealed structured marks require an anchor.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "color_hex": self.color_hex.upper(),
            "viewer_side": self.viewer_side,
            "count": self.count,
            "color_tolerance_delta_e": self.color_tolerance_delta_e,
            "anchor": self.anchor.to_dict() if self.anchor else None,
            "mirror_side": self.mirror_side,
            "shape_grammar": self.shape_grammar,
            "enforcement": self.enforcement,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> StructuredMark:
        anchor = data.get("anchor")
        return cls(
            id=str(data["id"]),
            label=str(data["label"]),
            color_hex=str(data["color_hex"]),
            viewer_side=cast(ViewerSide, data["viewer_side"]),
            count=int(data.get("count", 1)),
            color_tolerance_delta_e=float(data.get("color_tolerance_delta_e", 6.0)),
            anchor=MarkAnchor.from_dict(anchor)
            if isinstance(anchor, Mapping)
            else None,
            mirror_side=cast(MirrorSide, data.get("mirror_side", "none")),
            shape_grammar=str(data.get("shape_grammar", "")),
            enforcement=cast(MarkEnforcement, data.get("enforcement", "both")),
        )
