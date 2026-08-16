from __future__ import annotations

import pytest

from core.domain.entities.audio_asset import AudioAsset
from core.domain.value_objects.selected_highlight import SelectedHighlight
from core.domain.value_objects.word_timing import WordTiming


def _audio_asset(**overrides) -> AudioAsset:
    values = {
        "source_provider": "local",
        "source_asset_id": "song-123",
        "local_path": "C:/media/song.mp3",
        "duration_ms": 185_000,
        "media_type": "audio/mpeg",
        "license": "Commercial license",
        "usage_rights": "youtube_shorts_commercial",
    }
    values.update(overrides)
    return AudioAsset.create(**values)


def test_audio_asset_requires_rights_metadata():
    with pytest.raises(ValueError, match="license and usage_rights"):
        _audio_asset(license="")


def test_audio_asset_exports_auditable_metadata():
    asset = _audio_asset(title="Night Drive", artist="SELMA")

    data = asset.to_dict()

    assert asset.id
    assert data["source_asset_id"] == "song-123"
    assert data["license"] == "Commercial license"
    assert data["usage_rights"] == "youtube_shorts_commercial"


def test_selected_highlight_calculates_duration():
    highlight = SelectedHighlight(
        audio_asset_id="audio-1",
        start_ms=42_000,
        end_ms=63_500,
        score=0.92,
        selector_used="composite:v1",
        hook_type="chorus",
        rationale="High vocal energy and repeated lyric.",
    )

    assert highlight.duration_ms == 21_500


@pytest.mark.parametrize(
    ("start_ms", "end_ms"),
    [(0, 0), (-1, 4_000), (4_000, 3_999)],
)
def test_selected_highlight_rejects_invalid_bounds(start_ms: int, end_ms: int):
    with pytest.raises(ValueError):
        SelectedHighlight(
            audio_asset_id="audio-1",
            start_ms=start_ms,
            end_ms=end_ms,
            score=0.8,
            selector_used="fake",
            hook_type="chorus",
            rationale="Test selection.",
        )


def test_word_timing_uses_milliseconds_and_optional_confidence():
    timing = WordTiming(text="Tonight", start_ms=42_015, end_ms=42_390, confidence=0.98)

    assert timing.start_ms == 42_015
    assert timing.end_ms == 42_390
    assert timing.confidence == 0.98


@pytest.mark.parametrize(
    "kwargs",
    [
        {"text": "", "start_ms": 0, "end_ms": 1},
        {"text": "word", "start_ms": -1, "end_ms": 1},
        {"text": "word", "start_ms": 10, "end_ms": 10},
        {"text": "word", "start_ms": 10, "end_ms": 20, "confidence": 1.1},
    ],
)
def test_word_timing_rejects_invalid_values(kwargs):
    with pytest.raises(ValueError):
        WordTiming(**kwargs)
