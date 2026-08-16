"""Unit tests for the OpenAI vision adapter without network access."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.domain.exceptions import ProviderError
from infrastructure.providers.vision import openai_vision_provider as provider_module
from infrastructure.providers.vision.openai_vision_provider import OpenAIVisionProvider


@pytest.mark.asyncio
async def test_analyze_sends_base64_frames_and_maps_json(monkeypatch):
    captured: dict[str, object] = {}

    class FakeResponses:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                output_text=(
                    '{"relevance_score": 0.9, "scene_type": "city", '
                    '"lighting": "neon", "dominant_colors": ["blue"], '
                    '"indoors": false, "outdoors": true, '
                    '"camera_motion": "fast-paced", "people_present": false, '
                    '"vehicles_present": true, "confidence": 0.95}'
                )
            )

    monkeypatch.setattr(
        provider_module,
        "AsyncOpenAI",
        lambda **kwargs: SimpleNamespace(responses=FakeResponses()),
    )
    provider = OpenAIVisionProvider(api_key="test-key", model="test-model")

    result = await provider.analyze([b"jpeg-frame"], "energetic neon city")

    assert captured["model"] == "test-model"
    content = captured["input"][0]["content"]
    assert content[1]["type"] == "input_image"
    assert content[1]["image_url"].startswith("data:image/jpeg;base64,")
    assert result.relevance_score == 0.9
    assert result.camera_motion == "fast-paced"


@pytest.mark.asyncio
async def test_analyze_wraps_invalid_json_as_provider_error(monkeypatch):
    class FakeResponses:
        async def create(self, **kwargs):
            return SimpleNamespace(output_text="not-json")

    monkeypatch.setattr(
        provider_module,
        "AsyncOpenAI",
        lambda **kwargs: SimpleNamespace(responses=FakeResponses()),
    )
    provider = OpenAIVisionProvider(api_key="test-key", model="test-model")

    with pytest.raises(ProviderError, match="invalid JSON"):
        await provider.analyze([b"jpeg-frame"], "calm nature")
