import hashlib
import json
import logging
from typing import List

from core.domain.ports.translation_port import TranslationPort

logger = logging.getLogger(__name__)


class CachingTranslationProvider(TranslationPort):
    def __init__(self, inner_provider: TranslationPort) -> None:
        self._inner = inner_provider
        self._cache: dict[str, List[str]] = {}

    @property
    def provider_identity(self) -> str:
        return f"cached({self._inner.provider_identity})"

    def _compute_key(self, texts: List[str], target_language: str) -> str:
        payload = json.dumps({"texts": texts, "target_language": target_language}, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    async def translate_texts(self, texts: List[str], target_language: str) -> List[str]:
        if not texts:
            return []

        key = self._compute_key(texts, target_language)
        if key in self._cache:
            logger.info(f"Translation cache hit for key {key[:8]}...")
            return list(self._cache[key])

        logger.info(f"Translation cache miss for key {key[:8]}..., calling inner provider")
        results = await self._inner.translate_texts(texts, target_language)
        self._cache[key] = list(results)
        
        return results
