from __future__ import annotations

from PIL import Image
import pytest

from core.application.services.caption_ux_service import CaptionUxService
from core.domain.exceptions import CaptionUxError
from core.domain.value_objects.caption_ux import CaptionSafeZoneProfile
from core.domain.value_objects.subtitle_cue import SubtitleCue
from core.domain.value_objects.word_timing import WordTiming


def _cue(index: int, words: list[tuple[str, int, int]]) -> SubtitleCue:
    return SubtitleCue.from_words(
        [WordTiming(text, start, end) for text, start, end in words],
        index=index,
    )


def test_caption_report_measures_outline_scale_and_short_word_policy():
    cues = [
        _cue(1, [("Ahtapotların", 0, 320), ("üç", 330, 440), ("kalbi", 450, 780)]),
        _cue(2, [("vardır.", 800, 1_200)]),
    ]

    report = CaptionUxService().evaluate(cues)

    assert report.passed is True
    assert report.score == 10.0
    assert report.maximum_styled_width > 0
    assert "üç" in report.short_words_without_scale
    assert {sample.kind for sample in report.preview_samples} == {
        "longest_line",
        "widest_active_word",
        "lowest_positioned_cue",
    }


def test_caption_gate_rejects_crossed_sentence_boundary():
    cue = _cue(
        4,
        [("Bitti!", 0, 300), ("Şimdi", 310, 600), ("devam", 610, 900)],
    )

    with pytest.raises(CaptionUxError, match=r"hard_boundaries=\[4\]"):
        CaptionUxService().evaluate([cue])


def test_turkish_long_line_is_measured_against_mobile_safe_width():
    cue = _cue(
        2,
        [
            ("Muvaffakiyetsizleştiricileştiriveremeyebileceklerimizdenmişsinizcesine", 0, 700),
            ("görünüyor.", 710, 1_100),
        ],
    )

    with pytest.raises(CaptionUxError, match=r"horizontal_overflow=\[2\]"):
        CaptionUxService().evaluate([cue])


def test_caption_gate_rejects_bottom_ui_overlap():
    profile = CaptionSafeZoneProfile(caption_baseline_y=1600)
    cue = _cue(1, [("Üç", 0, 300), ("kalp", 310, 700)])

    with pytest.raises(CaptionUxError, match=r"vertical_overflow=\[1\]"):
        CaptionUxService(profile).evaluate([cue])


def test_preview_variants_cover_full_tablet_and_small_phone_sizes(tmp_path):
    source = tmp_path / "caption_100.jpg"
    Image.new("RGB", (1080, 1920), "navy").save(source)

    paths = CaptionUxService.create_preview_variants(str(source))

    assert len(paths) == 3
    with Image.open(paths[1]) as medium:
        assert medium.size == (810, 1440)
    with Image.open(paths[2]) as small:
        assert small.size == (360, 640)
