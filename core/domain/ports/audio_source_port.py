"""Boundary for acquiring licensed audio sources into the pipeline."""
from __future__ import annotations

from abc import ABC, abstractmethod

from core.domain.entities.audio_asset import AudioAsset


class AudioSourcePort(ABC):
    """Acquires a source and returns its provider-independent AudioAsset."""

    @abstractmethod
    async def acquire(self, source_reference: str) -> AudioAsset:
        """Acquire and persist a source identified by ``source_reference``.

        Adapters validate source-specific credentials and must populate the
        returned asset with auditable license and usage-rights metadata.
        """
        raise NotImplementedError
