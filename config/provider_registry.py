"""
provider_registry — maps configuration values to concrete provider
instances.

This is the one file that changes when a new provider is added or the
active provider is switched. Every service depends on a Port
(VoiceGeneratorPort, ScriptGeneratorPort, ...); this module is the only
place that knows which concrete class satisfies that Port for the current
configuration.

To add a new voice provider (e.g. OpenAI TTS):
  1. Implement VoiceGeneratorPort in infrastructure/providers/voice/openai_tts_provider.py
  2. Add "openai" as a branch below
  3. Add "openai" to Settings.voice_provider's allowed values in config/settings.py
No other file needs to change.
"""
from __future__ import annotations

from config.settings import Settings, get_settings
from core.application.services.search_cache_service import SearchCacheService
from core.application.services.search_orchestrator_service import SearchOrchestratorService
from core.application.services.asset_selection_service import AssetSelectionService
from core.application.services.vision_asset_scoring_service import VisionAssetScoringService
from core.application.selection.rules.asset_reuse_rule import AssetReuseRule
from core.application.selection.rules.keyword_fatigue_rule import KeywordFatigueRule
from core.application.selection.rules.provider_fatigue_rule import ProviderFatigueRule
from core.application.utils.resilient_provider_decorator import (
    ResilientSearchProviderDecorator,
)
from core.domain.exceptions import ProviderConnectionError, ProviderTimeoutError
from core.domain.ports.render_port import RenderPort
from core.domain.ports.audio_mix_port import AudioMixPort
from core.domain.ports.background_music_port import BackgroundMusicPort
from core.domain.ports.fact_check_port import FactCheckPort
from core.domain.ports.fact_source_port import FactSourcePort
from core.domain.ports.media_inspection_port import MediaInspectionPort
from core.domain.ports.scene_planning_port import ScenePlanningPort
from core.domain.ports.script_generator_port import ScriptGeneratorPort
from core.domain.ports.script_rewriter_port import ScriptRewriterPort
from core.domain.ports.translation_port import TranslationPort
from core.domain.ports.topic_selection_port import TopicSelectionPort
from core.domain.ports.trend_source_port import TrendSourcePort
from core.domain.ports.video_source_port import VideoSourcePort
from core.domain.ports.voice_generator_port import VoiceGeneratorPort
from infrastructure.providers.render.ffmpeg_render_provider import FfmpegRenderProvider
from infrastructure.providers.render.remotion_render_provider import RemotionRenderProvider
from infrastructure.providers.audio_mix.ffmpeg_audio_mix_provider import (
    FfmpegAudioMixProvider,
)
from infrastructure.providers.music.local_licensed_music_provider import (
    LocalLicensedMusicProvider,
)
from infrastructure.providers.fact_check.nvidia_fact_check_provider import (
    NvidiaFactCheckProvider,
)
from infrastructure.providers.fact_source.wikipedia_fact_source_provider import (
    WikipediaFactSourceProvider,
)
from infrastructure.providers.render.ffprobe_media_inspection_provider import (
    FfprobeMediaInspectionProvider,
)
from infrastructure.providers.frame_extraction.ffmpeg_frame_extractor import FfmpegFrameExtractor
from infrastructure.providers.vision.anthropic_vision_provider import AnthropicVisionProvider
from infrastructure.providers.vision.nvidia_vision_provider import NvidiaVisionProvider
from infrastructure.providers.vision.openai_vision_provider import OpenAIVisionProvider
from infrastructure.providers.vision.caching_vision_provider import CachingVisionProvider
from infrastructure.providers.scene_planning.claude_scene_planning_provider import (
    ClaudeScenePlanningProvider,
)
from infrastructure.providers.scene_planning.nvidia_scene_planning_provider import (
    NvidiaScenePlanningProvider,
)
from infrastructure.providers.script.claude_script_provider import ClaudeScriptProvider
from infrastructure.providers.script.nvidia_script_provider import NvidiaScriptProvider
from infrastructure.providers.script.nvidia_fact_grounded_rewriter import (
    NvidiaFactGroundedRewriter,
)
from infrastructure.providers.translation.caching_translation_provider import (
    CachingTranslationProvider,
)
from infrastructure.providers.translation.claude_translation_provider import (
    ClaudeTranslationProvider,
)
from infrastructure.providers.translation.nvidia_translation_provider import (
    NvidiaTranslationProvider,
)
from infrastructure.providers.topic_selection.nvidia_topic_selection_provider import (
    NvidiaTopicSelectionProvider,
)
from infrastructure.providers.trend.youtube_most_popular_provider import (
    YoutubeMostPopularProvider,
)
from infrastructure.providers.video.pexels_provider import PexelsProvider
from infrastructure.providers.video.orchestrated_video_source_provider import (
    OrchestratedVideoSourceProvider,
)
from infrastructure.providers.voice.caching_voice_provider import CachingVoiceProvider
from infrastructure.providers.voice.elevenlabs_provider import ElevenLabsVoiceProvider
from core.infrastructure.cache.in_memory_cache import InMemoryCache


