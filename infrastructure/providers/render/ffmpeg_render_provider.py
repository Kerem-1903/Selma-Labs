"""
FfmpegRenderProvider — concrete RenderPort adapter that shells out to the
``ffmpeg``/``ffprobe`` binaries.

This is the only file in the codebase that knows FFmpeg exists, or what its
CLI flags look like. RenderService and everything above it depends on
RenderPort, never on this class directly -- same separation every other
provider in this codebase already keeps from its Port.

Unlike PexelsProvider/ElevenLabsVoiceProvider/ClaudeScriptProvider (which
call a third-party HTTP API via httpx/an SDK), this adapter's external
system is a local subprocess, not a network call. Error mapping is
therefore based on subprocess exit codes and stderr, not HTTP status codes:
a non-zero exit from either binary, or a missing binary
(``FileNotFoundError``), is wrapped in ``RenderError`` -- this codebase has
no typed distinction (auth/timeout/quota) for subprocess failures the way
it does for HTTP providers, since none of those categories apply here.

Rendering approach, deliberately simple (no transitions/effects -- explicitly
out of Sprint 6/7 scope per the founding proposal):
1. Each clip is independently trimmed to its scene duration and normalized
   to one target resolution/fps/pixel format, so every segment is
   byte-compatible for concatenation (FFmpeg's concat *demuxer* requires
   matching codec parameters across inputs -- normalizing up front avoids
   the more fragile concat *filter* approach for a first implementation).
2. Normalized segments are concatenated (video only, no audio) via the
   concat demuxer.
3. The narration audio is muxed onto the concatenated video in one final
   pass, trimmed to whichever stream is shorter (``-shortest``) so the
   output never runs longer than the narration.
4. ``ffprobe`` reads the final file's actual duration/resolution/fps back
   for RenderResult, rather than trusting Timeline's own
   total_duration_seconds or assuming the configured resolution held --
   this is what the render engine actually produced, which is the whole
   reason to probe rather than echo the config back.

Every intermediate file lives in one process-local temporary directory
(cleaned up in a ``finally`` block); only the final muxed file survives,
copied out to its own temp path and returned via RenderResult.output_path,
per RenderResult's contract -- RenderService owns that file from there.
"""
from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
from pathlib import Path

from core.domain.entities.timeline import Timeline
from core.domain.exceptions import RenderError, RenderExecutionError
from core.domain.ports.render_port import RenderPort
from core.domain.value_objects.render_result import RenderResult
from infrastructure.providers.render.studio_audio_filter_graph import (
    build_studio_audio_filters,
)


