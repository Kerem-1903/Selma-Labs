import asyncio
import logging
import os
from pathlib import Path

from core.domain.entities.timeline import Timeline
from core.domain.exceptions import RenderError
from core.domain.ports.render_port import RenderPort
from core.domain.value_objects.render_result import RenderResult

logger = logging.getLogger(__name__)

class NVENCFastRenderAdapter(RenderPort):
    def __init__(
        self,
        ffmpeg_path: str = "ffmpeg",
        use_gpu: bool = True,
        timeout_seconds: int = 900
    ) -> None:
        self.ffmpeg_path = ffmpeg_path
        self.use_gpu = use_gpu
        self.timeout_seconds = timeout_seconds

    async def render(
        self,
        timeline: Timeline,
        narration_audio_path: str,
        subtitle_path: str | None = None,
    ) -> RenderResult:
        raise NotImplementedError("This adapter is optimized for the render_shorts method.")

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
        """
        NVENC and Audio Ducking powered single-pass video render.
        """
        if not video_clips:
            raise RenderError("No video clips provided for rendering.")

        concat_file = Path(output_path).with_suffix(".txt")
        try:
            with open(concat_file, "w", encoding="utf-8") as f:
                for clip in video_clips:
                    f.write(f"file '{Path(clip).resolve()}'\\n")

            vcodec = "h264_nvenc -preset p6 -tune hq" if self.use_gpu else "libx264 -preset fast"
            hwaccel_args = ["-hwaccel", "cuda"] if self.use_gpu else []

            # Filter graph construction
            filters = []

            # Map video
            video_map = "0:v"
            if subtitle_ass_path:
                filters.append(f"[0:v]subtitles='{subtitle_ass_path}'[v_out]")
                video_map = "[v_out]"

            # Map audio
            if background_music_path:
                # [1:a] is voiceover, [2:a] is background music
                audio_filter = (
                    "[2:a]volume=0.3[bgm_soft];"
                    "[1:a]asplit=2[voice_out][voice_sidechain];"
                    "[bgm_soft][voice_sidechain]sidechaincompress=threshold=0.0625:ratio=10:attack=50:release=300[bgm_ducked];"
                    "[bgm_ducked][voice_out]amix=inputs=2:duration=first:dropout_transition=2[audio_out]"
                )
                filters.append(audio_filter)
                audio_map = "[audio_out]"
            else:
                audio_map = "1:a"

            filter_complex = ";".join(filters)

            cmd = [
                self.ffmpeg_path, "-y",
                *hwaccel_args,
                "-f", "concat",
                "-safe", "0",
                "-i", str(concat_file.resolve()),
                "-i", str(Path(audio_path).resolve())
            ]

            if background_music_path:
                cmd.extend(["-i", str(Path(background_music_path).resolve())])

            if filter_complex:
                cmd.extend(["-filter_complex", filter_complex])

            cmd.extend([
                "-map", video_map,
                "-map", audio_map,
                "-c:v"
            ])
            cmd.extend(vcodec.split())
            cmd.extend([
                "-c:a", "aac",
                "-b:a", "192k",
                "-shortest",
                str(Path(output_path).resolve())
            ])

            logger.info("Starting NVENC fast render with command: %s", " ".join(cmd))

            # Process execution with process groups for safe cancellation
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                preexec_fn=os.setsid
            )

            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=self.timeout_seconds)
                if process.returncode != 0:
                    error_msg = stderr.decode() if stderr else "Unknown FFmpeg error"
                    raise RenderError(f"NVENC rendering failed: {error_msg}")
            except asyncio.TimeoutError as error:
                import signal
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                except ProcessLookupError:
                    pass
                raise RenderError(f"Render process timed out after {self.timeout_seconds} seconds") from error
            finally:
                if process.returncode is None:
                    import signal
                    try:
                        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                    except ProcessLookupError:
                        pass

            return output_path
        finally:
            if concat_file.exists():
                concat_file.unlink()