def get_trend_source_provider(settings: Settings) -> TrendSourcePort:
    if settings.trend_source_provider == "youtube":
        return YoutubeMostPopularProvider(
            api_key=settings.youtube_data_api_key,
            min_duration_seconds=settings.trend_min_duration_seconds,
            max_duration_seconds=settings.trend_max_duration_seconds,
            timeout_seconds=settings.provider_timeout_seconds,
            search_query=settings.trend_search_query,
            relevance_language=settings.trend_relevance_language,
            published_within_days=settings.trend_published_within_days,
        )
    raise ValueError(
        f"Unknown trend_source_provider configured: {settings.trend_source_provider!r}. "
        "Supported: ['youtube']"
    )


def get_topic_selection_provider(settings: Settings) -> TopicSelectionPort:
    if settings.topic_selection_provider == "nvidia":
        return NvidiaTopicSelectionProvider(
            api_key=settings.nvidia_api_key,
            base_url=settings.nvidia_base_url,
            model=settings.nvidia_text_model,
            timeout_seconds=settings.nvidia_timeout_seconds,
            audit_model=settings.nvidia_vision_model,
        )
    raise ValueError(
        f"Unknown topic_selection_provider configured: "
        f"{settings.topic_selection_provider!r}. Supported: ['nvidia']"
    )


def get_fact_source_provider(
    settings: Settings,
    *,
    language: str | None = None,
) -> FactSourcePort:
    if settings.fact_source_provider == "wikipedia":
        primary_language = (language or settings.fact_check_source_language).strip().lower()
        fallback_candidates = (
            settings.fact_check_source_language,
            *settings.fact_check_fallback_languages.split(","),
        )
        return WikipediaFactSourceProvider(
            language=primary_language,
            fallback_languages=tuple(dict.fromkeys(
                candidate.strip().lower()
                for candidate in fallback_candidates
                if candidate.strip()
                and candidate.strip().lower() != primary_language
            )),
            timeout_seconds=settings.provider_timeout_seconds,
            max_extract_chars=settings.fact_check_max_extract_chars,
        )
    raise ValueError(
        f"Unknown fact_source_provider configured: {settings.fact_source_provider!r}. "
        "Supported: ['wikipedia']"
    )


def get_fact_check_provider(settings: Settings) -> FactCheckPort:
    if settings.fact_check_provider == "nvidia":
        primary = NvidiaFactCheckProvider(
            api_key=settings.nvidia_api_key,
            base_url=settings.nvidia_base_url,
            model=settings.nvidia_fact_check_model,
            timeout_seconds=settings.fact_check_primary_timeout_seconds,
            audit_model=settings.nvidia_fact_check_audit_model,
            max_retries=settings.fact_check_primary_max_retries,
        )
        if (
            settings.fact_check_fallback_provider == "openai"
            and settings.openai_api_key.strip()
        ):
            from infrastructure.providers.fact_check.fallback_fact_check_provider import (
                FallbackFactCheckProvider,
            )
            from infrastructure.providers.fact_check.openai_fact_check_provider import (
                OpenAIFactCheckProvider,
            )

            return FallbackFactCheckProvider(
                primary,
                OpenAIFactCheckProvider(
                    api_key=settings.openai_api_key,
                    model=settings.openai_fact_check_model,
                    timeout_seconds=settings.provider_timeout_seconds,
                ),
            )
        return primary
    raise ValueError(
        f"Unknown fact_check_provider configured: {settings.fact_check_provider!r}. "
        "Supported: ['nvidia']"
    )


