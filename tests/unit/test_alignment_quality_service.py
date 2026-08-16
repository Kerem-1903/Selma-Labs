from __future__ import annotations

import pytest

from core.application.services.alignment_quality_service import AlignmentQualityService
from core.domain.exceptions import AlignmentQualityError
from core.domain.value_objects.selected_highlight import SelectedHighlight
from core.domain.value_objects.word_timing import WordTiming


def _highlight() -> SelectedHighlight:
    return SelectedHighlight(
        audio_asset_id="audio-1",
        start_ms=0,
        end_ms=15_000,
        score=0.9,
        selector_used="fake",
        hook_type="chorus",
        rationale="Test hook.",
    )


def test_validate_accepts_covered_alignment_without_long_silence():
    timings = [
        WordTiming("One", 0, 1_100),
        WordTiming("two", 3_000, 4_100),
        WordTiming("three", 7_000, 8_100),
        WordTiming("four", 11_000, 12_100),
    ]

    AlignmentQualityService().validate(timings, _highlight())


def test_validate_rejects_silence_gap_longer_than_five_seconds():
    timings = [WordTiming("One", 0, 500), WordTiming("two", 6_000, 7_000)]

    with pytest.raises(AlignmentQualityError, match="silence gap"):
        AlignmentQualityService().validate(timings, _highlight())


def test_validate_rejects_insufficient_word_coverage():
    timings = [WordTiming("One", 0, 1_000)]

    with pytest.raises(AlignmentQualityError, match="coverage"):
        AlignmentQualityService(maximum_silence_gap_ms=20_000).validate(
            timings,
            _highlight(),
        )


def test_validate_rejects_word_outside_highlight_bounds():
    timings = [WordTiming("Outside", 14_500, 15_500)]

    with pytest.raises(AlignmentQualityError, match="outside"):
        AlignmentQualityService(maximum_silence_gap_ms=20_000).validate(
            timings,
            _highlight(),
        )
