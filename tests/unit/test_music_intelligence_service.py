from __future__ import annotations

import pytest

from core.application.services.music_intelligence_service import MusicIntelligenceService
from core.domain.entities.audio_asset import AudioAsset
from core.domain.exceptions import HighlightSelectionError, LowConfidenceHighlightError
from core.domain.ports.audio_source_port import AudioSourcePort
from core.domain.ports.highlight_selector_port import HighlightSelectorPort
from core.domain.value_objects.selected_highlight import SelectedHighlight


def _asset() -> AudioAsset:
    return AudioAsset.create(
        source_provider="fake",
        source_asset_id="song-1",
        local_path="C:/fake/song.mp3",
        duration_ms=30_000,
        media_type="audio/mpeg",
        license="Test license",
        usage_rights="youtube_shorts_commercial",
    )


class FakeAudioSource(AudioSourcePort):
    def __init__(self, asset: AudioAsset) -> None:
        self.asset = asset
        self.source_uri: str | None = None

    async def acquire(self, source_reference: str) -> AudioAsset:
        self.source_uri = source_reference
        return self.asset


class FakeHighlightSelector(HighlightSelectorPort):
    def __init__(self, highlight: SelectedHighlight) -> None:
        self.highlight = highlight
        self.target_duration_ms: int | None = None

    async def select(
        self, audio_asset: AudioAsset, *, target_duration_ms: int
    ) -> SelectedHighlight:
        self.target_duration_ms = target_duration_ms
        return self.highlight


def _highlight(asset: AudioAsset, *, score: float = 0.8, duration_ms: int = 20_000) -> SelectedHighlight:
    return SelectedHighlight(
        audio_asset_id=asset.id,
        start_ms=2_000,
        end_ms=2_000 + duration_ms,
        score=score,
        selector_used="fake",
        hook_type="chorus",
        rationale="Test highlight.",
    )


@pytest.mark.asyncio
async def test_process_music_hook_acquires_source_and_selects_target_duration():
    asset = _asset()
    source = FakeAudioSource(asset)
    selector = FakeHighlightSelector(_highlight(asset))
    service = MusicIntelligenceService(source, selector)

    highlight = await service.process_music_hook("C:/music/song.mp3", 20_000)

    assert highlight.audio_asset_id == asset.id
    assert source.source_uri == "C:/music/song.mp3"
    assert selector.target_duration_ms == 20_000


@pytest.mark.asyncio
async def test_process_music_hook_blocks_low_confidence_highlight():
    asset = _asset()
    service = MusicIntelligenceService(
        FakeAudioSource(asset),
        FakeHighlightSelector(_highlight(asset, score=0.29)),
    )

    with pytest.raises(LowConfidenceHighlightError, match="below the required threshold"):
        await service.process_music_hook("C:/music/song.mp3", 20_000)


@pytest.mark.asyncio
async def test_process_music_hook_blocks_duration_outside_policy_tolerance():
    asset = _asset()
    service = MusicIntelligenceService(
        FakeAudioSource(asset),
        FakeHighlightSelector(_highlight(asset, duration_ms=19_000)),
        duration_tolerance_ms=250,
    )

    with pytest.raises(HighlightSelectionError, match="deviates beyond"):
        await service.process_music_hook("C:/music/song.mp3", 20_000)