class FfmpegRenderProvider(RenderPort):
    """Renders a Timeline into an MP4 file using local FFmpeg/ffprobe
    binaries."""

    _AUDIO_BOUNDARY_TOLERANCE_MS = 50

    def __init__(
        self,
        ffmpeg_binary: str = "ffmpeg",
        ffprobe_binary: str = "ffprobe",
        output_width: int = 1080,
        output_height: int = 1920,
        fps: int = 30,
        subprocess_timeout_seconds: float = 300.0,
        termination_grace_seconds: float = 5.0,
        maximum_cut_duration_seconds: float = 3.5,
        background_music_volume: float = 0.16,
    ) -> None:
        if subprocess_timeout_seconds <= 0:
            raise ValueError("subprocess_timeout_seconds must be greater than zero.")
        if termination_grace_seconds <= 0:
            raise ValueError("termination_grace_seconds must be greater than zero.")
        if maximum_cut_duration_seconds <= 0:
            raise ValueError("maximum_cut_duration_seconds must be greater than zero.")
        if not 0.0 < background_music_volume <= 1.0:
            raise ValueError("background_music_volume must be within (0, 1].")
        self._ffmpeg = ffmpeg_binary
        self._ffprobe = ffprobe_binary
        self._width = output_width
        self._height = output_height
        self._fps = fps
        self._subprocess_timeout_seconds = subprocess_timeout_seconds
        self._termination_grace_seconds = termination_grace_seconds
        self._maximum_cut_duration_seconds = maximum_cut_duration_seconds
        self._background_music_volume = background_music_volume

    async def render(
        self,
        timeline: Timeline,
        narration_audio_path: str,
        subtitle_path: str | None = None,
    ) -> RenderResult:
        if not timeline.clips:
            raise RenderError(f"Cannot render Timeline '{timeline.id}': it has no clips.")

        if not Path(narration_audio_path).is_file():
            raise RenderError(
                f"Narration audio file not found at '{narration_audio_path}'."
            )
        if subtitle_path is not None and not Path(subtitle_path).is_file():
            raise RenderError(f"Subtitle file not found at '{subtitle_path}'.")

        work_dir = Path(tempfile.mkdtemp(prefix="selma-render-"))
        try:
            segment_paths = await self._normalize_segments(timeline, work_dir)
            concatenated_path = await self._concatenate(segment_paths, work_dir)
            final_path = self._final_output_path()
            await self._mux_audio(
                concatenated_path,
                narration_audio_path,
                final_path,
                subtitle_path=subtitle_path,
            )
            probe = await self._probe(final_path)
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

        return RenderResult(
            output_path=str(final_path),
            duration_seconds=probe["duration_seconds"],
            width=probe["width"],
            height=probe["height"],
            fps=probe["fps"],
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
        """Concatenate portrait footage, burn ASS captions, and mux a hook.

        Each input clip is normalized and trimmed before concat. If the
        supplied footage is shorter than the selected audio excerpt, clips
        are cycled until the exact audio duration is covered. All subprocess
        work remains asynchronous through :meth:`_run`.
        """
        del creative_timeline_path  # Used by motion renderers; FFmpeg keeps ASS compatibility.
        try:
            if not video_clips:
                raise RenderExecutionError("Cannot render a Short without video clips.")
            if not Path(audio_path).is_file():
                raise RenderExecutionError(f"Audio file not found at '{audio_path}'.")
            if not Path(subtitle_ass_path).is_file():
                raise RenderExecutionError(
                    f"ASS subtitle file not found at '{subtitle_ass_path}'."
                )
            if any(not Path(clip).is_file() for clip in video_clips):
                raise RenderExecutionError("One or more selected video clips are missing.")
            if background_music_path is not None and not Path(background_music_path).is_file():
                raise RenderExecutionError(
                    f"Background music file not found at '{background_music_path}'."
                )
            if audio_start_ms < 0:
                raise RenderExecutionError("audio_start_ms must not be negative.")
            if clip_durations_seconds is not None and len(clip_durations_seconds) != len(video_clips):
                raise RenderExecutionError(
                    "Storyboard clip durations must match the selected clip count."
                )
            if motion_types is not None and len(motion_types) != len(video_clips):
                raise RenderExecutionError(
                    "Storyboard motion types must match the selected clip count."
                )
            if shot_types is not None and len(shot_types) != len(video_clips):
                raise RenderExecutionError(
                    "Storyboard shot types must match the selected clip count."
                )
            if visual_jobs is not None and len(visual_jobs) != len(video_clips):
                raise RenderExecutionError(
                    "Storyboard visual jobs must match the selected clip count."
                )

            full_audio_duration = await self._probe_media_duration(Path(audio_path))
            effective_end_ms = (
                round(full_audio_duration * 1_000)
                if audio_end_ms is None
                else audio_end_ms
            )
            effective_end_ms = self._normalize_audio_end_ms(
                effective_end_ms,
                round(full_audio_duration * 1_000),
            )
            if effective_end_ms <= audio_start_ms:
                raise RenderExecutionError("Selected audio bounds must have positive duration.")

            target_duration_seconds = (effective_end_ms - audio_start_ms) / 1_000
            destination = Path(output_path).resolve()
            destination.parent.mkdir(parents=True, exist_ok=True)
            segments = self._plan_shorts_segments(
                video_clips,
                target_duration_seconds,
                clip_durations_seconds=clip_durations_seconds,
            )
            planned_motion_types = [
                (motion_types or ["steady"])[index % len(motion_types or ["steady"])]
                for index in range(len(segments))
            ]
            planned_shot_types = [
                (shot_types or ["medium"])[index % len(shot_types or ["medium"])]
                for index in range(len(segments))
            ]
            planned_visual_jobs = [
                (visual_jobs or ["support_context"])[
                    index % len(visual_jobs or ["support_context"])
                ]
                for index in range(len(segments))
            ]
            await self._render_shorts_single_pass(
                segments,
                audio_path,
                destination,
                subtitle_ass_path,
                audio_start_seconds=audio_start_ms / 1_000,
                audio_duration_seconds=target_duration_seconds,
                motion_types=planned_motion_types,
                shot_types=planned_shot_types,
                visual_jobs=planned_visual_jobs,
                background_music_path=background_music_path,
                procedural_audio_accents=procedural_audio_accents,
                sound_design_plan=sound_design_plan,
            )

            if not destination.is_file() or destination.stat().st_size == 0:
                raise RenderExecutionError("FFmpeg completed without creating a usable MP4.")
            return str(destination)
        except RenderExecutionError:
            raise
        except RenderError as error:
            raise RenderExecutionError(str(error)) from error
        except OSError as error:
            raise RenderExecutionError(f"Could not prepare Shorts render: {error}") from error

    @classmethod
    def _normalize_audio_end_ms(cls, requested_ms: int, source_duration_ms: int) -> int:
        overshoot_ms = requested_ms - source_duration_ms
        if overshoot_ms <= 0:
            return requested_ms
        if overshoot_ms <= cls._AUDIO_BOUNDARY_TOLERANCE_MS:
            return source_duration_ms
        raise RenderExecutionError("Selected audio bounds exceed the source audio duration.")

    def _plan_shorts_segments(
        self,
        video_clips: list[str],
        target_duration_seconds: float,
        *,
        clip_durations_seconds: list[float] | None = None,
    ) -> list[tuple[Path, float, float]]:
        """Plan bounded editorial cuts without creating encoded intermediates."""
        if clip_durations_seconds is not None:
            if len(clip_durations_seconds) != len(video_clips):
                raise RenderExecutionError(
                    "Storyboard clip durations must match the selected clip count."
                )
            if any(duration <= 0 for duration in clip_durations_seconds):
                raise RenderExecutionError(
                    "Storyboard clip durations must all be positive."
                )
            duration_delta = target_duration_seconds - sum(clip_durations_seconds)
            if abs(duration_delta) > 0.050:
                raise RenderExecutionError(
                    "Storyboard clip durations must cover the selected audio duration."
                )
            clip_durations_seconds = list(clip_durations_seconds)
            clip_durations_seconds[-1] += duration_delta

        segments: list[tuple[Path, float, float]] = []
        remaining = target_duration_seconds
        position = 0
        while remaining > 0.001:
            source_path = Path(video_clips[position % len(video_clips)])
            requested_duration = (
                clip_durations_seconds[position]
                if clip_durations_seconds is not None
                else self._maximum_cut_duration_seconds
            )
            duration = min(
                self._maximum_cut_duration_seconds,
                requested_duration,
                remaining,
            )
            segments.append((source_path, duration, position * 1.3))
            remaining -= duration
            position += 1
            if clip_durations_seconds is not None and position >= len(video_clips):
                break
        if remaining > 0.001:
            raise RenderExecutionError(
                "Storyboard segment plan did not cover the selected audio duration."
            )
        return segments

    async def _render_shorts_single_pass(
        self,
        segments: list[tuple[Path, float, float]],
        audio_path: str,
        output_path: Path,
        subtitle_ass_path: str,
        *,
        audio_start_seconds: float,
        audio_duration_seconds: float,
        motion_types: list[str],
        shot_types: list[str],
        visual_jobs: list[str],
        background_music_path: str | None,
        procedural_audio_accents: bool,
        sound_design_plan: dict | None,
    ) -> None:
        """Compose, subtitle, normalize audio, and encode exactly once.

        Every source is looped at the demuxer boundary and trimmed inside one
        filter graph. This removes the former CRF20 intermediate generation
        followed by a second CRF20 final encode.
        """
        command = [self._ffmpeg, "-y"]
        for source_path, _, _ in segments:
            command.extend(["-stream_loop", "-1", "-i", str(source_path)])
        audio_input_index = len(segments)
        command.extend(["-i", audio_path])
        music_input_index: int | None = None
        if background_music_path is not None:
            music_input_index = audio_input_index + 1
            command.extend(["-stream_loop", "-1", "-i", background_music_path])

        filters: list[str] = []
        for index, (_, duration, phase) in enumerate(segments):
            filters.append(
                f"[{index}:v]trim=duration={duration:.6f},setpts=PTS-STARTPTS,"
                f"{self._motion_filter(phase, motion_types[index], shot_types[index], visual_jobs[index])}[v{index}]"
            )
        concat_inputs = "".join(f"[v{index}]" for index in range(len(segments)))
        filters.append(
            f"{concat_inputs}concat=n={len(segments)}:v=1:a=0[joined]"
        )
        filters.append(
            f"[joined]{self._subtitle_filter(subtitle_ass_path)}[video]"
        )
        filters.extend(build_studio_audio_filters(
            voice_input_index=audio_input_index,
            music_input_index=music_input_index,
            audio_start_seconds=audio_start_seconds,
            duration_seconds=audio_duration_seconds,
            background_music_volume=self._background_music_volume,
            sound_design_plan=sound_design_plan,
            legacy_procedural_accents=procedural_audio_accents,
        ))

        command.extend(
            [
                "-filter_complex", ";".join(filters),
                "-map", "[video]",
                "-map", "[audio]",
                "-c:v", "libx264",
                "-preset", "slow",
                "-crf", "17",
                "-profile:v", "high",
                "-x264-params", "colorprim=bt709:transfer=bt709:colormatrix=bt709:range=limited",
                "-pix_fmt", "yuv420p",
                "-colorspace", "bt709",
                "-color_primaries", "bt709",
                "-color_trc", "bt709",
                "-color_range", "tv",
                "-c:a", "aac",
                "-b:a", "384k",
                "-ar", "48000",
                "-ac", "2",
                "-t", f"{audio_duration_seconds:.6f}",
                "-shortest",
                "-movflags", "+faststart",
                str(output_path),
            ]
        )
        await self._run(
            command,
            context="single-pass Shorts composition, loudness normalization, and encode",
        )

    def _motion_filter(
        self,
        phase: float,
        motion_type: str = "steady",
        shot_type: str = "medium",
        visual_job: str = "support_context",
    ) -> str:
        """Return a Ken-Burns treatment that starts on a visible frame.

        ``zoompan`` is deliberately applied after aspect-ratio normalization,
        so both a JPEG/PNG input and a regular MP4 receive real camera motion.
        Editorial boundaries are deliberate hard cuts. In particular, the
        first frame is never faded from black, so the opening visual is usable
        as a hook and thumbnail frame.
        """
        shot_scale = {
            "wide-establishing": 1.03,
            "overhead-wide": 1.06,
            "tracking-medium": 1.10,
            "low-angle-medium": 1.11,
            "macro-close-up": 1.18,
            "detail-insert": 1.22,
        }.get(shot_type, 1.10)
        scaled_width = int(self._width * shot_scale)
        scaled_height = int(self._height * shot_scale)
        if motion_type == "fast-paced":
            zoom_step, x_travel, y_travel = 0.00090, 30, 22
        elif motion_type == "slow-motion":
            zoom_step, x_travel, y_travel = 0.00025, 10, 8
        else:
            zoom_step, x_travel, y_travel = 0.00055, 20, 14
        job_motion = {
            "establish_subject": (1.25, 1.15, 1.00),
            "locate_part": (1.15, 0.45, 0.40),
            "demonstrate_mechanism": (0.90, 1.45, 0.35),
            "compare_states": (0.85, 1.55, 0.55),
            "show_consequence": (0.70, 0.70, 0.65),
            "deliver_payoff": (0.40, 0.45, 0.35),
        }.get(visual_job, (1.0, 1.0, 1.0))
        zoom_step *= job_motion[0]
        x_travel = round(x_travel * job_motion[1])
        y_travel = round(y_travel * job_motion[2])
        return (
            f"scale={scaled_width}:{scaled_height}:force_original_aspect_ratio=increase,"
            f"crop={scaled_width}:{scaled_height},"
            "zoompan="
            f"z='min(zoom+{zoom_step:.5f},1.12)':"
            f"x='iw/2-(iw/zoom/2)+{x_travel}*sin(on/26+{phase})':"
            f"y='ih/2-(ih/zoom/2)+{y_travel}*cos(on/31+{phase})':"
            f"d=1:s={self._width}x{self._height}:fps={self._fps},setsar=1"
        )

    async def _probe_media_duration(self, path: Path) -> float:
        stdout = await self._run(
            [
                self._ffprobe, "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            context=f"probing media duration for '{path.name}'",
            capture=True,
        )
        try:
            duration = float(stdout.strip())
        except ValueError as error:
            raise RenderExecutionError(
                f"Could not determine media duration for '{path}'."
            ) from error
        if duration <= 0:
            raise RenderExecutionError(f"Media file '{path}' has no usable duration.")
        return duration

    async def _normalize_segments(self, timeline: Timeline, work_dir: Path) -> list[Path]:
        segment_paths: list[Path] = []
        for i, clip in enumerate(timeline.clips):
            duration = clip.scene.end_time - clip.scene.start_time
            if duration <= 0:
                raise RenderError(
                    f"Scene {clip.scene.index} has non-positive duration "
                    f"({duration}s); cannot render."
                )
            segment_path = work_dir / f"segment_{i:04d}.mp4"
            phase = i * 1.3
            scaled_width = int(self._width * 1.06)
            scaled_height = int(self._height * 1.06)
            await self._run(
                [
                    self._ffmpeg, "-y",
                    "-stream_loop", "-1",
                    "-i", clip.asset.local_path,
                    "-t", str(duration),
                    "-vf",
                    (
                        f"scale={scaled_width}:{scaled_height}:"
                        "force_original_aspect_ratio=increase,"
                        f"crop={self._width}:{self._height}:"
                        f"x='(in_w-out_w)/2+(in_w-out_w)*0.20*sin(t*0.8+{phase})':"
                        f"y='(in_h-out_h)/2+(in_h-out_h)*0.20*cos(t*0.6+{phase})',"
                        "setsar=1"
                    ),
                    "-r", str(self._fps),
                    "-an",
                    "-c:v", "libx264",
                    "-preset", "ultrafast",
                    "-crf", "0",
                    "-pix_fmt", "yuv420p",
                    str(segment_path),
                ],
                context=f"normalizing clip for scene {clip.scene.index}",
            )
            segment_paths.append(segment_path)
        return segment_paths

    async def _concatenate(self, segment_paths: list[Path], work_dir: Path) -> Path:
        list_file = work_dir / "concat_list.txt"
        list_file.write_text(
            "\n".join(f"file '{p.resolve()}'" for p in segment_paths), encoding="utf-8"
        )
        concatenated_path = work_dir / "concatenated.mp4"
        await self._run(
            [
                self._ffmpeg, "-y",
                "-f", "concat", "-safe", "0",
                "-i", str(list_file),
                "-c", "copy",
                str(concatenated_path),
            ],
            context="concatenating normalized clips",
        )
        return concatenated_path

    async def _mux_audio(
        self,
        video_path: Path,
        audio_path: str,
        output_path: Path,
        *,
        subtitle_path: str | None = None,
    ) -> None:
        command = [
            self._ffmpeg, "-y",
            "-i", str(video_path),
            "-i", audio_path,
            "-map", "0:v", "-map", "1:a",
        ]
        if subtitle_path is None:
            command.extend(["-c:v", "copy"])
        else:
            command.extend(
                [
                    "-vf", self._subtitle_filter(subtitle_path),
                    "-c:v", "libx264",
                    "-preset", "slow",
                    "-crf", "17",
                    "-profile:v", "high",
                    "-x264-params", "colorprim=bt709:transfer=bt709:colormatrix=bt709:range=limited",
                    "-pix_fmt", "yuv420p",
                    "-colorspace", "bt709",
                    "-color_primaries", "bt709",
                    "-color_trc", "bt709",
                    "-color_range", "tv",
                ]
            )
        command.extend(
            [
                "-c:a", "aac",
                "-b:a", "384k",
                "-ar", "48000",
                "-ac", "2",
                "-af", "loudnorm=I=-14:TP=-1.5:LRA=9",
                "-shortest",
                "-movflags", "+faststart",
                str(output_path),
            ]
        )
        await self._run(
            command,
            context="muxing narration audio onto concatenated video",
        )

    @staticmethod
    def _subtitle_filter(subtitle_path: str) -> str:
        escaped = str(Path(subtitle_path).resolve()).replace("\\", "/")
        escaped = escaped.replace(":", r"\:").replace("'", r"\'")
        if Path(subtitle_path).suffix.lower() == ".ass":
            return f"subtitles=filename='{escaped}'"
        style = (
            "FontName=Arial,FontSize=18,Bold=1,PrimaryColour=&H00FFFFFF,"
            "OutlineColour=&H00000000,BorderStyle=1,Outline=3,Shadow=1,"
            "Alignment=2,MarginV=220"
        )
        return f"subtitles=filename='{escaped}':force_style='{style}'"

    async def _probe(self, path: Path) -> dict:
        stdout = await self._run(
            [
                self._ffprobe, "-v", "error",
                "-print_format", "json",
                "-show_format", "-show_streams",
                str(path),
            ],
            context="probing rendered output",
            capture=True,
        )
        try:
            info = json.loads(stdout)
            video_stream = next(
                s for s in info["streams"] if s.get("codec_type") == "video"
            )
            num, den = (video_stream.get("avg_frame_rate") or "0/1").split("/")
            fps = (float(num) / float(den)) if float(den or 0) else 0.0
            return {
                "duration_seconds": float(info["format"]["duration"]),
                "width": int(video_stream["width"]),
                "height": int(video_stream["height"]),
                "fps": fps,
            }
        except (KeyError, ValueError, StopIteration, json.JSONDecodeError) as exc:
            raise RenderError(
                f"Could not parse ffprobe output for rendered file '{path}': {exc}"
            ) from exc

    def _final_output_path(self) -> Path:
        fd, path = tempfile.mkstemp(prefix="selma-rendered-", suffix=".mp4")
        import os

        os.close(fd)
        return Path(path)

    async def _run(self, command: list[str], *, context: str, capture: bool = False) -> str:
        process: asyncio.subprocess.Process | None = None
        try:
            process = await asyncio.wait_for(
                asyncio.create_subprocess_exec(
                    *command,
                    stdout=(
                        asyncio.subprocess.PIPE if capture else asyncio.subprocess.DEVNULL
                    ),
                    stderr=asyncio.subprocess.PIPE,
                ),
                timeout=self._subprocess_timeout_seconds,
            )
        except FileNotFoundError as exc:
            raise RenderError(
                f"Could not find binary '{command[0]}' while {context}. "
                "Is FFmpeg installed and on PATH?"
            ) from exc
        except asyncio.TimeoutError as exc:
            raise RenderExecutionError(
                f"Timed out starting '{command[0]}' while {context}."
            ) from exc

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=self._subprocess_timeout_seconds,
            )
            if process.returncode != 0:
                stderr_text = (stderr_bytes or b"").decode("utf-8", errors="replace")[-2000:]
                raise RenderError(
                    f"FFmpeg failed while {context} (exit code {process.returncode}): "
                    f"{stderr_text}"
                )
            return (stdout_bytes or b"").decode("utf-8", errors="replace")
        except asyncio.TimeoutError as exc:
            raise RenderExecutionError(
                f"Timed out after {self._subprocess_timeout_seconds:.0f}s while {context}."
            ) from exc
        except asyncio.CancelledError:
            await asyncio.shield(self._stop_process(process))
            raise
        finally:
            if process.returncode is None:
                await asyncio.shield(self._stop_process(process))

    async def _stop_process(self, process: asyncio.subprocess.Process) -> None:
        """Terminate a child process and reap it so no zombie PID survives."""
        if process.returncode is not None:
            return
        try:
            process.terminate()
        except ProcessLookupError:
            return

        await asyncio.sleep(0.1)
        if process.returncode is None:
            try:
                await asyncio.wait_for(process.wait(), timeout=self._termination_grace_seconds)
            except asyncio.TimeoutError:
                try:
                    process.kill()
                except ProcessLookupError:
                    return

        try:
            await asyncio.wait_for(process.communicate(), timeout=self._termination_grace_seconds)
        except asyncio.TimeoutError:
            if process.returncode is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    return
            await process.communicate()
