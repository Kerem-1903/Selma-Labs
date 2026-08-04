"""
Unit tests for VoiceService.

Same principle as Sprint 1's test_script_service.py: these never touch the
network or a real TTS API. FakeVoiceProvider and FakeStorage are minimal
in-memory implementations of VoiceGeneratorPort and StoragePort, proving
both ports are genuinely swappable and that VoiceService's business logic
is testable in isolation.
"""
from __future__ import annotations

import pytest

from core.application.services.voice_service import VoiceService
from core.domain.entities.script import Script
from core.domain.exceptions import ProviderTimeoutError, StorageError, VoiceGenerationError
from core.domain.ports.storage_port import StoragePort
from core.domain.ports.voice_generator_port import VoiceGeneratorPort
from core.domain.value_objects.generated_audio import GeneratedAudio
from core.domain.value_objects.speech_segment import SpeechSegment
from core.domain.value_objects.storage_reference import StorageReference


class FakeVoiceProvider(VoiceGeneratorPort):
    """In-memory VoiceGeneratorPort implementation for tests."""

    def __init__(
        self,
        *,
        duration_seconds: float = 10.0,
        audio_bytes: bytes = b"fake-audio",
        segments=None,
        raises=None,
    ):
        self._duration_seconds = duration_seconds
        self._audio_bytes = audio_bytes
        self._segments = segments or []
        self._raises = raises
        self.last_call: dict | None = None

    async def generate_voice(self, text: str, voice_name: str) -> GeneratedAudio:
        self.last_call = {"text": text, "voice_name": voice_name}
        if self._raises:
            raise self._raises
        return GeneratedAudio(
            audio_bytes=self._audio_bytes,
            duration_seconds=self._duration_seconds,
            sample_rate=44100,
            provider="fake-provider",
            voice_name=voice_name,
            segments=self._segments,
        )


class FakeStorage(StoragePort):
    """In-memory StoragePort implementation for tests."""

    def __init__(self, raises=None):
        self._raises = raises
        self.saved: dict | None = None

    async def save(self, key: str, data: bytes, content_type: str) -> StorageReference:
        if self._raises:
            raise self._raises
        self.saved = {"key": key, "data": data, "content_type": content_type}
        return StorageReference(key=key, path=f"/fake/{key}", size_bytes=len(data))


def _script(text: str = "This is a narration script for testing purposes.") -> Script:
    return Script.create(
        topic="Test topic",
        full_text=text,
        target_duration_seconds=45,
        provider_used="fake",
    )


@pytest.mark.asyncio
async def test_generate_returns_voice_track_with_expected_fields():
    provider = FakeVoiceProvider(duration_seconds=12.5)
    storage = FakeStorage()
    service = VoiceService(provider, storage, default_voice_name="default-voice")

    script = _script()
    voice_track = await service.generate(script)

    assert voice_track.script_id == script.id
    assert voice_track.duration_seconds == 12.5
    assert voice_track.provider == "fake-provider"
    assert voice_track.voice_name == "default-voice"
    assert voice_track.sample_rate == 44100
    assert voice_track.file_path == f"/fake/{storage.saved['key']}"
    assert voice_track.audio_id  # non-empty uuid


@pytest.mark.asyncio
async def test_uses_default_voice_name_when_none_provided():
    provider = FakeVoiceProvider()
    service = VoiceService(provider, FakeStorage(), default_voice_name="default-voice")

    await service.generate(_script())

    assert provider.last_call["voice_name"] == "default-voice"


@pytest.mark.asyncio
async def test_uses_override_voice_name_when_provided():
    provider = FakeVoiceProvider()
    service = VoiceService(provider, FakeStorage(), default_voice_name="default-voice")

    await service.generate(_script(), voice_name="custom-voice")

    assert provider.last_call["voice_name"] == "custom-voice"


@pytest.mark.asyncio
async def test_passes_script_text_verbatim_to_provider():
    provider = FakeVoiceProvider()
    service = VoiceService(provider, FakeStorage(), default_voice_name="v")

    script = _script("Exact narration text.")
    await service.generate(script)

    assert provider.last_call["text"] == "Exact narration text."


@pytest.mark.asyncio
async def test_rejects_script_with_empty_text():
    service = VoiceService(FakeVoiceProvider(), FakeStorage(), default_voice_name="v")

    empty_script = Script.create(
        topic="t", full_text="   ", target_duration_seconds=45, provider_used="fake"
    )

    with pytest.raises(VoiceGenerationError, match="no narration text"):
        await service.generate(empty_script)


@pytest.mark.asyncio
async def test_rejects_zero_duration_audio_from_provider():
    provider = FakeVoiceProvider(duration_seconds=0.0)
    service = VoiceService(provider, FakeStorage(), default_voice_name="v")

    with pytest.raises(VoiceGenerationError, match="invalid audio duration"):
        await service.generate(_script())


@pytest.mark.asyncio
async def test_rejects_empty_audio_bytes_from_provider():
    provider = FakeVoiceProvider(audio_bytes=b"")
    service = VoiceService(provider, FakeStorage(), default_voice_name="v")

    with pytest.raises(VoiceGenerationError, match="empty audio"):
        await service.generate(_script())


@pytest.mark.asyncio
async def test_propagates_provider_errors_unchanged():
    provider = FakeVoiceProvider(raises=ProviderTimeoutError("simulated timeout"))
    service = VoiceService(provider, FakeStorage(), default_voice_name="v")

    with pytest.raises(ProviderTimeoutError, match="simulated timeout"):
        await service.generate(_script())


@pytest.mark.asyncio
async def test_propagates_storage_errors_unchanged():
    provider = FakeVoiceProvider()
    storage = FakeStorage(raises=StorageError("disk full"))
    service = VoiceService(provider, storage, default_voice_name="v")

    with pytest.raises(StorageError, match="disk full"):
        await service.generate(_script())


@pytest.mark.asyncio
async def test_segments_default_to_empty_when_provider_supplies_none():
    provider = FakeVoiceProvider()
    service = VoiceService(provider, FakeStorage(), default_voice_name="v")

    voice_track = await service.generate(_script())

    assert voice_track.segments == []
    assert voice_track.to_dict()["segments"] == []


@pytest.mark.asyncio
async def test_segments_pass_through_when_provider_supplies_them():
    segments = [
        SpeechSegment(text="Titanic was the largest ship", start=0.0, end=3.4),
        SpeechSegment(text="But it sank", start=3.4, end=5.9),
    ]
    provider = FakeVoiceProvider(segments=segments)
    service = VoiceService(provider, FakeStorage(), default_voice_name="v")

    voice_track = await service.generate(_script())

    assert voice_track.segments == segments
    exported = voice_track.to_dict()
    assert exported["segments"][0] == {
        "text": "Titanic was the largest ship", "start": 0.0, "end": 3.4
    }
    assert exported["audio_file"] == voice_track.file_path
    assert exported["duration"] == voice_track.duration_seconds
