from __future__ import annotations

import base64
import hashlib

from core.domain.ports.keyframe_generation_port import KeyframeGenerationPort
from core.domain.value_objects.generated_keyframe import GeneratedKeyframe
from core.domain.value_objects.keyframe_generation_request import KeyframeGenerationRequest


class FakeKeyframeGenerationProvider(KeyframeGenerationPort):
    """Deterministic offline adapter for tests and pipeline smoke checks."""

    _PNG = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )

    def __init__(self) -> None:
        self.requests: list[KeyframeGenerationRequest] = []

    @property
    def name(self) -> str:
        return "fake:keyframe"

    async def generate_keyframe(
        self, request: KeyframeGenerationRequest
    ) -> GeneratedKeyframe:
        self.requests.append(request)
        request_digest = hashlib.sha256(
            repr(request.to_dict()).encode("utf-8")
        ).hexdigest()[:24]
        return GeneratedKeyframe(
            image_bytes=self._PNG,
            content_type="image/png",
            width=request.width,
            height=request.height,
            provider_asset_id=f"fake-{request_digest}",
            metadata={"offline": True},
        )