def get_script_rewriter_provider(settings: Settings) -> ScriptRewriterPort:
    return NvidiaFactGroundedRewriter(
        api_key=settings.nvidia_api_key,
        base_url=settings.nvidia_base_url,
        model=settings.nvidia_text_model,
        timeout_seconds=settings.nvidia_timeout_seconds,
    )


def get_script_provider(settings: Settings) -> ScriptGeneratorPort:
    """Return the configured ScriptGeneratorPort implementation."""
    if settings.script_provider == "claude":
        return ClaudeScriptProvider(
            api_key=settings.anthropic_api_key,
            model=settings.script_model,
        )
    if settings.script_provider == "nvidia":
        return NvidiaScriptProvider(
            api_key=settings.nvidia_api_key,
            base_url=settings.nvidia_base_url,
            model=settings.nvidia_text_model,
            timeout_seconds=settings.nvidia_timeout_seconds,
        )
    raise ValueError(
        f"Unknown script_provider configured: {settings.script_provider!r}. "
        "Supported: ['claude', 'nvidia']"
    )


def get_voice_provider(settings: Settings) -> VoiceGeneratorPort:
    """Return the configured VoiceGeneratorPort implementation.

    If voice_cache_enabled is set, the returned provider is transparently
    wrapped in CachingVoiceProvider — VoiceService and every other caller
    still just see a VoiceGeneratorPort and have no way to tell whether
    caching is active underneath.
    """
    if settings.voice_provider == "elevenlabs":
        base_provider: VoiceGeneratorPort = ElevenLabsVoiceProvider(
            api_key=settings.elevenlabs_api_key,
            model_id=settings.elevenlabs_model_id,
            stability=settings.elevenlabs_stability,
            similarity_boost=settings.elevenlabs_similarity_boost,
            style=settings.elevenlabs_style,
            speed=settings.elevenlabs_speed,
            use_speaker_boost=settings.elevenlabs_use_speaker_boost,
        )
        provider_identity = (
            f"elevenlabs:{settings.elevenlabs_model_id}:"
            f"stability={settings.elevenlabs_stability}:"
            f"similarity={settings.elevenlabs_similarity_boost}:"
            f"style={settings.elevenlabs_style}:"
            f"speed={settings.elevenlabs_speed}:"
            f"boost={settings.elevenlabs_use_speaker_boost}"
        )
    else:
        raise ValueError(
            f"Unknown voice_provider configured: {settings.voice_provider!r}. "
            "Supported: ['elevenlabs']"
        )

    if settings.voice_cache_enabled:
        return CachingVoiceProvider(
            inner=base_provider,
            cache_dir=settings.voice_cache_dir,
            provider_identity=provider_identity,
        )
    return base_provider


def get_video_source_provider(settings: Settings) -> VideoSourcePort:
    """Return the configured VideoSourcePort implementation.

    Only "pexels" is supported in Sprint 3. Adding a new provider (e.g.
    Pixabay, Mixkit) follows the same three steps as adding a voice
    provider — see this module's docstring.
    """
    if settings.video_provider == "pexels":
        return PexelsProvider(api_key=settings.pexels_api_key)
    raise ValueError(
        f"Unknown video_provider configured: {settings.video_provider!r}. "
        "Supported: ['pexels']"
    )


