"""Boundary for selecting the strongest short-form excerpt from an audio asset."""
from __future__ import annotations

from abc import ABC, abstractmethod

from core.domain.entities.audio_asset import AudioAsset
from core.domain.value_objects.selected_highlight import SelectedHighlight


class HighlightSelectorPort(ABC):
    """Uses provider-specific audio intelligence behind a stable contract."""

    @abstractmethod
    async def select(
        self,
        audio_asset: AudioAsset,
        *,
        target_duration_ms: int,
    ) -> SelectedHighlight:
        """Return one scored excerpt at ``target_duration_ms``.

        The adapter may combine signal processing, lyrics, and model output,
        but it must not leak provider-specific response types to the domain.
        """
        raise NotImplementedError
