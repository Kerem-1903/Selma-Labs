"""Offline production preflight for tools, credentials, storage, and settings."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

from config.settings import Settings
from core.domain.value_objects.system_health import SystemHealthCheck, SystemHealthReport


class SystemHealthService:
    def __init__(
        self,
        settings: Settings,
        *,
        project_root: str | Path,
        executable_lookup: Callable[[str], str | None] = shutil.which,
        command_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
        minimum_free_disk_gb: float = 2.0,
    ) -> None:
        if minimum_free_disk_gb <= 0:
            raise ValueError("minimum_free_disk_gb must be greater than zero.")
        self._settings = settings
        self._project_root = Path(project_root).resolve()
        self._lookup = executable_lookup
        self._run_command = command_runner
        self._minimum_free_disk_gb = minimum_free_disk_gb

    def evaluate(
        self,
        *,
        profile: str = "factory",
        run_directory: str | Path = ".selma_runs",
        output_directory: str | Path | None = None,
        local_visual_manifest: str | Path | None = None,
    ) -> SystemHealthReport:
        if profile not in {"factory", "audio", "trends"}:
            raise ValueError("Health profile must be factory, audio, or trends.")
        checks: list[SystemHealthCheck] = []
        checks.extend(self._tool_checks())
        checks.extend(self._configuration_checks(profile, bool(local_visual_manifest)))
        checks.extend(self._credential_checks(profile, bool(local_visual_manifest)))
        if local_visual_manifest:
            manifest_path = self._resolve(local_visual_manifest)
            checks.append(self._result(
                "local_visual_manifest",
                manifest_path.is_file(),
                True,
                f"Configured: {manifest_path}.",
                "Provide a readable operator-approved visual manifest.",
            ))
        checks.extend(self._storage_checks(run_directory, output_directory))
        ready = not any(
            check.required and check.status == "FAIL" for check in checks
        )
        return SystemHealthReport(profile=profile, ready=ready, checks=tuple(checks))

    def _tool_checks(self) -> list[SystemHealthCheck]:
        checks = [
            self._command_check("ffmpeg", self._settings.ffmpeg_binary_path, ["-version"]),
            self._command_check("ffprobe", self._settings.ffprobe_binary_path, ["-version"]),
        ]
        if self._settings.render_provider == "remotion":
            checks.extend([
                self._command_check("node", "node", ["--version"]),
                self._command_check("npm", "npm", ["--version"]),
            ])
            motion_dir = self._resolve(self._settings.remotion_project_dir)
            package_exists = (motion_dir / "package.json").is_file()
            configured_cli = self._settings.remotion_cli_path.strip()
            cli_candidates = (
                (self._resolve(configured_cli),)
                if configured_cli
                else (
                    motion_dir / "node_modules" / ".bin" / "remotion",
                    motion_dir / "node_modules" / ".bin" / "remotion.cmd",
                )
            )
            remotion_installed = any(path.is_file() for path in cli_candidates)
            cli_description = ", ".join(str(path) for path in cli_candidates)
            checks.append(self._result(
                "remotion_project",
                package_exists and remotion_installed,
                True,
                f"Project: {motion_dir}; CLI: {cli_description}; available: "
                f"{remotion_installed}.",
                (
                    "Correct REMOTION_CLI_PATH."
                    if configured_cli
                    else "Run npm install in the motion directory."
                ),
            ))
        return checks

    def _configuration_checks(
        self, profile: str, local_visual_manifest: bool = False
    ) -> list[SystemHealthCheck]:
        portrait = (
            self._settings.render_output_width >= 1080
            and self._settings.render_output_height >= 1920
            and self._settings.render_output_height > self._settings.render_output_width
        )
        fps_valid = 23 <= self._settings.render_fps <= 60
        captions_valid = (
            self._settings.caption_maximum_words_per_cue <= 4
            and self._settings.caption_maximum_cue_duration_ms <= 2_200
            and self._settings.caption_safe_margin_left >= 0
            and self._settings.caption_safe_margin_right >= 0
        )
        checks = [
            self._result(
                "portrait_render_profile", portrait, True,
                f"{self._settings.render_output_width}x{self._settings.render_output_height}.",
                "Use a portrait render profile of at least 1080x1920.",
            ),
            self._result(
                "render_framerate", fps_valid, True,
                f"{self._settings.render_fps} fps.",
                "Choose a frame rate between 23 and 60 fps.",
            ),
            self._result(
                "caption_policy", captions_valid, True,
                f"{self._settings.caption_maximum_words_per_cue} words; "
                f"{self._settings.caption_maximum_cue_duration_ms}ms maximum cue.",
                "Restore the mobile caption density and safe-zone limits.",
            ),
        ]
        if profile in {"factory", "audio"} and not local_visual_manifest:
            checks.append(self._result(
                "vision_quality_gate_enabled",
                self._settings.vision_enabled,
                True,
                f"VISION_ENABLED={self._settings.vision_enabled}.",
                "Set VISION_ENABLED=true only when the selected vision provider and budget are ready.",
            ))
        return checks

    def _credential_checks(
        self, profile: str, local_visual_manifest: bool = False
    ) -> list[SystemHealthCheck]:
        requirements: dict[str, tuple[str, bool, str]] = {}

        def require(name: str, value: str, reason: str, *, required: bool = True) -> None:
            previous = requirements.get(name)
            requirements[name] = (
                value,
                required or bool(previous and previous[1]),
                reason if previous is None else f"{previous[2]}; {reason}",
            )

        if profile == "factory":
            if self._settings.script_provider == "nvidia" or self._settings.scene_planning_provider == "nvidia" or self._settings.translation_provider == "nvidia":
                require("nvidia_api_key", self._settings.nvidia_api_key, "selected text/scene/translation provider")
            if self._settings.script_provider == "claude" or self._settings.scene_planning_provider == "claude" or self._settings.translation_provider == "claude":
                require("anthropic_api_key", self._settings.anthropic_api_key, "selected Claude provider")
            if self._settings.fact_check_provider == "nvidia":
                require("nvidia_api_key", self._settings.nvidia_api_key, "selected fact-check provider")
            if self._settings.fact_check_fallback_provider == "openai":
                require("openai_api_key", self._settings.openai_api_key, "optional fact-check fallback", required=False)
            if self._settings.voice_provider == "elevenlabs":
                require("elevenlabs_api_key", self._settings.elevenlabs_api_key, "selected narration provider")
        if self._settings.video_provider == "pexels" and not local_visual_manifest:
            require("pexels_api_key", self._settings.pexels_api_key, "selected visual provider")
        if (
            profile in {"factory", "audio"}
            and self._settings.vision_enabled
            and not local_visual_manifest
        ):
            vision_credentials = {
                "openai": ("openai_api_key", self._settings.openai_api_key),
                "nvidia": ("nvidia_api_key", self._settings.nvidia_api_key),
                "anthropic": ("anthropic_api_key", self._settings.anthropic_api_key),
            }
            name, value = vision_credentials[self._settings.vision_provider]
            require(name, value, "enabled vision provider")
        if profile == "trends":
            require("youtube_data_api_key", self._settings.youtube_data_api_key, "trend discovery profile")
            if self._settings.topic_selection_provider == "nvidia":
                require("nvidia_api_key", self._settings.nvidia_api_key, "trend topic selection provider")

        checks: list[SystemHealthCheck] = []
        for name, (value, required, reason) in sorted(requirements.items()):
            present = bool(value.strip())
            status = "PASS" if present else ("FAIL" if required else "WARN")
            checks.append(SystemHealthCheck(
                name=name,
                status=status,
                required=required,
                details=f"Configured for {reason}." if present else f"Missing; needed for {reason}.",
                remediation=None if present else f"Set {name.upper()} in the local .env file.",
            ))
        return checks

    def _storage_checks(
        self,
        run_directory: str | Path,
        output_directory: str | Path | None,
    ) -> list[SystemHealthCheck]:
        resolved_output = self._resolve(
            output_directory or self._settings.storage_root_dir
        )
        storage_paths = {
            "output_directory": resolved_output,
            "voice_cache_directory": self._resolve(self._settings.voice_cache_dir),
            "run_checkpoint_directory": self._resolve(run_directory),
        }
        checks = [
            self._directory_check(name, path) for name, path in storage_paths.items()
        ]
        try:
            free_gb = shutil.disk_usage(resolved_output).free / (1024 ** 3)
        except OSError as error:
            checks.append(self._result(
                "free_disk_space",
                False,
                True,
                f"Could not inspect {resolved_output}: {type(error).__name__}.",
                "Choose an accessible output directory.",
            ))
            return checks
        checks.append(self._result(
            "free_disk_space",
            free_gb >= self._minimum_free_disk_gb,
            True,
            f"{free_gb:.2f} GB free at {resolved_output}; minimum "
            f"{self._minimum_free_disk_gb:.2f} GB.",
            "Free disk space before downloading assets or rendering.",
        ))
        return checks

    def _command_check(
        self,
        name: str,
        configured_command: str,
        arguments: list[str],
    ) -> SystemHealthCheck:
        command = configured_command.strip()
        resolved = (
            str(self._resolve(command))
            if Path(command).parent != Path(".")
            else self._lookup(command)
        )
        if not resolved or not Path(resolved).exists():
            return self._result(
                name, False, True, f"Executable '{command}' was not found.",
                f"Install {name} or configure its executable path.",
            )
        try:
            completed = self._run_command(
                [resolved, *arguments],
                cwd=self._project_root,
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            return self._result(
                name, False, True, f"Executable probe failed: {type(error).__name__}.",
                f"Repair the {name} installation or executable path.",
            )
        first_line = (completed.stdout or completed.stderr or "").splitlines()[:1]
        return self._result(
            name,
            completed.returncode == 0,
            True,
            first_line[0][:180] if first_line else f"Exit code {completed.returncode}.",
            f"Repair the {name} installation or executable path.",
        )

    def _directory_check(self, name: str, path: Path) -> SystemHealthCheck:
        try:
            path.mkdir(parents=True, exist_ok=True)
            descriptor, probe_path = tempfile.mkstemp(prefix=".selma-health-", dir=path)
            os.close(descriptor)
            Path(probe_path).unlink()
        except OSError as error:
            return self._result(
                name, False, True, f"Cannot write to {path}: {type(error).__name__}.",
                "Choose a writable directory and verify filesystem permissions.",
            )
        return self._result(name, True, True, f"Writable: {path}.", "")

    def _resolve(self, path: str | Path) -> Path:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = self._project_root / candidate
        return candidate.resolve()

    @staticmethod
    def _result(
        name: str,
        passed: bool,
        required: bool,
        details: str,
        remediation: str,
    ) -> SystemHealthCheck:
        return SystemHealthCheck(
            name=name,
            status="PASS" if passed else ("FAIL" if required else "WARN"),
            required=required,
            details=details,
            remediation=None if passed else remediation,
        )
