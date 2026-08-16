from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from core.domain.entities.audio_asset import AudioAsset
from core.domain.exceptions import HighlightSelectionError
from infrastructure.providers.audio import librosa_highlight_selector as selector_module
from infrastructure.providers.audio.librosa_highlight_selector import LibrosaHighlightSelector


def _audio_asset() -> AudioAsset:
    return AudioAsset.create(
        source_provider="local",
        source_asset_id="song-1",
        local_path="C:/media/song.mp3",
        duration_ms=10_000,
        media_type="audio/mpeg",
        license="Commercial",
        usage_rights="youtube_shorts_commercial",
    )


@pytest.mark.asyncio
async def test_selector_uses_worker_thread_and_picks_highest_energy_window(monkeypatch):
    calls: list[str] = []

    class FakeFeature:
        @staticmethod
        def rms(*, y, hop_length):
            calls.append("rms")
            return [[0.1, 0.1, 0.9, 1.0, 0.9, 0.1, 0.1, 0.1]]

    class FakeOnset:
        @staticmethod
        def onset_strength(*, y, sr, hop_length):
            calls.append("onset")
            return [0.0, 0.0, 0.8, 1.0, 0.8, 0.0, 0.0, 0.0]

    fake_librosa = SimpleNamespace(
        load=lambda path, sr, mono: ([0.1] * 8_000, 1_000),
        feature=FakeFeature(),
        onset=FakeOnset(),
    )
    monkeypatch.setattr(selector_module, "librosa", fake_librosa)

    original_to_thread = asyncio.to_thread

    async def observing_to_thread(function, *args, **kwargs):
        calls.append("to_thread")
        return await original_to_thread(function, *args, **kwargs)

    monkeypatch.setattr(selector_module.asyncio, "to_thread", observing_to_thread)

    highlight = await LibrosaHighlightSelector().select(
        _audio_asset(), target_duration_ms=2_000
    )

    assert calls[0] == "to_thread"
    assert calls[1:] == ["rms", "onset"]
    assert highlight.start_ms == 512
    assert highlight.duration_ms == 2_000
    assert highlight.confidence_score > 0.6
    assert highlight.selector_used == "librosa:rms-onset:v1"


@pytest.mark.asyncio
async def test_selector_rejects_target_longer_than_audio():
    with pytest.raises(HighlightSelectionError, match="cannot exceed"):
        await LibrosaHighlightSelector().select(_audio_asset(), target_duration_ms=10_001)


@pytest.mark.asyncio
async def test_selector_wraps_librosa_decode_errors(monkeypatch):
    class BrokenLibrosa:
        @staticmethod
        def load(path, sr, mono):
            raise RuntimeError("decoder failed")

    monkeypatch.setattr(selector_module, "librosa", BrokenLibrosa())

    with pytest.raises(HighlightSelectionError, match="decoder failed"):
        await LibrosaHighlightSelector().select(_audio_asset(), target_duration_ms=2_000)
