"""
Unit tests for SubtitleFormatter.

Pure, no I/O, no fakes needed -- format_srt/format_vtt are deterministic
static methods operating only on already-constructed SubtitleTrack data.
"""
from __future__ import annotations

from core.application.services.subtitle_formatter import SubtitleFormatter
from core.domain.entities.subtitle_track import SubtitleTrack
from core.domain.value_objects.subtitle_cue import SubtitleCue


def _cue(index: int, scene_index: int, start: float, end: float, text: str) -> SubtitleCue:
    return SubtitleCue(index=index, scene_index=scene_index, start_time=start, end_time=end, text=text)


def _track(cues) -> SubtitleTrack:
    return SubtitleTrack.create(scene_plan_id="plan-1", cues=cues)


def test_format_srt_produces_sequentially_numbered_blocks():
    track = _track([
        _cue(1, 0, 0.0, 2.5, "First cue."),
        _cue(2, 0, 2.5, 5.0, "Second cue."),
    ])

    srt = SubtitleFormatter.format_srt(track)

    assert srt.startswith("1\n")
    assert "\n2\n" in srt
    assert "First cue." in srt
    assert "Second cue." in srt


def test_format_srt_timecode_uses_comma_millisecond_separator():
    track = _track([_cue(1, 0, 0.0, 1.5, "Hi.")])

    srt = SubtitleFormatter.format_srt(track)

    assert "00:00:00,000 --> 00:00:01,500" in srt


def test_format_srt_timecode_rolls_over_minutes_and_hours():
    track = _track([_cue(1, 0, 3661.25, 3662.0, "Late cue.")])

    srt = SubtitleFormatter.format_srt(track)

    assert "01:01:01,250 --> 01:01:02,000" in srt


def test_format_srt_empty_track_returns_empty_string():
    track = _track([])
    assert SubtitleFormatter.format_srt(track) == ""


def test_format_vtt_starts_with_webvtt_header():
    track = _track([_cue(1, 0, 0.0, 1.0, "Hi.")])

    vtt = SubtitleFormatter.format_vtt(track)

    assert vtt.startswith("WEBVTT\n\n")


def test_format_vtt_timecode_uses_period_millisecond_separator():
    track = _track([_cue(1, 0, 0.0, 1.5, "Hi.")])

    vtt = SubtitleFormatter.format_vtt(track)

    assert "00:00:00.000 --> 00:00:01.500" in vtt
    # WebVTT never uses SRT's comma separator.
    assert "," not in vtt


def test_format_vtt_empty_track_still_has_header_only():
    track = _track([])
    vtt = SubtitleFormatter.format_vtt(track)
    assert vtt == "WEBVTT\n\n"


def test_format_vtt_has_no_numeric_cue_identifiers():
    track = _track([
        _cue(1, 0, 0.0, 1.0, "First."),
        _cue(2, 0, 1.0, 2.0, "Second."),
    ])

    vtt = SubtitleFormatter.format_vtt(track)
    lines = [line for line in vtt.split("\n") if line.strip()]

    # Every non-blank line is either the header, a timecode line, or cue
    # text -- never a bare integer sequence number the way SRT has.
    assert "1" not in lines
    assert "2" not in lines


def test_multiline_cue_text_preserved_in_both_formats():
    track = _track([_cue(1, 0, 0.0, 2.0, "Line one\nLine two")])

    srt = SubtitleFormatter.format_srt(track)
    vtt = SubtitleFormatter.format_vtt(track)

    assert "Line one\nLine two" in srt
    assert "Line one\nLine two" in vtt


def test_formatter_is_stateless_and_not_instantiated():
    track = _track([_cue(1, 0, 0.0, 1.0, "Hi.")])
    # Called as static methods on the class, never on an instance.
    assert SubtitleFormatter.format_srt(track) == SubtitleFormatter.format_srt(track)
