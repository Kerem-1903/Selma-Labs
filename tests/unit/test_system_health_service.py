from __future__ import annotations

import subprocess
import sys

from config.settings import Settings
from core.application.services.system_health_service import SystemHealthService


def _settings(tmp_path, **overrides) -> Settings:
    values = {
        "script_provider": "nvidia",
        "scene_planning_provider": "nvidia",
        "translation_provider": "nvidia",
        "fact_check_provider": "nvidia",
        "fact_check_fallback_provider": "none",
        "voice_provider": "elevenlabs",
        "video_provider": "pexels",
        "render_provider": "ffmpeg",
        "vision_enabled": True,
        "vision_provider": "openai",
        "nvidia_api_key": "configured",
        "openai_api_key": "configured",
        "elevenlabs_api_key": "configured",
        "pexels_api_key": "configured",
        "storage_root_dir": str(tmp_path / "output"),
        "voice_cache_dir": str(tmp_path / "cache"),
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _service(settings, tmp_path):
    return SystemHealthService(
        settings,
        project_root=tmp_path,
        executable_lookup=lambda _: sys.executable,
        command_runner=lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args[0], returncode=0, stdout="tool version", stderr=""
        ),
        minimum_free_disk_gb=0.0001,
    )


def test_factory_health_passes_with_required_tools_credentials_and_storage(tmp_path):
    report = _service(_settings(tmp_path), tmp_path).evaluate(
        profile="factory",
        run_directory=tmp_path / "runs",
    )

    assert report.ready is True
    assert report.failures == ()
    assert {check.name for check in report.checks} >= {
        "ffmpeg",
        "ffprobe",
        "nvidia_api_key",
        "elevenlabs_api_key",
        "pexels_api_key",
        "free_disk_space",
    }


def test_missing_required_voice_credential_fails_without_exposing_values(tmp_path):
    report = _service(
        _settings(tmp_path, elevenlabs_api_key=""),
        tmp_path,
    ).evaluate(run_directory=tmp_path / "runs")

    failure = next(check for check in report.failures if check.name == "elevenlabs_api_key")
    assert report.ready is False
    assert "configured" not in failure.details
    assert "ELEVENLABS_API_KEY" in (failure.remediation or "")


def test_trend_profile_requires_youtube_key_but_factory_profile_does_not(tmp_path):
    settings = _settings(tmp_path, youtube_data_api_key="")
    service = _service(settings, tmp_path)

    assert service.evaluate(profile="factory", run_directory=tmp_path / "runs-a").ready is True
    trend = service.evaluate(profile="trends", run_directory=tmp_path / "runs-b")
    assert trend.ready is False
    assert "youtube_data_api_key" in {check.name for check in trend.failures}


def test_invalid_portrait_configuration_fails_before_render(tmp_path):
    report = _service(
        _settings(tmp_path, render_output_width=1920, render_output_height=1080),
        tmp_path,
    ).evaluate(run_directory=tmp_path / "runs")

    assert report.ready is False
    assert "portrait_render_profile" in {check.name for check in report.failures}


def test_disabled_vision_gate_fails_before_any_paid_factory_stage(tmp_path):
    report = _service(
        _settings(tmp_path, vision_enabled=False),
        tmp_path,
    ).evaluate(run_directory=tmp_path / "runs")

    assert report.ready is False
    assert "vision_quality_gate_enabled" in {
        check.name for check in report.failures
    }


def test_audio_profile_does_not_require_text_or_voice_credentials(tmp_path):
    settings = _settings(
        tmp_path,
        nvidia_api_key="",
        elevenlabs_api_key="",
        vision_provider="openai",
        openai_api_key="configured",
    )

    report = _service(settings, tmp_path).evaluate(
        profile="audio",
        run_directory=tmp_path / "runs",
    )

    assert report.ready is True
    names = {check.name for check in report.checks}
    assert "nvidia_api_key" not in names
    assert "elevenlabs_api_key" not in names


def test_health_checks_the_cli_output_directory_instead_of_the_default(tmp_path):
    settings = _settings(tmp_path)
    custom_output = tmp_path / "custom-output"

    report = _service(settings, tmp_path).evaluate(
        run_directory=tmp_path / "runs",
        output_directory=custom_output,
    )

    output_check = next(
        check for check in report.checks if check.name == "output_directory"
    )
    assert report.ready is True
    assert str(custom_output.resolve()) in output_check.details


def test_remotion_health_uses_the_configured_cli_path(tmp_path):
    motion_dir = tmp_path / "motion"
    motion_dir.mkdir()
    (motion_dir / "package.json").write_text("{}", encoding="utf-8")
    custom_cli = tmp_path / "tools" / "remotion.cmd"
    custom_cli.parent.mkdir()
    custom_cli.write_text("", encoding="utf-8")
    settings = _settings(
        tmp_path,
        render_provider="remotion",
        remotion_project_dir=str(motion_dir),
        remotion_cli_path=str(custom_cli),
    )

    report = _service(settings, tmp_path).evaluate(
        run_directory=tmp_path / "runs"
    )

    remotion = next(
        check for check in report.checks if check.name == "remotion_project"
    )
    assert remotion.status == "PASS"
    assert str(custom_cli.resolve()) in remotion.details
