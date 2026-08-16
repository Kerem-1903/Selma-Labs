import json

import pytest

from core.application.services.audio_experience_service import AudioExperienceService
from core.domain.ports.audio_mix_port import AudioMixPort
from core.domain.ports.background_music_port import BackgroundMusicPort
from core.domain.ports.storage_port import StoragePort
from core.domain.value_objects.audio_mix_result import AudioMixResult
from core.domain.value_objects.background_track import BackgroundTrack
from core.domain.value_objects.storage_reference import StorageReference
from infrastructure.providers.music.local_licensed_music_provider import (
    LocalLicensedMusicProvider,
)


class FakeMusicProvider(BackgroundMusicPort):
    async def select(
        self,
        theme: str,
        track_name: str | None = None,
    ) -> BackgroundTrack:
        return BackgroundTrack("music.mp3", theme, "Creator", "Commercial", [theme])


class FakeMixProvider(AudioMixPort):
    def __init__(self, output_path: str) -> None:
        self.output_path = output_path

    async def mix(
        self,
        *,
        narration_path: str,
        music_path: str,
        duration_seconds: float,
    ) -> AudioMixResult:
        return AudioMixResult(self.output_path)


class FakeStorage(StoragePort):
    async def save(self, key: str, data: bytes, content_type: str) -> StorageReference:
        return StorageReference(key=key, path=f"C:/output/{key}", size_bytes=len(data))


@pytest.mark.asyncio
async def test_local_music_provider_requires_license_metadata(tmp_path):
    music = tmp_path / "science.mp3"
    music.write_bytes(b"music")
    (tmp_path / "license_manifest.json").write_text(
        json.dumps(
            {
                "tracks": [
                    {
                        "file": music.name,
                        "title": "Science",
                        "themes": ["science"],
                        "attribution": "Test Creator",
                        "license": "Commercial Test License",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    selected = await LocalLicensedMusicProvider(str(tmp_path)).select("science facts")

    assert selected.file_path == str(music.resolve())
    assert selected.attribution == "Test Creator"


@pytest.mark.asyncio
async def test_audio_experience_persists_mixed_audio_and_cleans_temp(tmp_path):
    mixed = tmp_path / "mixed.m4a"
    mixed.write_bytes(b"mixed audio")
    service = AudioExperienceService(
        music_provider=FakeMusicProvider(),
        mix_provider=FakeMixProvider(str(mixed)),
        storage=FakeStorage(),
    )

    reference, track = await service.create_mix(
        theme="nature",
        narration_path="voice.mp3",
        duration_seconds=20.0,
        storage_key="audio/premium.m4a",
    )

    assert reference.key == "audio/premium.m4a"
    assert track.license == "Commercial"
    assert not mixed.exists()
