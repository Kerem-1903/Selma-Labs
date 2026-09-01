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
    openai_api_key: str = ""
    ollama_api_url: str = "http://localhost:11434/api/generate"
    ollama_script_model: str = "llama3"

    selmagpt_api_url: str = "http://localhost:11434/v1/chat/completions"
    selmagpt_model_name: str = "llama3.1:8b"

    # Check https://docs.claude.com for the current recommended model string
    # before running — model identifiers change over time.
    script_model: str = "claude-sonnet-4-5"
    script_provider: Literal["claude", "nvidia", "ollama", "selmagpt", "swarm"] = "swarm"
    nvidia_api_key: str = ""
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    nvidia_text_model: str = "meta/llama-3.3-70b-instruct"
    nvidia_vision_model: str = "nvidia/llama-3.1-nemotron-nano-vl-8b-v1"
    nvidia_timeout_seconds: float = 180.0
    default_target_duration_seconds: int = 45

    fact_source_provider: Literal["wikipedia"] = "wikipedia"
    fact_check_provider: Literal["nvidia", "selmagpt"] = "selmagpt"
    nvidia_fact_check_model: str = "meta/llama-3.1-8b-instruct"
    nvidia_fact_check_audit_model: str = "nvidia/llama-3.1-nemotron-nano-8b-v1"
    fact_check_fallback_provider: Literal["openai", "none"] = "openai"
    openai_fact_check_model: str = "gpt-5.6-sol"
    fact_check_primary_timeout_seconds: float = 180.0
    fact_check_primary_max_retries: int = 0
    fact_check_source_language: str = "en"
    fact_check_fallback_languages: str = "tr"
    fact_check_source_limit: int = 5
    fact_check_max_extract_chars: int = 5000
    fact_check_rewrite_attempts: int = 2

    youtube_data_api_key: str = ""
    trend_source_provider: Literal["youtube"] = "youtube"
    topic_selection_provider: Literal["nvidia"] = "nvidia"
    trend_region_code: str = "US"
    trend_category_ids: str = "15,27,28"
    trend_max_results_per_category: int = 20
    trend_candidate_limit: int = 20
    trend_min_duration_seconds: int = 10
    trend_max_duration_seconds: int = 180
    trend_search_query: str = "science facts|animal facts|nature facts"
    trend_relevance_language: str = "en"
    trend_published_within_days: int = 30

    # Voice generation (Sprint 2). voice_provider is the single switch that
    # selects an adapter via config/provider_registry.py — add new literal
    # values here as new adapters are implemented.
    voice_provider: Literal["elevenlabs", "local_xtts"] = "elevenlabs"
    local_voice_reference_path: str = "output/user_uploads/voice_reference.wav"
    elevenlabs_api_key: str = ""
    elevenlabs_model_id: str = "eleven_multilingual_v2"
    elevenlabs_stability: float = 0.35
    elevenlabs_similarity_boost: float = 0.8
    elevenlabs_style: float = 0.45
    elevenlabs_speed: float = 1.05
    elevenlabs_use_speaker_boost: bool = True
    # "George" — the API quickstart voice and usable on the free API tier.
    # Override via ELEVENLABS_VOICE_ID or the CLI's --voice-id flag.
    elevenlabs_voice_id: str = "JBFqnCBsd6RMkjVDRZzb"
    brand_signature_enabled: bool = True
    brand_signature_text: str = "Welcome to Strange Things."
    pronunciation_lexicon_path: str = "assets/audio/pronunciation_lexicon.json"

    storage_root_dir: str = "output"
    audio_license_manifest_path: str = "input_audio/license_manifest.json"
    require_audio_license_manifest: bool = True

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
    video_generation_provider: str = "none" # options: "none", "luma", "comfyui"
    luma_api_key: str = ""
    comfyui_api_url: str = "http://127.0.0.1:8188"
    comfyui_workflow_path: str = "assets/comfyui_workflow.json"
    keyframe_generation_provider: Literal["fake", "comfyui"] = "fake"
    comfyui_keyframe_workflow_path: str = "assets/comfyui_keyframe_workflow.json"
    comfyui_keyframe_checkpoint: str = "sd_xl_base_1.0.safetensors"
    comfyui_character_lora_name: str = ""
    comfyui_character_lora_trigger_token: str = ""
    comfyui_character_lora_strength_model: float = 0.8
    comfyui_character_lora_strength_clip: float = 0.8
    comfyui_keyframe_timeout_seconds: float = 300.0
    comfyui_keyframe_poll_interval_seconds: float = 1.0
    keyframe_candidate_db_path: str = "data/keyframe_candidates.db"
    image_to_video_provider: Literal["fake", "comfyui"] = "fake"
    comfyui_i2v_workflow_path: str = "assets/comfyui_i2v_workflow.json"
    comfyui_i2v_timeout_seconds: float = 900.0
    comfyui_i2v_poll_interval_seconds: float = 2.0
    two_pass_motion_workflow_path: str = "assets/comfyui_i2v_workflow.json"
    two_pass_motion_cache_prefix: str = "motion/two-pass"
    two_pass_motion_timeout_seconds: float = 900.0
    two_pass_motion_width: int = 512
    two_pass_motion_height: int = 512
    two_pass_motion_fps: int = 8
    two_pass_motion_seed: int = 1903
    two_pass_motion_sampler: str = "euler"
    two_pass_motion_sampling_steps: int = 16
    two_pass_motion_guidance_scale: float = 4.5
    two_pass_motion_pass1_denoise: float = 0.12
    two_pass_motion_pass2_denoise: float = 0.06
    liveportrait_mode: Literal["mock"] = "mock"
    animation_compositor_timeout_seconds: float = 300.0
    comfyui_mode: str = "t2v"
    i2v_image_path: str = ""
    vision_safety_gate_enabled: bool = False
    vision_relevance_threshold: float = 0.70
    youtube_upload_enabled: bool = False
    youtube_upload_privacy: str = "unlisted"
    apply_cinematic_mastering: bool = False
    video_provider: Literal["pexels", "user_uploads"] = "pexels"
    pexels_api_key: str = ""
    default_video_max_results: int = 10

    # AI Vision candidate scoring. Disabled by default so a normal live run
    # cannot unexpectedly multiply API usage; enable explicitly via config or
    # the pipeline CLI once credentials and a budget are in place.
    vision_enabled: bool = False
    vision_provider: Literal["anthropic", "nvidia", "openai", "selmagpt"] = "selmagpt"
    vision_fallback_provider: Literal["nvidia", "openai", "none"] = "nvidia"
    vision_model: str = "claude-haiku-4-5"
    openai_vision_model: str = "gpt-5.6-luna"
    selmagpt_vision_model: str = "llava"
    selmagpt_vision_url: str = "http://localhost:11434/api/generate"
    vision_frames_per_asset: int = 3
    vision_top_candidates: int = 5
    vision_max_concurrency: int = 2
    vision_weight: float = 0.65

    # Scene planning (Sprint 4). Reuses anthropic_api_key above -- same
    # Anthropic account, a separate model setting because scene planning's
    # prompt/output shape is different enough from script generation that
    # tuning one shouldn't be forced to also affect the other.
    scene_planning_provider: Literal["claude", "nvidia", "selmagpt"] = "selmagpt"
    scene_planner_model: str = "claude-sonnet-4-5"
    scene_min_visual_beats: int = 3

    subtitle_style: str = "hormozi"
    subtitle_max_chars_per_line: int = 24
    subtitle_max_lines_per_cue: int = 1
    subtitle_min_cue_seconds: float = 0.8

    background_music_provider: Literal["local"] = "local"
    background_music_dir: str = "assets/music"
    background_music_enabled: bool = True
    background_music_volume: float = 0.16
    procedural_audio_accents_enabled: bool = True
    audio_mix_provider: Literal["ffmpeg"] = "ffmpeg"

    # Subtitle translation provider switch.
    translation_provider: Literal["claude", "nvidia", "selmagpt"] = "selmagpt"

    # Video rendering (Sprint 7). render_provider is the single switch that
    # selects an adapter via config/provider_registry.py, same pattern as
    # voice_provider/video_provider/scene_planning_provider above. Remotion
    # owns creative motion composition; FFmpeg remains the final mastering
    # encoder and the compatible fallback.
    render_provider: Literal["ffmpeg", "remotion"] = "remotion"
    ffmpeg_binary_path: str = "ffmpeg"
    ffprobe_binary_path: str = "ffprobe"
    blender_bin_path: str = ""
    remotion_project_dir: str = "motion"
    remotion_cli_path: str = ""
    remotion_subprocess_timeout_seconds: float = 900.0
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
    asset_perceptual_distance_threshold: int = 7
    asset_maximum_source_uses: int = 2
    asset_maximum_pose_uses: int = 2
    asset_maximum_camera_angle_uses: int = 2
    asset_maximum_background_uses: int = 3
    editorial_alignment_tolerance_ms: int = 120
    editorial_maximum_low_motion_ms: int = 2400
    editorial_maximum_visual_beat_ms: int = 2800
    caption_safe_margin_left: int = 120
    caption_safe_margin_right: int = 120
    caption_baseline_y: int = 1420
    caption_font_size: int = 68
    caption_outline_width: int = 6
    caption_active_scale_percent: int = 106
    caption_maximum_words_per_cue: int = 4
    caption_maximum_cue_duration_ms: int = 2200
    caption_minimum_scaled_emphasis_ms: int = 160

    # Search cache (Sprint 16)
    search_cache_enabled: bool = True
    search_cache_ttl_seconds: int = 300
    search_cache_negative_ttl_seconds: int = 60
    search_cache_max_entries: int = 1000
    youtube_performance_store: str = "data/youtube_performance.json"

    # Provider resilience (Sprint 17)
    provider_timeout_seconds: float = 15.0
    provider_max_retries: int = 2
    provider_retry_backoff: float = 0.5
    provider_max_backoff: float = 30.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
