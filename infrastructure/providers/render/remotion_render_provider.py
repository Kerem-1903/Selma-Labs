"""Creative Remotion composition with a single FFmpeg delivery encode."""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlparse

from core.domain.entities.timeline import Timeline
from core.domain.exceptions import RenderExecutionError
from core.domain.ports.render_port import RenderPort
from core.domain.value_objects.render_result import RenderResult
from infrastructure.providers.render.ffmpeg_render_provider import FfmpegRenderProvider
from infrastructure.providers.render.studio_audio_filter_graph import (
    build_studio_audio_filters,
)


class RemotionRenderProvider(RenderPort):
    """Render motion graphics in ProRes, then master narration and H.264 once."""

    def __init__(
        self,
        *,
        project_directory: str = "motion",
        remotion_cli_path: str = "",
        ffmpeg_binary: str = "ffmpeg",
        ffmpeg_fallback: FfmpegRenderProvider | None = None,
        subprocess_timeout_seconds: float = 900.0,
        background_music_volume: float = 0.16,
    ) -> None:
        project = Path(project_directory).resolve()
        if subprocess_timeout_seconds <= 0:
            raise ValueError("subprocess_timeout_seconds must be greater than zero.")
        if not 0.0 < background_music_volume <= 1.0:
            raise ValueError("background_music_volume must be within (0, 1].")
        self._project = project
        self._cli = Path(remotion_cli_path).resolve() if remotion_cli_path else (
            project / "node_modules" / ".bin" / "remotion.cmd"
        )
        self._ffmpeg = ffmpeg_binary
        self._fallback = ffmpeg_fallback or FfmpegRenderProvider(
            ffmpeg_binary=ffmpeg_binary
        )
        self._timeout = subprocess_timeout_seconds
        self._music_volume = background_music_volume

    async def render(
        self,
        timeline: Timeline,
        narration_audio_path: str,
        subtitle_path: str | None = None,
    ) -> RenderResult:
        """Keep the legacy Timeline API available through the FFmpeg adapter."""
        return await self._fallback.render(
            timeline,
            narration_audio_path,
            subtitle_path=subtitle_path,
        )

    async def render_shorts(
        self,
        audio_path: str,
        subtitle_ass_path: str,
        video_clips: list[str],
        output_path: str,
        *,
        audio_start_ms: int = 0,
        audio_end_ms: int | None = None,
        clip_durations_seconds: list[float] | None = None,
        motion_types: list[str] | None = None,
        shot_types: list[str] | None = None,
        visual_jobs: list[str] | None = None,
        background_music_path: str | None = None,
        procedural_audio_accents: bool = False,
        sound_design_plan: dict | None = None,
        creative_timeline_path: str | None = None,
    ) -> str:
        if creative_timeline_path is None:
            return await self._fallback.render_shorts(
                audio_path,
                subtitle_ass_path,
                video_clips,
                output_path,
                audio_start_ms=audio_start_ms,
                audio_end_ms=audio_end_ms,
                clip_durations_seconds=clip_durations_seconds,
                motion_types=motion_types,
                shot_types=shot_types,
                visual_jobs=visual_jobs,
                background_music_path=background_music_path,
                procedural_audio_accents=procedural_audio_accents,
                sound_design_plan=sound_design_plan,
            )

        audio = Path(audio_path).resolve()
        props = Path(creative_timeline_path).resolve()
        destination = Path(output_path).resolve()
        if not audio.is_file():
            raise RenderExecutionError(f"Audio file not found at '{audio}'.")
        if not props.is_file():
            raise RenderExecutionError(f"Remotion timeline not found at '{props}'.")
        if not self._project.is_dir():
            raise RenderExecutionError(
                f"Remotion project directory not found at '{self._project}'."
            )
        if not self._cli.is_file():
            raise RenderExecutionError(
                f"Remotion CLI not found at '{self._cli}'. Run npm install in motion/."
            )
        if background_music_path is not None and not Path(background_music_path).is_file():
            raise RenderExecutionError(
                f"Background music file not found at '{background_music_path}'."
            )

        full_audio_duration = await self._probe_duration(audio)
        source_duration_ms = round(full_audio_duration * 1_000)
        effective_end_ms = source_duration_ms if audio_end_ms is None else audio_end_ms
        effective_end_ms = FfmpegRenderProvider._normalize_audio_end_ms(
            effective_end_ms,
            source_duration_ms,
        )
        if audio_start_ms < 0 or effective_end_ms <= audio_start_ms:
            raise RenderExecutionError("Selected audio bounds must have positive duration.")
        duration = (effective_end_ms - audio_start_ms) / 1_000

        destination.parent.mkdir(parents=True, exist_ok=True)
        work_dir = Path(tempfile.mkdtemp(prefix="selma-remotion-"))
        visual_master = work_dir / "creative-master.mov"
        try:
            staged_props, public_directory = await asyncio.to_thread(
                self._stage_props,
                props,
                work_dir,
            )
            await self._run(
                [
                    str(self._cli),
                    "render",
                    "src/index.ts",
                    "StrangeThingsShort",
                    str(visual_master),
                    f"--props={staged_props}",
                    f"--public-dir={public_directory}",
                    "--codec=prores",
                    "--prores-profile=hq",
                    "--pixel-format=yuv422p10le",
                    "--muted",
                    "--log=error",
                ],
                context="rendering the Remotion creative master",
                cwd=self._project,
            )
            await self._master_delivery(
                visual_master,
                audio,
                destination,
                audio_start_seconds=audio_start_ms / 1_000,
                duration_seconds=duration,
                background_music_path=background_music_path,
                procedural_audio_accents=procedural_audio_accents,
                sound_design_plan=sound_design_plan,
            )
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

        if not destination.is_file() or destination.stat().st_size == 0:
            raise RenderExecutionError("Hybrid renderer did not create a usable MP4.")
        return str(destination)

    @staticmethod
    def _stage_props(props_path: Path, work_dir: Path) -> tuple[Path, Path]:
        """Expose local clips through Remotion's isolated public directory."""
        try:
            payload = json.loads(props_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise RenderExecutionError(
                f"Could not read Remotion timeline '{props_path}': {error}"
            ) from error

        public_directory = work_dir / "public"
        public_directory.mkdir(parents=True, exist_ok=True)
        staged_by_source: dict[Path, str] = {}
        for index, scene in enumerate(payload.get("scenes", [])):
            source_value = str(scene.get("source", "")).strip()
            if not source_value or source_value.lower().startswith(("http://", "https://")):
                continue
            source = RemotionRenderProvider._local_path_from_source(source_value)
            if not source.is_file():
                raise RenderExecutionError(
                    f"Remotion scene source not found at '{source}'."
                )
            resolved_source = source.resolve()
            staged_name = staged_by_source.get(resolved_source)
            if staged_name is None:
                staged_name = f"clip-{index:03d}{resolved_source.suffix.lower()}"
                staged_path = public_directory / staged_name
                try:
                    os.link(resolved_source, staged_path)
                except OSError:
                    shutil.copy2(resolved_source, staged_path)
                staged_by_source[resolved_source] = staged_name
            scene["source"] = staged_name

        staged_props = work_dir / "props.json"
        staged_props.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return staged_props, public_directory

    @staticmethod
    def _local_path_from_source(source: str) -> Path:
        if source.lower().startswith("file://"):
            parsed_path = unquote(urlparse(source).path)
            if os.name == "nt" and parsed_path.startswith("/"):
                parsed_path = parsed_path[1:]
            return Path(parsed_path)
        return Path(source)

    async def _master_delivery(
        self,
        visual_master: Path,
        audio: Path,
        destination: Path,
        *,
        audio_start_seconds: float,
        duration_seconds: float,
        background_music_path: str | None,
        procedural_audio_accents: bool,
        sound_design_plan: dict | None,
    ) -> None:
        command = [self._ffmpeg, "-y", "-i", str(visual_master), "-i", str(audio)]
        music_index: int | None = None
        if background_music_path is not None:
            music_index = 2
            command.extend(["-stream_loop", "-1", "-i", background_music_path])

        filters = build_studio_audio_filters(
            voice_input_index=1,
            music_input_index=music_index,
            audio_start_seconds=audio_start_seconds,
            duration_seconds=duration_seconds,
            background_music_volume=self._music_volume,
            sound_design_plan=sound_design_plan,
            legacy_procedural_accents=procedural_audio_accents,
        )

        command.extend(
            [
                "-filter_complex", ";".join(filters),
                "-map", "0:v:0", "-map", "[audio]",
                "-c:v", "libx264", "-preset", "slow", "-crf", "17",
                "-profile:v", "high", "-pix_fmt", "yuv420p",
                "-x264-params", "colorprim=bt709:transfer=bt709:colormatrix=bt709:range=limited",
                "-colorspace", "bt709", "-color_primaries", "bt709",
                "-color_trc", "bt709", "-color_range", "tv",
                "-c:a", "aac", "-b:a", "384k", "-ar", "48000", "-ac", "2",
                "-t", f"{duration_seconds:.6f}", "-shortest",
                "-movflags", "+faststart", str(destination),
            ]
        )
        await self._run(command, context="mastering the YouTube delivery file")

    async def _probe_duration(self, path: Path) -> float:
        stdout = await self._run(
            [
                self._fallback._ffprobe,
                "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(path),
            ],
            context="probing narration duration",
            capture=True,
        )
        try:
            duration = float(stdout.strip())
        except ValueError as error:
            raise RenderExecutionError("Could not determine narration duration.") from error
        if duration <= 0:
            raise RenderExecutionError("Narration audio has no usable duration.")
        return duration

    async def _run(
        self,
        command: list[str],
        *,
        context: str,
        cwd: Path | None = None,
        capture: bool = False,
    ) -> str:
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=str(cwd) if cwd is not None else None,
                stdout=asyncio.subprocess.PIPE if capture else asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
        except (FileNotFoundError, OSError) as error:
            raise RenderExecutionError(
                f"Could not start '{command[0]}' while {context}: {error}"
            ) from error
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=self._timeout
            )
        except asyncio.TimeoutError as error:
            process.kill()
            await process.communicate()
            raise RenderExecutionError(
                f"Timed out after {self._timeout:.0f}s while {context}."
            ) from error
        except asyncio.CancelledError:
            process.kill()
            await process.communicate()
            raise
        if process.returncode != 0:
            details = (stderr or b"").decode("utf-8", errors="replace")[-3000:]
            raise RenderExecutionError(
                f"Process failed while {context} (exit {process.returncode}): {details}"
            )
        return (stdout or b"").decode("utf-8", errors="replace")
