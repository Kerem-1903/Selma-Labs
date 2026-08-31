from __future__ import annotations

from dataclasses import dataclass

from core.domain.value_objects.render_profile import RenderProfile


@dataclass(frozen=True)
class AssembledVideo:
    storage_key: str
    content_type: str
    clip_ids: tuple[str, ...]
    profile: RenderProfile
    width: int
    height: int
    fps: float
    duration_seconds: float
    size_bytes: int