def get_pipeline_video_source_provider(settings: Settings) -> VideoSourcePort:
    """Build the resilient, cached search stack used by the main pipeline."""
    base_provider = get_video_source_provider(settings)
    provider_name = getattr(base_provider, "name", settings.video_provider)
    resilient_provider = ResilientSearchProviderDecorator(
        inner_provider=base_provider,
        timeout_seconds=settings.provider_timeout_seconds,
        max_retries=settings.provider_max_retries,
        base_delay=settings.provider_retry_backoff,
        max_backoff=settings.provider_max_backoff,
        retryable_exceptions=(ProviderTimeoutError, ProviderConnectionError),
    )
    orchestrator = SearchOrchestratorService(
        providers=[resilient_provider], orchestrator_name="video_search"
    )
    search_provider = orchestrator
    if settings.search_cache_enabled:
        search_provider = SearchCacheService(
            provider=orchestrator,
            cache=InMemoryCache(max_entries=settings.search_cache_max_entries),
            provider_name=orchestrator.name,
            default_ttl=settings.search_cache_ttl_seconds,
            negative_ttl=settings.search_cache_negative_ttl_seconds,
        )
    return OrchestratedVideoSourceProvider(
        search_provider=search_provider,
        download_providers={provider_name: base_provider},
    )


def get_asset_selection_service(settings: Settings) -> AssetSelectionService:
    return AssetSelectionService(
        rules=[
            AssetReuseRule(settings.asset_reuse_penalty),
            ProviderFatigueRule(settings.provider_fatigue_penalty),
            KeywordFatigueRule(settings.keyword_fatigue_penalty),
        ],
        provider_window=settings.asset_selection_provider_window,
        keyword_window=settings.asset_selection_keyword_window,
        top_k=settings.asset_selection_top_k,
    )


def get_vision_asset_scoring_service(settings: Settings) -> VisionAssetScoringService:
    if settings.vision_provider == "anthropic":
        base_provider = AnthropicVisionProvider(
            api_key=settings.anthropic_api_key,
            model_name=settings.vision_model,
        )
    elif settings.vision_provider == "openai":
        base_provider = OpenAIVisionProvider(
            api_key=settings.openai_api_key,
            model=settings.openai_vision_model,
            timeout_seconds=settings.provider_timeout_seconds,
        )
    elif settings.vision_provider == "nvidia":
        base_provider = NvidiaVisionProvider(
            api_key=settings.nvidia_api_key,
            base_url=settings.nvidia_base_url,
            model=settings.nvidia_vision_model,
            timeout_seconds=settings.nvidia_timeout_seconds,
        )
    else:
        raise ValueError(
            f"Unknown vision_provider configured: {settings.vision_provider!r}. "
            "Supported: ['anthropic', 'nvidia', 'openai']"
        )
    fallback_provider = None
    if (
        settings.vision_fallback_provider == "nvidia"
        and settings.vision_provider != "nvidia"
        and settings.nvidia_api_key.strip()
    ):
        fallback_provider = NvidiaVisionProvider(
            api_key=settings.nvidia_api_key,
            base_url=settings.nvidia_base_url,
            model=settings.nvidia_vision_model,
            timeout_seconds=settings.nvidia_timeout_seconds,
        )
    elif (
        settings.vision_fallback_provider == "openai"
        and settings.vision_provider != "openai"
        and settings.openai_api_key.strip()
    ):
        fallback_provider = OpenAIVisionProvider(
            api_key=settings.openai_api_key,
            model=settings.openai_vision_model,
            timeout_seconds=settings.provider_timeout_seconds,
        )
    if fallback_provider is not None:
        from infrastructure.providers.vision.fallback_vision_provider import (
            FallbackVisionProvider,
        )

        base_provider = FallbackVisionProvider(
            base_provider,
            fallback_provider,
        )
    vision_provider = CachingVisionProvider(base_provider, prompt_version="v1")
    return VisionAssetScoringService(
        frame_extractor=FfmpegFrameExtractor(
            ffmpeg_binary=settings.ffmpeg_binary_path,
            max_width=640,
        ),
        vision_provider=vision_provider,
        frames_per_asset=settings.vision_frames_per_asset,
        top_candidates=settings.vision_top_candidates,
        max_concurrency=settings.vision_max_concurrency,
        vision_weight=settings.vision_weight,
    )


