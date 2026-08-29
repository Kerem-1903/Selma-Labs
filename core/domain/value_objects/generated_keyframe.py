from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class GeneratedKeyframe:
    """Provider-neutral image bytes returned by a keyframe generator."""

    image_bytes: bytes
    content_type: str
    width: int
    height: int
    provider_asset_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
