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
from core.domain.ports.render_port import RenderPort
from core.domain.ports.scene_planning_port import ScenePlanningPort
from core.domain.ports.translation_port import TranslationPort
from core.domain.ports.video_source_port import VideoSourcePort
from core.domain.ports.voice_generator_port import VoiceGeneratorPort
from infrastructure.providers.render.ffmpeg_render_provider import FfmpegRenderProvider
from infrastructure.providers.scene_planning.claude_scene_planning_provider import (
    ClaudeScenePlanningProvider,
)
from infrastructure.providers.translation.caching_translation_provider import (
    CachingTranslationProvider,
)
from infrastructure.providers.translation.claude_translation_provider import (
    ClaudeTranslationProvider,
)
from infrastructure.providers.video.pexels_provider import PexelsProvider
from infrastructure.providers.voice.caching_voice_provider import CachingVoiceProvider
from infrastructure.providers.voice.elevenlabs_provider import ElevenLabsVoiceProvider


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
        )
        provider_identity = f"elevenlabs:{settings.elevenlabs_model_id}"
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


def get_scene_planning_provider(settings: Settings) -> ScenePlanningPort:
    """Return the configured ScenePlanningPort implementation.

    Only "claude" is supported in Sprint 4. Adding a new provider follows
    the same three steps as adding a voice or video provider — see this
    module's docstring.
    """
    if settings.scene_planning_provider == "claude":
        return ClaudeScenePlanningProvider(
            api_key=settings.anthropic_api_key, model=settings.scene_planner_model
        )
    raise ValueError(
        f"Unknown scene_planning_provider configured: "
        f"{settings.scene_planning_provider!r}. Supported: ['claude']"
    )


def get_render_provider(settings: Settings) -> RenderPort:
    """Return the configured RenderPort implementation.

    Only "ffmpeg" is supported in Sprint 7. Adding a new provider (e.g. a
    cloud rendering API, Remotion) follows the same three steps as adding
    any other provider -- see this module's docstring.
    """
    if settings.render_provider == "ffmpeg":
        return FfmpegRenderProvider(
            ffmpeg_binary=settings.ffmpeg_binary_path,
            ffprobe_binary=settings.ffprobe_binary_path,
            output_width=settings.render_output_width,
            output_height=settings.render_output_height,
            fps=settings.render_fps,
        )
    raise ValueError(
        f"Unknown render_provider configured: {settings.render_provider!r}. "
        "Supported: ['ffmpeg']"
    )


def get_translation_provider(settings: Settings | None = None) -> TranslationPort:
    """Return the configured TranslationPort implementation."""
    if settings is None:
        settings = get_settings()
    if settings.translation_provider == "claude":
        base_provider = ClaudeTranslationProvider(api_key=settings.anthropic_api_key)
        return CachingTranslationProvider(base_provider)
    raise ValueError(
        f"Unknown translation_provider configured: {settings.translation_provider!r}. "
        "Supported: ['claude']"
    )

