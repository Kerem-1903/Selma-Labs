"""
Application configuration, environment-variable driven.

Deliberately not instantiated at import time: constructing Settings() at
module load would make every test that imports this module fail without a
.env file present. get_settings() builds it lazily, once, and caches the
result — call sites that need config call get_settings(), they never
construct Settings() themselves.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Optional (default "") rather than required, as of Sprint 2: Settings
    # now covers multiple providers, and a voice-only test run shouldn't be
    # forced to also supply an Anthropic key it doesn't use. Each adapter
    # still fails fast with a clear ProviderAuthError if its own key is
    # missing at construction time — the fail-fast guarantee moved from
    # "at config load" to "at the point a provider is actually used,"
    # which is the correct place for it once more than one provider exists.
    anthropic_api_key: str = ""
    # Check https://docs.claude.com for the current recommended model string
    # before running — model identifiers change over time.
    script_model: str = "claude-sonnet-4-5"
    default_target_duration_seconds: int = 45

    # Voice generation (Sprint 2). voice_provider is the single switch that
    # selects an adapter via config/provider_registry.py — add new literal
    # values here as new adapters are implemented.
    voice_provider: Literal["elevenlabs"] = "elevenlabs"
    elevenlabs_api_key: str = ""
    elevenlabs_model_id: str = "eleven_multilingual_v2"
    # "Rachel" — a commonly-used default preset voice on ElevenLabs.
    # Override via ELEVENLABS_VOICE_ID or the CLI's --voice-id flag.
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM"

    storage_root_dir: str = "output"

    # Voice caching (Sprint 2.1). Transparent to VoiceService — see
    # CachingVoiceProvider's docstring. Enabled by default since it's pure
    # upside during development (repeated test runs on the same topic don't
    # re-spend ElevenLabs quota); disable if you specifically need to force
    # regeneration.
    voice_cache_enabled: bool = True
    voice_cache_dir: str = "cache/voice"

    # Visual asset discovery (Sprint 3). video_provider is the single
    # switch that selects an adapter via config/provider_registry.py, same
    # pattern as voice_provider above.
    video_provider: Literal["pexels"] = "pexels"
    pexels_api_key: str = ""
    default_video_max_results: int = 10

    # Scene planning (Sprint 4). Reuses anthropic_api_key above -- same
    # Anthropic account, a separate model setting because scene planning's
    # prompt/output shape is different enough from script generation that
    # tuning one shouldn't be forced to also affect the other.
    scene_planning_provider: Literal["claude"] = "claude"
    scene_planner_model: str = "claude-sonnet-4-5"

    # Subtitle translation provider switch.
    translation_provider: Literal["claude"] = "claude"

    # Video rendering (Sprint 7). render_provider is the single switch that
    # selects an adapter via config/provider_registry.py, same pattern as
    # voice_provider/video_provider/scene_planning_provider above. FFmpeg is
    # invoked as a local subprocess, not an HTTP API, so there is no API key
    # setting here -- just the binary names (override if not on PATH) and
    # the output profile every rendered video is normalized to.
    render_provider: Literal["ffmpeg"] = "ffmpeg"
    ffmpeg_binary_path: str = "ffmpeg"
    ffprobe_binary_path: str = "ffprobe"
    render_output_width: int = 1080
    render_output_height: int = 1920
    render_fps: int = 30

    # Asset selection (Sprint 15.x)
    asset_reuse_penalty: float = 0.8
    provider_fatigue_penalty: float = 0.2
    keyword_fatigue_penalty: float = 0.1
    asset_selection_provider_window: int = 3
    asset_selection_keyword_window: int = 15
    asset_selection_top_k: int = 5

    # Search cache (Sprint 16)
    search_cache_enabled: bool = True
    search_cache_ttl_seconds: float = 300.0
    search_cache_max_entries: int = 1000

    # Provider resilience (Sprint 17)
    provider_timeout_seconds: float = 2.0
    provider_max_retries: int = 2
    provider_retry_backoff: float = 0.5
    provider_max_backoff: float = 30.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
