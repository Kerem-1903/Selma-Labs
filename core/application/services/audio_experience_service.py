from __future__ import annotations

import os

from core.domain.ports.audio_mix_port import AudioMixPort
from core.domain.ports.background_music_port import BackgroundMusicPort
from core.domain.ports.storage_port import StoragePort
from core.domain.value_objects.background_track import BackgroundTrack
from core.domain.value_objects.storage_reference import StorageReference


class AudioExperienceService:
    def __init__(
        self,
        *,
        music_provider: BackgroundMusicPort,
        mix_provider: AudioMixPort,
        storage: StoragePort,
    ) -> None:
        self._music_provider = music_provider
        self._mix_provider = mix_provider
        self._storage = storage

    async def create_mix(
        self,
        *,
        theme: str,
        narration_path: str,
        duration_seconds: float,
        storage_key: str,
        selected_track: BackgroundTrack | None = None,
    ) -> tuple[StorageReference, BackgroundTrack]:
        track = selected_track or await self._music_provider.select(theme)
        result = await self._mix_provider.mix(
            narration_path=narration_path,
            music_path=track.file_path,
            duration_seconds=duration_seconds,
        )
        try:
            with open(result.output_path, "rb") as mixed_file:
                mixed_bytes = mixed_file.read()
            reference = await self._storage.save(
                key=storage_key,
                data=mixed_bytes,
                content_type="audio/mp4",
            )
        finally:
            try:
                os.remove(result.output_path)
            except OSError:
                pass
        return reference, track
