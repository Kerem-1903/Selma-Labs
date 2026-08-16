from __future__ import annotations

import pytest

from scripts.run_factory import build_arg_parser
from scripts.run_factory import _require_factory_configuration


def test_factory_cli_requires_audio_path_and_uses_durable_defaults():
    arguments = build_arg_parser().parse_args(["--audio-path", "song.mp3"])

    assert arguments.audio_path == "song.mp3"
    assert arguments.run_id is None
    assert arguments.target_duration_ms == 20_000
    assert arguments.duration_seconds == 24
    assert arguments.run_directory == ".selma_runs"


def test_factory_cli_accepts_explicit_resume_run_id():
    arguments = build_arg_parser().parse_args(
        ["--audio-path", "song.mp3", "--run-id", "run-123"]
    )

    assert arguments.run_id == "run-123"


def test_factory_cli_accepts_explicit_recovery_budget():
    arguments = build_arg_parser().parse_args(
        [
            "--topic",
            "octopus hearts",
            "--run-id",
            "run-123",
            "--additional-retries",
            "2",
        ]
    )

    assert arguments.additional_retries == 2


def test_factory_cli_accepts_controlled_downstream_reprocessing():
    arguments = build_arg_parser().parse_args(
        [
            "--topic",
            "octopus hearts",
            "--run-id",
            "run-123",
            "--reprocess-from",
            "VISION_SEARCH",
        ]
    )

    assert arguments.reprocess_from == "VISION_SEARCH"


def test_factory_cli_accepts_music_and_operator_reviewed_visual_inputs():
    arguments = build_arg_parser().parse_args([
        "--topic", "Venus", "--run-id", "run-123",
        "--reprocess-from", "MUSIC_SELECTION",
        "--music-track", "space-curiosity-bed",
        "--visual-manifest", "assets/visuals/venus/license_manifest.json",
    ])

    assert arguments.reprocess_from == "MUSIC_SELECTION"
    assert arguments.music_track == "space-curiosity-bed"
    assert arguments.visual_manifest.endswith("license_manifest.json")


def test_factory_cli_accepts_explicit_configuration_change_during_reprocess():
    arguments = build_arg_parser().parse_args([
        "--topic", "Venus", "--run-id", "run-123",
        "--reprocess-from", "VISUAL_LOCALIZATION_V2",
        "--accept-configuration-change",
    ])

    assert arguments.accept_configuration_change is True


def test_factory_cli_accepts_autonomous_inbox_mode():
    arguments = build_arg_parser().parse_args(["--autonomous", "--once"])

    assert arguments.autonomous is True
    assert arguments.audio_path is None
    assert arguments.inbox_directory == "input_audio"
    assert arguments.once is True


def test_factory_cli_accepts_topic_as_the_single_unified_entry_point():
    arguments = build_arg_parser().parse_args(
        [
            "--topic",
            "Why do octopuses have three hearts?",
            "--duration-seconds",
            "32",
            "--language",
            "tr",
        ]
    )

    assert arguments.topic == "Why do octopuses have three hearts?"
    assert arguments.audio_path is None
    assert arguments.duration_seconds == 32
    assert arguments.language == "tr"


def test_factory_configuration_requires_the_selected_provider_key():
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        _require_factory_configuration("", "ANTHROPIC_API_KEY")
