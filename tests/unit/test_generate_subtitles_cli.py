"""
CLI argument-parsing tests for scripts/generate_subtitles.py.

Same no-network principle as every other test in this codebase: this
tests only ``build_arg_parser()`` -- argparse configuration -- never
``main()``, which wires real Claude/ElevenLabs providers and would need
live API keys. This is the Sprint 8 composition root's own equivalent of
a unit test: it proves the CLI surface (flags, defaults, required
positional argument) behaves as documented, without touching a network.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent.parent / "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import generate_subtitles  # noqa: E402


def test_topic_is_required():
    parser = generate_subtitles.build_arg_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])


def test_topic_alone_uses_defaults():
    parser = generate_subtitles.build_arg_parser()
    args = parser.parse_args(["Titanic"])

    assert args.topic == "Titanic"
    assert args.rendered_video_id is None
    assert args.max_chars_per_line is None
    assert args.max_lines_per_cue is None
    assert args.min_cue_seconds is None
    assert args.json is False


def test_rendered_video_id_flag_is_captured():
    parser = generate_subtitles.build_arg_parser()
    args = parser.parse_args(["Titanic", "--rendered-video-id", "video-123"])
    assert args.rendered_video_id == "video-123"


def test_tuning_flags_are_captured():
    parser = generate_subtitles.build_arg_parser()
    args = parser.parse_args([
        "Titanic",
        "--max-chars-per-line", "30",
        "--max-lines-per-cue", "1",
        "--min-cue-seconds", "2.0",
    ])
    assert args.max_chars_per_line == 30
    assert args.max_lines_per_cue == 1
    assert args.min_cue_seconds == 2.0


def test_json_flag_defaults_false_and_can_be_set():
    parser = generate_subtitles.build_arg_parser()
    assert parser.parse_args(["Titanic"]).json is False
    assert parser.parse_args(["Titanic", "--json"]).json is True
