"""
CLI argument-parsing tests for scripts/render_video.py's Sprint 8
addition -- the ``--subtitle`` flag.

Same no-network principle as test_generate_subtitles_cli.py: only
``build_arg_parser()`` is exercised, never ``main()``. This is the
"render integration" coverage for Sprint 8 -- proving the render pipeline
CLI exposes the documented opt-in subtitle export flag, without needing
FFmpeg, Claude, ElevenLabs, or Pexels to actually run. RenderService,
RenderPort, Timeline, and RenderedVideo are untouched by Sprint 8 (see
render_video.py's own module docstring) and continue to be exercised only
by test_render_service.py / test_ffmpeg_render_provider.py, unmodified.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent.parent / "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import render_video  # noqa: E402


def test_topic_is_required():
    parser = render_video.build_arg_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])


def test_subtitle_flag_defaults_to_false():
    parser = render_video.build_arg_parser()
    args = parser.parse_args(["Titanic"])
    assert args.subtitle is False


def test_subtitle_flag_can_be_enabled():
    parser = render_video.build_arg_parser()
    args = parser.parse_args(["Titanic", "--subtitle"])
    assert args.subtitle is True


def test_subtitle_flag_is_independent_of_candidates_per_scene():
    parser = render_video.build_arg_parser()
    args = parser.parse_args(["Titanic", "--subtitle", "--candidates-per-scene", "5"])
    assert args.subtitle is True
    assert args.candidates_per_scene == 5


def test_candidates_per_scene_defaults_to_none():
    parser = render_video.build_arg_parser()
    args = parser.parse_args(["Titanic"])
    assert args.candidates_per_scene is None
