"""Boundary for provider-backed word-level audio alignment."""
from __future__ import annotations

from abc import ABC, abstractmethod

from core.domain.entities.audio_asset import AudioAsset
from core.domain.value_objects.selected_highlight import SelectedHighlight
from core.domain.value_objects.word_timing import WordTiming


class WordAlignmentPort(ABC):
    """Aligns spoken or sung words to the original audio timeline."""

    @abstractmethod
    async def align(
        self,
        audio_asset: AudioAsset,
        highlight: SelectedHighlight,
        *,
        language: str | None = None,
        transcript: str | None = None,
    ) -> list[WordTiming]:
        """Return word timings for ``highlight`` in asset-relative milliseconds.

        ``transcript`` is optional because some adapters perform transcription
        and alignment together, while forced-alignment adapters receive a
        trusted lyric transcript from the application layer.
        """
        raise NotImplementedError
