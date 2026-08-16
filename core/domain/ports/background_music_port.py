from __future__ import annotations

from abc import ABC, abstractmethod

from core.domain.value_objects.background_track import BackgroundTrack


class BackgroundMusicPort(ABC):
    @abstractmethod
    async def select(
        self,
        theme: str,
        track_name: str | None = None,
    ) -> BackgroundTrack:
        raise NotImplementedError
