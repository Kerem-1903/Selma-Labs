from __future__ import annotations

import pytest

from core.application.services.cue_partitioning_service import CuePartitioningService
from core.domain.exceptions import CuePartitioningError
from core.domain.value_objects.word_timing import WordTiming


def _words(values: list[tuple[str, int, int]]) -> list[WordTiming]:
    return [WordTiming(text, start_ms, end_ms) for text, start_ms, end_ms in values]


def test_partition_limits_each_cue_to_five_words():
    words = _words(
        [(f"word{index}", index * 250, index * 250 + 150) for index in range(6)]
    )

    cues = CuePartitioningService().partition(words)

    assert [cue.word_count for cue in cues] == [4, 2]
    assert [cue.text for cue in cues] == [
        "word0 word1 word2 word3",
        "word4 word5",
    ]


def test_partition_starts_new_cue_after_punctuation():
    words = _words(
        [
            ("This", 0, 300),
            ("is", 350, 550),
            ("it!", 600, 900),
            ("Next", 1_000, 1_300),
        ]
    )

    cues = CuePartitioningService().partition(words)

    assert [cue.text for cue in cues] == ["This is it!", "Next"]


def test_partition_rejects_a_trailing_singleton_when_timing_prevents_rebalancing():
    words = _words(
        [
            ("One", 0, 500),
            ("two", 1_400, 1_900),
            ("three", 2_400, 2_700),
        ]
    )

    with pytest.raises(CuePartitioningError, match="at least 2 words"):
        CuePartitioningService().partition(words)


def test_partition_cue_derives_text_start_end_and_word_count_from_words():
    words = _words([("Hello", 1_250, 1_500), ("world", 1_600, 2_100)])

    cue = CuePartitioningService().partition(words)[0]

    assert cue.start_ms == 1_250
    assert cue.end_ms == 2_100
    assert cue.start_time == 1.25
    assert cue.end_time == 2.1
    assert cue.word_count == 2


def test_partition_rejects_one_word_that_exceeds_maximum_cue_duration():
    words = _words([("drawn-out", 0, 2_501)])

    with pytest.raises(CuePartitioningError, match="exceeds"):
        CuePartitioningService().partition(words)


def test_partition_keeps_single_punctuation_word_until_it_has_context():
    words = _words(
        [
            ("Wait!", 0, 300),
            ("Three", 400, 700),
            ("hearts", 750, 1_050),
        ]
    )

    cues = CuePartitioningService().partition(words)

    assert [cue.text for cue in cues] == ["Wait!", "Three hearts"]


def test_partition_prefers_comma_and_conjunction_boundaries():
    words = _words(
        [
            ("İki", 0, 200),
            ("kalp,", 210, 500),
            ("ama", 510, 700),
            ("üçüncüsü", 710, 1_050),
            ("vücudu", 1_060, 1_350),
            ("besler.", 1_360, 1_700),
        ]
    )

    cues = CuePartitioningService().partition(words)

    assert [cue.text for cue in cues] == [
        "İki kalp,",
        "ama üçüncüsü vücudu besler.",
    ]


def test_partition_uses_styled_width_validator_before_word_limit():
    words = _words(
        [
            ("Ahtapotların", 0, 300),
            ("olağanüstü", 310, 600),
            ("dolaşımı", 610, 900),
            ("çalışır.", 910, 1_200),
        ]
    )
    service = CuePartitioningService(
        line_width_validator=lambda values: len(values) <= 2
    )

    cues = service.partition(words)

    assert [cue.word_count for cue in cues] == [2, 2]


def test_safe_width_can_override_two_word_density_preference():
    words = _words(
        [("olağanüstü", 0, 400), ("ahtapotların", 410, 850)]
    )
    service = CuePartitioningService(
        line_width_validator=lambda values: len(values) <= 1
    )

    cues = service.partition(words)

    assert [cue.text for cue in cues] == ["olağanüstü", "ahtapotların"]
