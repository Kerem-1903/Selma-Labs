"""
Unit tests for ScriptService.

These tests never touch the network or the Anthropic API — that's the
entire point of coding against ScriptGeneratorPort. FakeScriptProvider
below is a minimal in-memory implementation of the port, used only in
tests, proving the port is genuinely swappable.
"""
from __future__ import annotations

import pytest

from core.application.services.script_service import ScriptService
from core.domain.entities.script import Script
from core.domain.exceptions import ScriptGenerationError
from core.domain.ports.script_generator_port import ScriptGeneratorPort


class FakeScriptProvider(ScriptGeneratorPort):
    """In-memory ScriptGeneratorPort implementation for tests."""

    def __init__(self, text: str) -> None:
        self._text = text

    async def generate_script(self, topic: str, target_duration_seconds: int) -> Script:
        return Script.create(
            topic=topic,
            full_text=self._text,
            target_duration_seconds=target_duration_seconds,
            provider_used="fake",
        )


def _words(n: int) -> str:
    return " ".join("word" for _ in range(n))


@pytest.mark.asyncio
async def test_generate_returns_script_within_expected_word_range():
    # 45s target -> ~112 expected words at 150 wpm; 110 is comfortably in range
    provider = FakeScriptProvider(_words(110))
    service = ScriptService(provider)

    script = await service.generate("Test topic", target_duration_seconds=45)

    assert script.topic == "Test topic"
    assert script.estimated_word_count == 110
    assert script.provider_used == "fake"


@pytest.mark.asyncio
async def test_rejects_empty_topic():
    service = ScriptService(FakeScriptProvider(_words(100)))

    with pytest.raises(ScriptGenerationError, match="Topic must not be empty"):
        await service.generate("   ", target_duration_seconds=45)


@pytest.mark.asyncio
async def test_rejects_duration_below_minimum():
    service = ScriptService(FakeScriptProvider(_words(100)))

    with pytest.raises(ScriptGenerationError, match="target_duration_seconds"):
        await service.generate("Topic", target_duration_seconds=5)


@pytest.mark.asyncio
async def test_rejects_duration_above_maximum():
    service = ScriptService(FakeScriptProvider(_words(100)))

    with pytest.raises(ScriptGenerationError, match="target_duration_seconds"):
        await service.generate("Topic", target_duration_seconds=200)


@pytest.mark.asyncio
async def test_rejects_script_too_short_for_target_duration():
    # 5 words for a 45s (~112 word) target is far below the 0.5x floor
    provider = FakeScriptProvider(_words(5))
    service = ScriptService(provider)

    with pytest.raises(ScriptGenerationError, match="outside the expected range"):
        await service.generate("Topic", target_duration_seconds=45)


@pytest.mark.asyncio
async def test_rejects_script_too_long_for_target_duration():
    # 300 words for a 15s (~37 word) target is far above the 1.6x ceiling
    provider = FakeScriptProvider(_words(300))
    service = ScriptService(provider)

    with pytest.raises(ScriptGenerationError, match="outside the expected range"):
        await service.generate("Topic", target_duration_seconds=15)


@pytest.mark.asyncio
async def test_rejects_empty_provider_output():
    provider = FakeScriptProvider("   ")
    service = ScriptService(provider)

    with pytest.raises(ScriptGenerationError, match="empty"):
        await service.generate("Topic", target_duration_seconds=45)
