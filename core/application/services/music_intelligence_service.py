"""Application use case for acquiring audio and selecting a publishable hook."""
from __future__ import annotations

from core.domain.entities.audio_asset import AudioAsset
from core.domain.exceptions import HighlightSelectionError, LowConfidenceHighlightError
from core.domain.ports.audio_source_port import AudioSourcePort
from core.domain.ports.highlight_selector_port import HighlightSelectorPort
from core.domain.value_objects.selected_highlight import SelectedHighlight


class MusicIntelligenceService:
    """Coordinates source acquisition, selection, and deterministic policy checks."""

    def __init__(
        self,
        audio_source: AudioSourcePort,
        highlight_selector: HighlightSelectorPort,
        *,
        minimum_confidence_score: float = 0.30,
        duration_tolerance_ms: int = 250,
    ) -> None:
        if not 0.0 <= minimum_confidence_score <= 1.0:
            raise ValueError("minimum_confidence_score must be between 0.0 and 1.0.")
        if duration_tolerance_ms < 0:
            raise ValueError("duration_tolerance_ms must not be negative.")
        self._audio_source = audio_source
        self._highlight_selector = highlight_selector
        self._minimum_confidence_score = minimum_confidence_score
        self._duration_tolerance_ms = duration_tolerance_ms

    async def process_music_hook(
        self,
        source_uri: str,
        target_duration_ms: int,
    ) -> SelectedHighlight:
        """Acquire a source, select its hook, and enforce publishability policy.

        The source asset remains available to the caller's workflow through
        its acquisition stage; this use case exposes only the selected hook.
        """
        if not source_uri.strip():
            raise HighlightSelectionError("source_uri must not be empty.")
        if target_duration_ms <= 0:
            raise HighlightSelectionError("target_duration_ms must be greater than zero.")

        _, highlight = await self.process_music_hook_with_asset(
            source_uri,
            target_duration_ms,
        )
        return highlight

    async def process_music_hook_with_asset(
        self,
        source_uri: str,
        target_duration_ms: int,
    ) -> tuple[AudioAsset, SelectedHighlight]:
        """Acquire a source and hook together for durable orchestration.

        ``process_music_hook`` remains the focused compatibility API for
        callers that only need a highlight. Durable workflows additionally
        need the exact inspected asset for alignment after process recovery;
        returning both avoids a second provider acquisition.
        """
        if not source_uri.strip():
            raise HighlightSelectionError("source_uri must not be empty.")
        if target_duration_ms <= 0:
            raise HighlightSelectionError("target_duration_ms must be greater than zero.")

        audio_asset = await self._audio_source.acquire(source_uri)
        highlight = await self._highlight_selector.select(
            audio_asset,
            target_duration_ms=target_duration_ms,
        )
        self._validate_highlight(audio_asset, highlight, target_duration_ms)
        return audio_asset, highlight

    def _validate_highlight(
        self,
        audio_asset: AudioAsset,
        highlight: SelectedHighlight,
        target_duration_ms: int,
    ) -> None:
        if highlight.audio_asset_id != audio_asset.id:
            raise HighlightSelectionError(
                "Highlight belongs to a different AudioAsset than the acquired source."
            )
        if highlight.start_ms < 0 or highlight.end_ms > audio_asset.duration_ms:
            raise HighlightSelectionError("Highlight bounds fall outside the source audio.")
        if abs(highlight.duration_ms - target_duration_ms) > self._duration_tolerance_ms:
            raise HighlightSelectionError(
                "Highlight duration deviates beyond the configured tolerance."
            )
        if highlight.confidence_score < self._minimum_confidence_score:
            raise LowConfidenceHighlightError(
                f"Highlight confidence {highlight.confidence_score:.3f} is below the "
                f"required threshold {self._minimum_confidence_score:.3f}."
            )
