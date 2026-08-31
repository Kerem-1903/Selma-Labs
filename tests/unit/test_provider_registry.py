import pytest
from config.provider_registry import (
    get_asset_selection_service,
    get_audio_mix_provider,
    get_background_music_provider,
    get_fact_check_provider,
    get_fact_source_provider,
    get_media_inspection_provider,
    get_image_to_video_generation_provider,
    get_pipeline_video_source_provider,
    get_render_provider,
    get_scene_planning_provider,
    get_script_provider,
    get_script_rewriter_provider,
    get_topic_selection_provider,
    get_translation_provider,
    get_trend_source_provider,
    get_video_source_provider,
    get_voice_provider,
)
from config.settings import Settings
from infrastructure.providers.render.ffmpeg_render_provider import FfmpegRenderProvider
from infrastructure.providers.render.remotion_render_provider import RemotionRenderProvider
from infrastructure.providers.audio_mix.ffmpeg_audio_mix_provider import FfmpegAudioMixProvider
from infrastructure.providers.music.local_licensed_music_provider import LocalLicensedMusicProvider
from infrastructure.providers.fact_check.nvidia_fact_check_provider import NvidiaFactCheckProvider
from infrastructure.providers.fact_source.wikipedia_fact_source_provider import WikipediaFactSourceProvider
from infrastructure.providers.render.ffprobe_media_inspection_provider import (
    FfprobeMediaInspectionProvider,
)
from infrastructure.providers.scene_planning.claude_scene_planning_provider import ClaudeScenePlanningProvider
from infrastructure.providers.scene_planning.nvidia_scene_planning_provider import NvidiaScenePlanningProvider
from infrastructure.providers.script.nvidia_script_provider import NvidiaScriptProvider
from infrastructure.providers.script.nvidia_fact_grounded_rewriter import NvidiaFactGroundedRewriter
from infrastructure.providers.translation.caching_translation_provider import CachingTranslationProvider
from infrastructure.providers.topic_selection.nvidia_topic_selection_provider import NvidiaTopicSelectionProvider
from infrastructure.providers.trend.youtube_most_popular_provider import YoutubeMostPopularProvider
from infrastructure.providers.video.pexels_provider import PexelsProvider
from infrastructure.providers.video.orchestrated_video_source_provider import (
    OrchestratedVideoSourceProvider,
)
from infrastructure.providers.video.fake_image_to_video_provider import (
    FakeImageToVideoProvider,
)
from infrastructure.providers.voice.caching_voice_provider import CachingVoiceProvider
from infrastructure.providers.vision.caching_vision_provider import CachingVisionProvider


def test_get_translation_provider_success():
    settings = Settings(anthropic_api_key="test-key", translation_provider="claude")
    provider = get_translation_provider(settings)
    assert isinstance(provider, CachingTranslationProvider)


def test_get_nvidia_script_provider_success():
    settings = Settings(nvidia_api_key="test-key", script_provider="nvidia")
    assert isinstance(get_script_provider(settings), NvidiaScriptProvider)
    assert isinstance(get_script_rewriter_provider(settings), NvidiaFactGroundedRewriter)


def test_get_fact_check_providers_success():
    settings = Settings(
        nvidia_api_key="test-key",
        fact_check_fallback_provider="none", fact_check_provider="nvidia",
    )
    assert isinstance(get_fact_source_provider(settings), WikipediaFactSourceProvider)
    assert isinstance(get_fact_check_provider(settings), NvidiaFactCheckProvider)


def test_fact_source_uses_content_language_and_default_as_fallback():
    settings = Settings(
        fact_check_source_language="en",
        fact_check_fallback_languages="tr,de",
    )

    provider = get_fact_source_provider(settings, language="tr")

    assert provider._language == "tr"
    assert provider._fallback_languages == ("en", "de")


