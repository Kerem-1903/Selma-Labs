import pytest
from typing import List
from core.domain.ports.translation_port import TranslationPort
from infrastructure.providers.translation.caching_translation_provider import CachingTranslationProvider


class MockTranslationPort(TranslationPort):
    def __init__(self):
        self.call_count = 0

    @property
    def provider_identity(self) -> str:
        return "mock"

    async def translate_texts(self, texts: List[str], target_language: str) -> List[str]:
        self.call_count += 1
        return [f"trans {t}" for t in texts]


@pytest.mark.asyncio
async def test_cache_hit_prevents_duplicate_calls():
    inner = MockTranslationPort()
    cached = CachingTranslationProvider(inner_provider=inner)

    texts = ["a", "b"]
    res1 = await cached.translate_texts(texts, "fr")
    assert inner.call_count == 1
    assert res1 == ["trans a", "trans b"]

    res2 = await cached.translate_texts(texts, "fr")
    assert inner.call_count == 1
    assert res2 == res1
