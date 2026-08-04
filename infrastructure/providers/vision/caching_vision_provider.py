import hashlib
import json
import logging
from typing import List

from core.domain.ports.vision_analysis_port import VisionAnalysisPort
from core.domain.value_objects.vision_analysis_result import VisionAnalysisResult

logger = logging.getLogger(__name__)


class CachingVisionProvider(VisionAnalysisPort):
    def __init__(self, inner_provider: VisionAnalysisPort, prompt_version: str) -> None:
        self._inner = inner_provider
        self._prompt_version = prompt_version
        self._cache: dict[str, VisionAnalysisResult] = {}

    @property
    def provider_identity(self) -> str:
        return f"cached({self._inner.provider_identity})"

    def _compute_key(self, frame_bytes: List[bytes], scene_context: str) -> str:
        frame_hashes = [hashlib.sha256(b).hexdigest() for b in frame_bytes]
        payload = json.dumps({
            "model": self._inner.provider_identity,
            "prompt_version": self._prompt_version,
            "scene_context": scene_context,
            "frames": frame_hashes
        }, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    async def analyze(self, frame_bytes: List[bytes], scene_context: str) -> VisionAnalysisResult:
        key = self._compute_key(frame_bytes, scene_context)
        if key in self._cache:
            logger.info(f"Vision cache hit for key {key[:8]}...")
            return self._cache[key]

        logger.info(f"Vision cache miss for key {key[:8]}..., calling inner provider")
        result = await self._inner.analyze(frame_bytes, scene_context)
        self._cache[key] = result
        return result
