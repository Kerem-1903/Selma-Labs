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
from core.domain.exceptions import RenderError
from core.domain.ports.render_port import RenderPort
from core.domain.value_objects.render_result import RenderResult


class FfmpegRenderProvider(RenderPort):
    """Renders a Timeline into an MP4 file using local FFmpeg/ffprobe
    binaries."""

    def __init__(
        self,
        ffmpeg_binary: str = "ffmpeg",
        ffprobe_binary: str = "ffprobe",
        output_width: int = 1080,
        output_height: int = 1920,
        fps: int = 30,
    ) -> None:
        self._ffmpeg = ffmpeg_binary
        self._ffprobe = ffprobe_binary
        self._width = output_width
        self._height = output_height
        self._fps = fps

    async def render(self, timeline: Timeline, narration_audio_path: str) -> RenderResult:
        if not timeline.clips:
            raise RenderError(f"Cannot render Timeline '{timeline.id}': it has no clips.")

        if not Path(narration_audio_path).is_file():
            raise RenderError(
                f"Narration audio file not found at '{narration_audio_path}'."
            )

        work_dir = Path(tempfile.mkdtemp(prefix="selma-render-"))
        try:
            segment_paths = await self._normalize_segments(timeline, work_dir)
            concatenated_path = await self._concatenate(segment_paths, work_dir)
            final_path = self._final_output_path()
            await self._mux_audio(concatenated_path, narration_audio_path, final_path)
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
            await self._run(
                [
                    self._ffmpeg, "-y",
                    "-i", clip.asset.local_path,
                    "-t", str(duration),
                    "-vf",
                    (
                        f"scale={self._width}:{self._height}:"
                        "force_original_aspect_ratio=decrease,"
                        f"pad={self._width}:{self._height}:(ow-iw)/2:(oh-ih)/2,setsar=1"
                    ),
                    "-r", str(self._fps),
                    "-an",
                    "-c:v", "libx264",
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

    async def _mux_audio(self, video_path: Path, audio_path: str, output_path: Path) -> None:
        await self._run(
            [
                self._ffmpeg, "-y",
                "-i", str(video_path),
                "-i", audio_path,
                "-map", "0:v", "-map", "1:a",
                "-c:v", "copy", "-c:a", "aac",
                "-shortest",
                str(output_path),
            ],
            context="muxing narration audio onto concatenated video",
        )

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
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE if capture else asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise RenderError(
                f"Could not find binary '{command[0]}' while {context}. "
                "Is FFmpeg installed and on PATH?"
            ) from exc

        stdout_bytes, stderr_bytes = await process.communicate()
        if process.returncode != 0:
            stderr_text = (stderr_bytes or b"").decode("utf-8", errors="replace")[-2000:]
            raise RenderError(
                f"FFmpeg failed while {context} (exit code {process.returncode}): "
                f"{stderr_text}"
            )
        return (stdout_bytes or b"").decode("utf-8", errors="replace")
