"""Render and verify a Remotion animatic outside the domain layer."""

from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

from core.domain.entities.animatic_project import AnimaticProject
from core.domain.exceptions import RenderExecutionError
from core.domain.ports.media_inspection_port import MediaInspectionPort
from core.domain.value_objects.media_inspection import MediaInspection


@dataclass(frozen=True)
class AnimaticRenderResult:
    status: str
    output_path: str
    inspection: MediaInspection | None = None
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "output_path": self.output_path,
            "inspection": self.inspection.to_dict() if self.inspection else None,
            "error": self.error,
        }


class AnimaticRenderService:
    """Run Remotion and fail closed unless ffprobe matches the project contract."""

    def __init__(
        self,
        *,
        motion_directory: str | Path = "motion",
        remotion_binary: str = "npx",
        inspector: MediaInspectionPort,
        timeout_seconds: float = 300.0,
        browser_executable: str | Path | None = None,
    ) -> None:
        self._motion_directory = Path(motion_directory)
        self._remotion_binary = (
            f"{remotion_binary}.cmd"
            if sys.platform == "win32" and remotion_binary == "npx"
            else remotion_binary
        )
        self._inspector = inspector
        self._timeout_seconds = timeout_seconds
        self._browser_executable = (
            str(Path(browser_executable).resolve())
            if browser_executable
            else ""
        )

    async def render(
        self,
        project: AnimaticProject,
        *,
        props_path: str | Path,
        output_path: str | Path,
    ) -> AnimaticRenderResult:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        # Keep the final media suffix so Remotion selects an MP4-capable
        # container while the temporary file remains unpublished.
        temporary = output.with_name(f".{output.stem}.rendering{output.suffix}")
        temporary.unlink(missing_ok=True)
        command = [
            self._remotion_binary,
            "remotion",
            "render",
            "src/index.ts",
            "AnimeAnimatic",
            str(temporary.resolve()),
            f"--props={Path(props_path).resolve()}",
            "--log=error",
        ]
        if self._browser_executable:
            command.insert(-1, f"--browser-executable={self._browser_executable}")
        process = None
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=str(self._motion_directory.resolve()),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=self._timeout_seconds
            )
            if process.returncode != 0:
                detail = (stderr or stdout or b"").decode("utf-8", errors="replace")[-3000:]
                raise RenderExecutionError(f"Remotion render failed: {detail}")
            if not temporary.is_file() or temporary.stat().st_size <= 0:
                raise RenderExecutionError("Remotion completed without an MP4 output.")
            inspection = await self._inspector.inspect(str(temporary))
            expected_duration = project.duration_in_frames / project.fps
            if inspection.fps_fraction != Fraction(project.fps, 1):
                raise RenderExecutionError(
                    f"Rendered FPS {inspection.fps_rational} does not match {project.fps}/1."
                )
            if inspection.frame_count is not None:
                if inspection.frame_count != project.duration_in_frames:
                    raise RenderExecutionError(
                        f"Rendered frame count {inspection.frame_count} does not match "
                        f"{project.duration_in_frames}."
                    )
            elif abs((inspection.video_duration_seconds or inspection.duration_seconds) - expected_duration) > (1 / project.fps):
                raise RenderExecutionError(
                    f"Rendered video duration {inspection.video_duration_seconds or inspection.duration_seconds:.4f}s does not match "
                    f"{expected_duration:.4f}s."
                )
            os.replace(temporary, output)
            return AnimaticRenderResult(
                status="READY_FOR_REVIEW",
                output_path=str(output),
                inspection=inspection,
            )
        except (RenderExecutionError, asyncio.TimeoutError) as error:
            if process is not None and process.returncode is None:
                process.kill()
                await process.communicate()
            temporary.unlink(missing_ok=True)
            if isinstance(error, asyncio.TimeoutError):
                error = RenderExecutionError("Remotion render timed out.")
            return AnimaticRenderResult(
                status="FAILED",
                output_path=str(output),
                error=str(error),
            )
        except Exception as error:  # noqa: BLE001 - provider boundary fails closed
            if process is not None and process.returncode is None:
                process.kill()
                await process.communicate()
            temporary.unlink(missing_ok=True)
            return AnimaticRenderResult(
                status="FAILED",
                output_path=str(output),
                error=str(error),
            )
