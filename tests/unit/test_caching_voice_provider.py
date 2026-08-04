"""
Unit tests for CachingVoiceProvider.

No network involved — wraps a counting FakeVoiceProvider and asserts on
call counts and returned data, using a pytest tmp_path for the cache dir.
"""
from __future__ import annotations

import json

import pytest

from core.domain.ports.voice_generator_port import VoiceGeneratorPort
from core.domain.value_objects.generated_audio import GeneratedAudio
from core.domain.value_objects.speech_segment import SpeechSegment
from infrastructure.providers.voice.caching_voice_provider import CachingVoiceProvider


class CountingVoiceProvider(VoiceGeneratorPort):
    """Fake provider that counts how many times it was actually called,
    so tests can assert the cache prevented (or didn't prevent) a call."""

    def __init__(self, segments=None):
        self.call_count = 0
        self._segments = segments or []

    async def generate_voice(self, text: str, voice_name: str) -> GeneratedAudio:
        self.call_count += 1
        return GeneratedAudio(
            audio_bytes=f"audio-for-{text}-{voice_name}".encode(),
            duration_seconds=10.0,
            sample_rate=44100,
            provider="fake-provider",
            voice_name=voice_name,
            segments=self._segments,
        )


@pytest.mark.asyncio
async def test_second_identical_call_is_served_from_cache(tmp_path):
    inner = CountingVoiceProvider()
    cache = CachingVoiceProvider(inner, cache_dir=str(tmp_path), provider_identity="fake:v1")

    first = await cache.generate_voice("Hello world", "voice-a")
    second = await cache.generate_voice("Hello world", "voice-a")

    assert inner.call_count == 1  # only called once, second was a cache hit
    assert first.audio_bytes == second.audio_bytes
    assert second.duration_seconds == 10.0


@pytest.mark.asyncio
async def test_different_text_is_a_cache_miss(tmp_path):
    inner = CountingVoiceProvider()
    cache = CachingVoiceProvider(inner, cache_dir=str(tmp_path), provider_identity="fake:v1")

    await cache.generate_voice("Hello world", "voice-a")
    await cache.generate_voice("Different text", "voice-a")

    assert inner.call_count == 2


@pytest.mark.asyncio
async def test_different_voice_name_is_a_cache_miss(tmp_path):
    inner = CountingVoiceProvider()
    cache = CachingVoiceProvider(inner, cache_dir=str(tmp_path), provider_identity="fake:v1")

    await cache.generate_voice("Hello world", "voice-a")
    await cache.generate_voice("Hello world", "voice-b")

    assert inner.call_count == 2


@pytest.mark.asyncio
async def test_different_provider_identity_is_a_cache_miss(tmp_path):
    inner_a = CountingVoiceProvider()
    inner_b = CountingVoiceProvider()
    cache_a = CachingVoiceProvider(inner_a, cache_dir=str(tmp_path), provider_identity="fake:v1")
    cache_b = CachingVoiceProvider(inner_b, cache_dir=str(tmp_path), provider_identity="fake:v2")

    await cache_a.generate_voice("Hello world", "voice-a")
    await cache_b.generate_voice("Hello world", "voice-a")

    assert inner_a.call_count == 1
    assert inner_b.call_count == 1


@pytest.mark.asyncio
async def test_cache_preserves_segments(tmp_path):
    segments = [SpeechSegment(text="Hello", start=0.0, end=1.2)]
    inner = CountingVoiceProvider(segments=segments)
    cache = CachingVoiceProvider(inner, cache_dir=str(tmp_path), provider_identity="fake:v1")

    await cache.generate_voice("Hello world", "voice-a")
    cached = await cache.generate_voice("Hello world", "voice-a")

    assert cached.segments == segments


@pytest.mark.asyncio
async def test_corrupt_cache_entry_is_treated_as_a_miss(tmp_path):
    inner = CountingVoiceProvider()
    cache = CachingVoiceProvider(inner, cache_dir=str(tmp_path), provider_identity="fake:v1")

    await cache.generate_voice("Hello world", "voice-a")
    # Corrupt the cached metadata file directly.
    key = cache._compute_key("Hello world", "voice-a")
    (tmp_path / f"{key}.json").write_text("{not valid json")

    await cache.generate_voice("Hello world", "voice-a")

    assert inner.call_count == 2  # corrupt entry forced a regeneration


@pytest.mark.asyncio
async def test_write_cache_creates_readable_json_metadata(tmp_path):
    inner = CountingVoiceProvider()
    cache = CachingVoiceProvider(inner, cache_dir=str(tmp_path), provider_identity="fake:v1")

    await cache.generate_voice("Hello world", "voice-a")

    key = cache._compute_key("Hello world", "voice-a")
    meta = json.loads((tmp_path / f"{key}.json").read_text())
    assert meta["provider"] == "fake-provider"
    assert meta["duration_seconds"] == 10.0
    assert (tmp_path / f"{key}.mp3").exists()
