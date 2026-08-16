"""Compatibility tests for the single run_factory composition root."""
from __future__ import annotations

import subprocess
import sys

from scripts.run_factory import build_arg_parser as factory_arg_parser
from scripts.run_factory import main as factory_main
from scripts.run_pipeline import build_arg_parser
from scripts.run_pipeline import main


def test_compatibility_alias_exports_the_factory_entry_points():
    assert build_arg_parser is factory_arg_parser
    assert main is factory_main


def test_compatibility_alias_accepts_the_unified_topic_mode():
    arguments = build_arg_parser().parse_args(
        ["--topic", "Why do octopuses have three hearts?", "--language", "tr"]
    )

    assert arguments.topic == "Why do octopuses have three hearts?"
    assert arguments.language == "tr"


def test_factory_accepts_licensed_music_controls():
    arguments = build_arg_parser().parse_args(
        [
            "--topic",
            "Ocean mystery",
            "--music-theme",
            "mystery",
            "--music-track",
            "deep-ocean",
        ]
    )

    assert arguments.music_theme == "mystery"
    assert arguments.music_track == "deep-ocean"
    assert arguments.no_background_music is False


def test_compatibility_cli_help_describes_the_single_factory():
    result = subprocess.run(
        [sys.executable, "scripts/run_pipeline.py", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "--topic" in result.stdout
    assert "--audio-path" in result.stdout
