from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class BlenderRenderManifest:
    render_id: str
    frame_count: int
    avg_frame_time_ms: float
    resolution: str
    output_video_path: str
    engine: str = "EEVEE"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "render_id": self.render_id,
            "frame_count": self.frame_count,
            "avg_frame_time_ms": self.avg_frame_time_ms,
            "resolution": self.resolution,
            "output_video_path": self.output_video_path,
            "engine": self.engine,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BlenderRenderManifest":
        return cls(
            render_id=data["render_id"],
            frame_count=int(data["frame_count"]),
            avg_frame_time_ms=float(data["avg_frame_time_ms"]),
            resolution=data["resolution"],
            output_video_path=data["output_video_path"],
            engine=data.get("engine", "EEVEE"),
        )
