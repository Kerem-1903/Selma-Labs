from __future__ import annotations

import hashlib

from core.domain.ports.image_to_video_generation_port import ImageToVideoGenerationPort
from core.domain.value_objects.generated_video_clip import GeneratedVideoClip
from core.domain.value_objects.image_to_video_request import ImageToVideoRequest


class FakeImageToVideoProvider(ImageToVideoGenerationPort):
    def __init__(self) -> None:
        self.requests: list[ImageToVideoRequest] = []

    @property
    def name(self) -> str:
        return "fake:image-to-video"

    async def generate_video(self, request: ImageToVideoRequest) -> GeneratedVideoClip:
        self.requests.append(request)
        asset_id = hashlib.sha256(repr(request).encode("utf-8")).hexdigest()[:16]
        return GeneratedVideoClip(
            video_bytes=b"\x00\x00\x00\x18ftypmp42SELMA-A8",
            content_type="video/mp4",
            width=request.width,
            height=request.height,
            duration_seconds=request.target_duration_seconds,
            fps=request.fps,
            provider_asset_id=asset_id,
            metadata={"source_image_storage_key": request.source_image_storage_key},
        )
