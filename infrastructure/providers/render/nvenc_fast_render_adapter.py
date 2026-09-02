import asyncio
import logging
import os
from pathlib import Path

from core.domain.entities.timeline import Timeline
from core.domain.exceptions import RenderError
from core.domain.ports.render_port import RenderPort
from core.domain.value_objects.render_result import RenderResult
from infrastructure.providers.render.smart_cropping_service import SmartCroppingService
from infrastructure.providers.render.studio_audio_filter_graph import build_studio_audio_filters

logger = logging.getLogger(__name__)

class NVENCFastRenderAdapter(RenderPort):
    def __init__(
        self,
        ffmpeg_path: str = "ffmpeg",
        use_gpu: bool = True,
        timeout_seconds: int = 900,
        smart_crop: bool = True,
        output_width: int = 1080,
        output_height: int = 1920
    ) -> None:
        self.ffmpeg_path = ffmpeg_path
        self.use_gpu = use_gpu
        self.timeout_seconds = timeout_seconds
        self.smart_crop = smart_crop
        self.output_width = output_width
        self.output_height = output_height
        self.cropping_service = SmartCroppingService(target_ratio=output_width/output_height) if smart_crop else None

    async def render(
        self,
        timeline: Timeline,
        narration_audio_path: str,
        subtitle_path: str | None = None,
    ) -> RenderResult:
        import uuid
        import tempfile

        tmp_dir = Path(tempfile.gettempdir())
        output_path = str(tmp_dir / f"selma-rendered-{uuid.uuid4().hex}.mp4")

        video_clips = [clip.asset.local_path for clip in timeline.clips if clip.asset and getattr(clip.asset, 'local_path', None)]
        clip_durations = [(clip.scene.end_time - clip.scene.start_time) for clip in timeline.clips]

        await self.render_shorts(
            audio_path=narration_audio_path,
            subtitle_ass_path=subtitle_path,
            video_clips=video_clips,
            output_path=output_path,
            clip_durations_seconds=clip_durations
        )

        size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
        return RenderResult(file_path=output_path, file_size_bytes=size)

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
        if not video_clips:
            raise RenderError("No video clips provided for rendering.")

        vcodec = "h264_nvenc -preset p6 -tune hq" if self.use_gpu else "libx264 -preset fast"
        hwaccel_args = ["-hwaccel", "cuda"] if self.use_gpu else []

        cmd = [self.ffmpeg_path, "-y", *hwaccel_args]

        # Add all video inputs
        for clip in video_clips:
            cmd.extend(["-i", str(Path(clip).resolve())])

        audio_input_idx = len(video_clips)
        cmd.extend(["-i", str(Path(audio_path).resolve())])

        music_input_idx = None
        if background_music_path:
            music_input_idx = audio_input_idx + 1
            cmd.extend(["-i", str(Path(background_music_path).resolve())])

        filters = []

        # Process each video clip
        for i, clip in enumerate(video_clips):
            # If smart crop is enabled, fetch crop params
            crop_cmd = f"crop={self.output_width}:{self.output_height}:(in_w-{self.output_width})/2:(in_h-{self.output_height})/2"
            if self.smart_crop and self.cropping_service:
                # Do this in a thread to prevent blocking asyncio
                crop_cmd = await asyncio.to_thread(
                    self.cropping_service.get_crop_filter, clip, self.output_width, self.output_height
                )

            # If clip duration is provided, trim it. Otherwise just use it as is.
            duration_filter = ""
            if clip_durations_seconds and i < len(clip_durations_seconds):
                dur = clip_durations_seconds[i]
                duration_filter = f"trim=duration={dur:.6f},setpts=PTS-STARTPTS,"

            filters.append(f"[{i}:v]{duration_filter}scale=ceil(in_w*max({self.output_width}/in_w\\,{self.output_height}/in_h)/2)*2:ceil(in_h*max({self.output_width}/in_w\\,{self.output_height}/in_h)/2)*2,{crop_cmd},setsar=1/1,format=yuv420p[v{i}]")

        # Concat video streams
        concat_inputs = "".join([f"[v{i}]" for i in range(len(video_clips))])
        filters.append(f"{concat_inputs}concat=n={len(video_clips)}:v=1:a=0[joined]")

        video_map = "[joined]"
        if subtitle_ass_path:
            escaped_sub = str(Path(subtitle_ass_path).resolve()).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")
            filters.append(f"[joined]subtitles='{escaped_sub}'[v_out]")
            video_map = "[v_out]"

        # Build full studio audio filters with SFX, Ducking, and Voice EQ
        total_duration = sum(clip_durations_seconds) if clip_durations_seconds else 60.0

        audio_filters = build_studio_audio_filters(
            voice_input_index=audio_input_idx,
            music_input_index=music_input_idx,
            audio_start_seconds=audio_start_ms / 1000.0,
            duration_seconds=total_duration,
            background_music_volume=0.3,
            sound_design_plan=sound_design_plan,
            legacy_procedural_accents=procedural_audio_accents
        )
        filters.extend(audio_filters)
        audio_map = "[audio]"

        filter_complex = ";".join(filters)

        cmd.extend([
            "-filter_complex", filter_complex,
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

        logger.info("Starting NVENC fast render with Smart Cropping command: %s", " ".join(cmd))

        kwargs = {}
        if os.name == "posix":
            kwargs["start_new_session"] = True

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **kwargs
        )

        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=self.timeout_seconds)
            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown FFmpeg error"
                raise RenderError(f"NVENC rendering failed: {error_msg}")
        except asyncio.TimeoutError as error:
            if os.name == "posix":
                import signal
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                except ProcessLookupError:
                    pass
            else:
                process.terminate()
            raise RenderError(f"Render process timed out after {self.timeout_seconds} seconds") from error
        finally:
            if process.returncode is None:
                if os.name == "posix":
                    import signal
                    try:
                        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                else:
                    process.kill()

        return output_path
