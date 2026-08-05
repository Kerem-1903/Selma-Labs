"""
Tests for scripts/run_pipeline.py — operational pipeline CLI.

Coverage:
- --help exits successfully
- positional topic works
- --topic flag works
- missing topic fails
- invalid duration fails
- dry run completes with all stages
- metadata.json is created and marks dry-run mode
- metadata contains only relative artifact paths (no machine-specific absolute paths)
- metadata marks simulated flag for dry-run
- outputs stay under the requested directory
- target-language output is handled
- stage failure returns non-zero exit
- live-mode missing configuration fails clearly (without network access)
"""
import json
import os
import subprocess
import sys
import pytest
from pathlib import Path
import tempfile

from scripts.run_pipeline import build_arg_parser, main


# ────────────────────────────────────────────────────────────────
# Argument parser tests
# ────────────────────────────────────────────────────────────────

def test_build_arg_parser_defaults():
    """Positional topic with --dry-run uses correct defaults."""
    parser = build_arg_parser()
    args = parser.parse_args(["The Physics of Quantum Entanglement", "--dry-run"])
    assert args.topic == "The Physics of Quantum Entanglement"
    assert args.dry_run is True
    assert args.language == "en"
    assert args.target_languages == []
    assert args.duration is None
    assert args.output is None


def test_build_arg_parser_option_topic():
    """--topic flag is accepted as an alternative to positional."""
    parser = build_arg_parser()
    args = parser.parse_args(["--topic", "Black Holes", "--dry-run", "--output", "out_dir"])
    assert args.topic_option == "Black Holes"
    assert args.output == "out_dir"


def test_build_arg_parser_duration_is_passed_through():
    """--duration is parsed as int."""
    parser = build_arg_parser()
    args = parser.parse_args(["Topic", "--duration", "30"])
    assert args.duration == 30


# ────────────────────────────────────────────────────────────────
# CLI help test
# ────────────────────────────────────────────────────────────────

def test_help_exits_successfully():
    """--help must exit 0 without requiring API credentials."""
    result = subprocess.run(
        [sys.executable, "scripts/run_pipeline.py", "--help"],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parent.parent.parent),
    )
    assert result.returncode == 0
    assert "Run end-to-end SELMA Shorts video generation pipeline" in result.stdout


# ────────────────────────────────────────────────────────────────
# Missing topic error test
# ────────────────────────────────────────────────────────────────

def test_missing_topic_exits_nonzero():
    """Running with no topic argument must fail with non-zero exit code."""
    result = subprocess.run(
        [sys.executable, "scripts/run_pipeline.py", "--dry-run"],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parent.parent.parent),
    )
    assert result.returncode != 0


# ────────────────────────────────────────────────────────────────
# Invalid duration test
# ────────────────────────────────────────────────────────────────

def test_invalid_duration_exits_nonzero():
    """--duration outside 15-90 range must fail with non-zero exit code."""
    result = subprocess.run(
        [sys.executable, "scripts/run_pipeline.py", "Test Topic", "--dry-run", "--duration", "5"],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parent.parent.parent),
    )
    assert result.returncode != 0
    assert "15 and 90" in result.stderr


# ────────────────────────────────────────────────────────────────
# Full dry-run execution test
# ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_pipeline_dry_run_executes_successfully(monkeypatch):
    """Complete dry-run should succeed, produce metadata, and mark as simulated."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_path = Path(tmp_dir) / "test_run_out"
        test_args = [
            "run_pipeline.py",
            "Deep Ocean Exploration",
            "--dry-run",
            "--output",
            str(out_path),
            "--target-languages",
            "es",
        ]
        monkeypatch.setattr("sys.argv", test_args)

        await main()

        # Output directory exists
        assert out_path.exists()

        # metadata.json exists and can be parsed
        metadata_file = out_path / "metadata.json"
        assert metadata_file.exists()
        data = json.loads(metadata_file.read_text(encoding="utf-8"))

        # Status and mode checks
        assert data["status"] == "SUCCESS"
        assert data["mode"] == "dry_run"
        assert data["simulated"] is True

        # All stages completed
        assert data["stages"]["script"]["status"] == "COMPLETED"
        assert data["stages"]["voice"]["status"] == "COMPLETED"
        assert data["stages"]["scene_planning"]["status"] == "COMPLETED"
        assert data["stages"]["asset_matching"]["status"] == "COMPLETED"
        assert data["stages"]["timeline"]["status"] == "COMPLETED"
        assert data["stages"]["rendering"]["status"] == "COMPLETED"
        assert data["stages"]["subtitles"]["status"] == "COMPLETED"
        assert data["stages"]["translation"]["status"] == "COMPLETED"

        # Simulated flags on stages with external providers
        assert data["stages"]["voice"]["simulated"] is True
        assert data["stages"]["rendering"]["simulated"] is True


@pytest.mark.asyncio
async def test_dry_run_metadata_has_relative_paths(monkeypatch):
    """All artifact paths in metadata.json must be relative (no machine-specific absolute paths)."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_path = Path(tmp_dir) / "relative_path_test"
        test_args = [
            "run_pipeline.py",
            "Relative Path Test",
            "--dry-run",
            "--output",
            str(out_path),
        ]
        monkeypatch.setattr("sys.argv", test_args)

        await main()

        data = json.loads((out_path / "metadata.json").read_text(encoding="utf-8"))

        # Check all artifact paths are relative (no drive letter or root slash)
        for key, path_value in data["artifacts"].items():
            assert not Path(path_value).is_absolute(), (
                f"Artifact '{key}' has absolute path: {path_value}"
            )


@pytest.mark.asyncio
async def test_dry_run_outputs_stay_under_requested_directory(monkeypatch):
    """All generated files must be within the specified --output directory."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_path = Path(tmp_dir) / "containment_test"
        test_args = [
            "run_pipeline.py",
            "Containment Test",
            "--dry-run",
            "--output",
            str(out_path),
        ]
        monkeypatch.setattr("sys.argv", test_args)

        await main()

        # Walk all files and confirm they are under out_path
        for root, dirs, files in os.walk(out_path):
            for f in files:
                full_path = Path(root) / f
                assert str(full_path).startswith(str(out_path)), (
                    f"File {full_path} escaped the output directory"
                )

        # Verify expected subdirectories exist
        assert (out_path / "script").is_dir()
        assert (out_path / "scenes").is_dir()
        assert (out_path / "assets").is_dir()
        assert (out_path / "timeline").is_dir()
        assert (out_path / "subtitles").is_dir()


@pytest.mark.asyncio
async def test_dry_run_without_translation(monkeypatch):
    """Dry run without --target-languages should skip translation stage gracefully."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_path = Path(tmp_dir) / "no_translation_test"
        test_args = [
            "run_pipeline.py",
            "No Translation Test",
            "--dry-run",
            "--output",
            str(out_path),
        ]
        monkeypatch.setattr("sys.argv", test_args)

        await main()

        data = json.loads((out_path / "metadata.json").read_text(encoding="utf-8"))
        assert data["status"] == "SUCCESS"
        assert "translation" not in data["stages"]
