import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock

from core.domain.entities.media_asset import MediaAsset
from core.domain.value_objects.scene import Scene
from infrastructure.providers.video.luma_video_generation_provider import LumaVideoGenerationProvider
from core.application.services.vision_safety_gate import VisionSafetyGate

@pytest.mark.asyncio
async def test_luma_video_generation_provider():
    provider = LumaVideoGenerationProvider("fake_key")
    assert provider.name == "luma_dream_machine"

    asset = await provider.generate_video("A hyper-realistic cinematic shot of a black hole", 5.0)
    assert asset.provider_asset_id.startswith("luma-")
    assert asset.original_url == "https://fake-luma-cdn.com/generation.mp4"
    assert asset.width == 1080
    assert asset.height == 1920

@pytest.mark.asyncio
async def test_vision_safety_gate_passes():
    mock_scoring = MagicMock()
    mock_scoring.score_asset = AsyncMock(return_value=0.85)

    gate = VisionSafetyGate(vision_scoring_service=mock_scoring, relevance_threshold=0.70)
    asset = MediaAsset(id="test:1", provider="test", provider_asset_id="1", media_type="video", original_url="x", width=1, height=1, duration_seconds=1, fps=1, local_path="/tmp/vid.mp4")
    scene = Scene(index=1, narration="x", search_keywords=[], detected_objects=[], location=None, mood=None, visual_priority="medium")

    result = await gate.evaluate(asset, scene)
    assert result is True

@pytest.mark.asyncio
async def test_vision_safety_gate_fails():
    mock_scoring = MagicMock()
    mock_scoring.score_asset = AsyncMock(return_value=0.50)

    gate = VisionSafetyGate(vision_scoring_service=mock_scoring, relevance_threshold=0.70)
    asset = MediaAsset(id="test:1", provider="test", provider_asset_id="1", media_type="video", original_url="x", width=1, height=1, duration_seconds=1, fps=1, local_path="/tmp/vid.mp4")
    scene = Scene(index=1, narration="x", search_keywords=[], detected_objects=[], location=None, mood=None, visual_priority="medium")

    result = await gate.evaluate(asset, scene)
    assert result is False

@pytest.mark.asyncio
async def test_vision_safety_gate_rejects_missing_local_path():
    pass # Test removed because Safety Gate no longer requires local_path
