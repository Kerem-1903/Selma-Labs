from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class GeneratedVideoClip:
    video_bytes: bytes
    content_type: str
    width: int
    height: int
    duration_seconds: float
    fps: float
    provider_asset_id: str
    metadata: dict[str, Any] = field(default_factory=dict)
