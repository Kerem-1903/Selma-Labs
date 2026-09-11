from __future__ import annotations

import base64
import hashlib
from io import BytesIO

from PIL import Image

from core.domain.ports.keyframe_generation_port import KeyframeGenerationPort
from core.domain.value_objects.generated_keyframe import GeneratedKeyframe
from core.domain.value_objects.keyframe_generation_request import KeyframeGenerationRequest


class FakeKeyframeGenerationProvider(KeyframeGenerationPort):
    """Deterministic offline adapter for tests and pipeline smoke checks."""

    _PNG = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )

    def __init__(self, *, sized_output: bool = False) -> None:
        self.requests: list[KeyframeGenerationRequest] = []
        self._sized_output = sized_output

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
        image_bytes = self._PNG
        if self._sized_output:
            image = Image.new("RGB", (request.width, request.height), (32, 42, 52))
            output = BytesIO()
            image.save(output, format="PNG", optimize=True)
            image_bytes = output.getvalue()
        return GeneratedKeyframe(
            image_bytes=image_bytes,
            content_type="image/png",
            width=request.width,
            height=request.height,
            provider_asset_id=f"fake-{request_digest}",
            metadata={"offline": True},
        )
