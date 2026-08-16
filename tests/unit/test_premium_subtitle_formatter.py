from __future__ import annotations

import re

import pytest

from core.application.services.premium_subtitle_formatter import PremiumSubtitleFormatter
from core.domain.exceptions import KaraokeFormattingError
from core.domain.value_objects.subtitle_cue import SubtitleCue
from core.domain.value_objects.word_timing import WordTiming
from core.domain.value_objects.visual_intent import VisualIntent


def test_format_writes_persistent_phrase_and_active_word_overlays():
    cue = SubtitleCue.from_words(
        [
            WordTiming("Hello", 1_000, 1_350),
            WordTiming("world!", 1_500, 2_100),
        ],
        index=1,
    )

    ass = PremiumSubtitleFormatter().format([cue])

    assert "PlayResY: 1920" in ass
    assert "MarginV, Encoding" in ass
    assert "Arial Black" in ass
    assert ",120,120,500,1" in ass
    assert "Dialogue: 0,0:00:01.00,0:00:02.10,KaraokeBase" in ass
    assert "Hello world!" in ass
    assert "Dialogue: 1,0:00:01.00,0:00:01.35,KaraokeActive" in ass
    assert "Dialogue: 1,0:00:01.50,0:00:02.10,KaraokeActive" in ass
    assert r"\fscy106\t(0,120,\fscy100)}Hello" in ass
    assert r"\fscx106" not in ass
    assert r"\move(540,1436,540,1420,0,140)" in ass
    assert r"\blur1.1\t(0,120,\blur0)\fad(45,70)" in ass
    assert r"{\alpha&HFF&}world!" in ass


def test_format_rejects_legacy_cue_without_word_timing():
    cue = SubtitleCue(index=1, scene_index=0, start_time=0.0, end_time=1.0, text="Legacy")

    with pytest.raises(KaraokeFormattingError, match="word-timed"):
        PremiumSubtitleFormatter().format([cue])


def test_each_word_has_one_active_overlay_and_one_shared_base_event():
    cue = SubtitleCue.from_words(
        [
            WordTiming("one", 0, 15),
            WordTiming("two", 15, 30),
            WordTiming("three", 30, 45),
        ],
        index=1,
    )

    ass = PremiumSubtitleFormatter().format([cue])

    assert ass.count("Dialogue: 0,") == 1
    assert ass.count("Dialogue: 1,") == 3
    assert len(re.findall(r"\\alpha&H00&", ass)) == 3


def test_format_rejects_more_than_four_words_in_one_cue():
    cue = SubtitleCue.from_words(
        [
            WordTiming(f"word{index}", index * 100, index * 100 + 90)
            for index in range(5)
        ]
    )

    with pytest.raises(KaraokeFormattingError, match="no more than four"):
        PremiumSubtitleFormatter().format([cue])


def test_single_short_word_uses_color_without_scale_pulse():
    cue = SubtitleCue.from_words([WordTiming("Ve", 0, 80)])

    ass = PremiumSubtitleFormatter().format([cue])

    active_event = next(
        line
        for line in ass.splitlines()
        if line.startswith("Dialogue: 1,") and "KaraokeActive" in line
    )
    assert "Ve" in active_event
    assert r"\1c&H0000D7FF&" in active_event
    assert r"\fscx106" not in active_event


def test_format_adds_and_merges_semantic_explanation_overlays():
    cue = SubtitleCue.from_words(
        [WordTiming("Üç", 0, 300), WordTiming("kalp", 310, 700)]
    )
    intents = [
        VisualIntent(
            "octopus",
            "reflective",
            "steady",
            start_ms=0,
            end_ms=1_000,
            explanatory_required=True,
            explanation_mode="hybrid",
            overlay_labels=("3 KALP",),
        ),
        VisualIntent(
            "octopus",
            "reflective",
            "steady",
            start_ms=1_000,
            end_ms=2_000,
            explanatory_required=True,
            explanation_mode="hybrid",
            overlay_labels=("3 KALP",),
        ),
    ]

    ass = PremiumSubtitleFormatter().format([cue], visual_intents=intents)

    assert "Style: VisualLabel" in ass
    assert ass.count("VisualLabel,,") == 1
    assert "Dialogue: 3,0:00:00.00,0:00:02.00,VisualLabel" in ass
    assert "Dialogue: 2,0:00:00.00,0:00:02.00,VisualAccent" in ass
    assert r"\move(540,274,540,240,0,220)" in ass
    assert "● 3" in ass
    assert "3 KALP" in ass


def test_mechanism_overlay_uses_directional_arrow_animation():
    cue = SubtitleCue.from_words(
        [WordTiming("Kan", 0, 300), WordTiming("pompalar", 310, 900)]
    )
    intent = VisualIntent(
        "octopus",
        "reflective",
        "steady",
        start_ms=0,
        end_ms=1_200,
        visual_job="demonstrate_mechanism",
        explanatory_required=True,
        explanation_mode="hybrid",
        overlay_labels=("KALP → SOLUNGAÇ",),
    )

    ass = PremiumSubtitleFormatter().format([cue], visual_intents=[intent])

    assert r"\move(455,330,625,330,120,760)" in ass
    assert "VisualAccent,,0,0,0," in ass
    assert "→" in ass
