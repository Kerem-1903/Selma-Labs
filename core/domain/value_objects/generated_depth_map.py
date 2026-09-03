from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GeneratedDepthMap:
    image_bytes: bytes
    content_type: str
    width: int
    height: int
    provider_asset_id: str = ""
