from __future__ import annotations

from abc import ABC, abstractmethod

from core.domain.value_objects.audio_mix_result import AudioMixResult


class AudioMixPort(ABC):
    @abstractmethod
    async def mix(
        self,
        *,
        narration_path: str,
        music_path: str,
        duration_seconds: float,
    ) -> AudioMixResult:
        raise NotImplementedError