def test_fact_check_uses_fast_primary_and_independent_audit_models():
    settings = Settings(
        nvidia_api_key="test-key",
        fact_check_fallback_provider="none", fact_check_provider="nvidia",
        nvidia_fact_check_model="meta/llama-3.1-8b-instruct",
        nvidia_fact_check_audit_model="nvidia/llama-3.1-nemotron-nano-8b-v1",
    )

    provider = get_fact_check_provider(settings)

    assert provider._model == "meta/llama-3.1-8b-instruct"
    assert provider._audit_model == "nvidia/llama-3.1-nemotron-nano-8b-v1"


def test_get_premium_audio_providers_success():
    settings = Settings(background_music_dir="assets/music")
    assert isinstance(get_background_music_provider(settings), LocalLicensedMusicProvider)
    assert isinstance(get_audio_mix_provider(settings), FfmpegAudioMixProvider)


def test_get_trend_providers_success():
    settings = Settings(
        youtube_data_api_key="test-key",
        nvidia_api_key="test-key",
    )
    assert isinstance(get_trend_source_provider(settings), YoutubeMostPopularProvider)
    assert isinstance(get_topic_selection_provider(settings), NvidiaTopicSelectionProvider)


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


def test_get_local_voice_clone_provider_success():
    from infrastructure.providers.voice.local_voice_clone_provider import LocalVoiceCloneProvider
    from pathlib import Path

    settings = Settings(
        voice_provider="local_xtts",
        local_voice_reference_path="output/user_uploads/voice_reference.wav",
        voice_cache_enabled=False,
    )

    provider = get_voice_provider(settings)
    assert isinstance(provider, LocalVoiceCloneProvider)
    assert Path(provider.reference_audio_path).name == "voice_reference.wav"

def test_get_video_source_provider_success():
    settings = Settings(pexels_api_key="test-key", video_provider="pexels")
    provider = get_video_source_provider(settings)
    assert isinstance(provider, PexelsProvider)


def test_get_fake_image_to_video_provider_success():
    provider = get_image_to_video_generation_provider(
        Settings(image_to_video_provider="fake")
    )
    assert isinstance(provider, FakeImageToVideoProvider)


def test_comfyui_image_to_video_provider_requires_storage():
    with pytest.raises(ValueError, match="requires"):
        get_image_to_video_generation_provider(
            Settings(image_to_video_provider="comfyui")
        )


def test_get_pipeline_video_source_provider_builds_integrated_stack():
    settings = Settings(pexels_api_key="test-key", video_provider="pexels")

    provider = get_pipeline_video_source_provider(settings)

    assert isinstance(provider, OrchestratedVideoSourceProvider)


def test_get_asset_selection_service_success():
    settings = Settings()

    assert get_asset_selection_service(settings) is not None


def test_get_scene_planning_provider_success():
    settings = Settings(anthropic_api_key="test-key", scene_planning_provider="claude")
    provider = get_scene_planning_provider(settings)
    assert isinstance(provider, ClaudeScenePlanningProvider)


def test_get_nvidia_scene_planning_provider_success():
    settings = Settings(nvidia_api_key="test-key", scene_planning_provider="nvidia")
    provider = get_scene_planning_provider(settings)
    assert isinstance(provider, NvidiaScenePlanningProvider)


def test_get_render_provider_success():
    settings = Settings(render_provider="ffmpeg")
    provider = get_render_provider(settings)
    assert isinstance(provider, FfmpegRenderProvider)


def test_get_remotion_render_provider_success():
    settings = Settings(render_provider="remotion")

    provider = get_render_provider(settings)

    assert isinstance(provider, RemotionRenderProvider)


def test_get_media_inspection_provider_success():
    settings = Settings(render_provider="ffmpeg")

    provider = get_media_inspection_provider(settings)

    assert isinstance(provider, FfprobeMediaInspectionProvider)


def test_get_openai_vision_scoring_service_success():
    from config.provider_registry import get_vision_asset_scoring_service

    settings = Settings(
        openai_api_key="test-key",
        vision_provider="openai",
    )

    service = get_vision_asset_scoring_service(settings)

    assert isinstance(service._vision_provider, CachingVisionProvider)
