import pytest
from config.provider_registry import (
    get_render_provider,
    get_scene_planning_provider,
    get_translation_provider,
    get_video_source_provider,
    get_voice_provider,
)
from config.settings import Settings
from infrastructure.providers.render.ffmpeg_render_provider import FfmpegRenderProvider
from infrastructure.providers.scene_planning.claude_scene_planning_provider import ClaudeScenePlanningProvider
from infrastructure.providers.translation.caching_translation_provider import CachingTranslationProvider
from infrastructure.providers.video.pexels_provider import PexelsProvider
from infrastructure.providers.voice.caching_voice_provider import CachingVoiceProvider


def test_get_translation_provider_success():
    settings = Settings(anthropic_api_key="test-key", translation_provider="claude")
    provider = get_translation_provider(settings)
    assert isinstance(provider, CachingTranslationProvider)


def test_get_translation_provider_unsupported_raises_value_error():
    settings = Settings()
    # Force invalid provider value
    object.__setattr__(settings, "translation_provider", "unsupported_provider")
    with pytest.raises(ValueError, match="Unknown translation_provider configured"):
        get_translation_provider(settings)


def test_get_voice_provider_success():
    settings = Settings(elevenlabs_api_key="test-key", voice_provider="elevenlabs", voice_cache_enabled=True)
    provider = get_voice_provider(settings)
    assert isinstance(provider, CachingVoiceProvider)


def test_get_video_source_provider_success():
    settings = Settings(pexels_api_key="test-key", video_provider="pexels")
    provider = get_video_source_provider(settings)
    assert isinstance(provider, PexelsProvider)


def test_get_scene_planning_provider_success():
    settings = Settings(anthropic_api_key="test-key", scene_planning_provider="claude")
    provider = get_scene_planning_provider(settings)
    assert isinstance(provider, ClaudeScenePlanningProvider)


def test_get_render_provider_success():
    settings = Settings(render_provider="ffmpeg")
    provider = get_render_provider(settings)
    assert isinstance(provider, FfmpegRenderProvider)