def get_scene_planning_provider(settings: Settings) -> ScenePlanningPort:
    """Return the configured ScenePlanningPort implementation.

    Supports Anthropic Claude and NVIDIA's OpenAI-compatible endpoint.
    """
    if settings.scene_planning_provider == "claude":
        return ClaudeScenePlanningProvider(
            api_key=settings.anthropic_api_key, model=settings.scene_planner_model
        )
    if settings.scene_planning_provider == "nvidia":
        return NvidiaScenePlanningProvider(
            api_key=settings.nvidia_api_key,
            base_url=settings.nvidia_base_url,
            model=settings.nvidia_text_model,
            timeout_seconds=settings.nvidia_timeout_seconds,
        )
    raise ValueError(
        f"Unknown scene_planning_provider configured: "
        f"{settings.scene_planning_provider!r}. Supported: ['claude', 'nvidia']"
    )


def get_render_provider(settings: Settings) -> RenderPort:
    """Return the configured RenderPort implementation.

    Remotion supplies the creative composition and FFmpeg supplies delivery
    mastering. The original FFmpeg-only path remains available as fallback.
    nvenc allows fast hardware accelerated rendering with ducking.
    """
    if settings.render_provider == "nvenc":
        from infrastructure.providers.render.nvenc_fast_render_adapter import NVENCFastRenderAdapter
        return NVENCFastRenderAdapter(
            ffmpeg_path=settings.ffmpeg_binary_path,
            use_gpu=True,
            timeout_seconds=settings.remotion_subprocess_timeout_seconds
        )
    if settings.render_provider == "ffmpeg":
        return FfmpegRenderProvider(
            ffmpeg_binary=settings.ffmpeg_binary_path,
            ffprobe_binary=settings.ffprobe_binary_path,
            output_width=settings.render_output_width,
            output_height=settings.render_output_height,
            fps=settings.render_fps,
        )
    if settings.render_provider == "remotion":
        fallback = FfmpegRenderProvider(
            ffmpeg_binary=settings.ffmpeg_binary_path,
            ffprobe_binary=settings.ffprobe_binary_path,
            output_width=settings.render_output_width,
            output_height=settings.render_output_height,
            fps=settings.render_fps,
            background_music_volume=settings.background_music_volume,
        )
        return RemotionRenderProvider(
            project_directory=settings.remotion_project_dir,
            remotion_cli_path=settings.remotion_cli_path,
            ffmpeg_binary=settings.ffmpeg_binary_path,
            ffmpeg_fallback=fallback,
            subprocess_timeout_seconds=settings.remotion_subprocess_timeout_seconds,
            background_music_volume=settings.background_music_volume,
        )
    raise ValueError(
        f"Unknown render_provider configured: {settings.render_provider!r}. "
        "Supported: ['ffmpeg', 'remotion']"
    )


def get_background_music_provider(settings: Settings) -> BackgroundMusicPort:
    if settings.background_music_provider == "local":
        return LocalLicensedMusicProvider(settings.background_music_dir)
    raise ValueError(
        f"Unknown background_music_provider: {settings.background_music_provider!r}."
    )


def get_audio_mix_provider(settings: Settings) -> AudioMixPort:
    if settings.audio_mix_provider == "ffmpeg":
        return FfmpegAudioMixProvider(settings.ffmpeg_binary_path)
    raise ValueError(f"Unknown audio_mix_provider: {settings.audio_mix_provider!r}.")


def get_media_inspection_provider(settings: Settings) -> MediaInspectionPort:
    return FfprobeMediaInspectionProvider(
        ffmpeg_binary=settings.ffmpeg_binary_path,
        ffprobe_binary=settings.ffprobe_binary_path,
    )


def get_translation_provider(settings: Settings | None = None) -> TranslationPort:
    """Return the configured TranslationPort implementation."""
    if settings is None:
        settings = get_settings()
    if settings.translation_provider == "claude":
        base_provider = ClaudeTranslationProvider(api_key=settings.anthropic_api_key)
        return CachingTranslationProvider(base_provider)
    if settings.translation_provider == "nvidia":
        base_provider = NvidiaTranslationProvider(
            api_key=settings.nvidia_api_key,
            base_url=settings.nvidia_base_url,
            model=settings.nvidia_text_model,
            timeout_seconds=settings.nvidia_timeout_seconds,
        )
        return CachingTranslationProvider(base_provider)
    raise ValueError(
        f"Unknown translation_provider configured: {settings.translation_provider!r}. "
        "Supported: ['claude', 'nvidia']"
    )
