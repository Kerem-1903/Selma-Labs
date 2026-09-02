from __future__ import annotations

import asyncio
import json
from pathlib import Path

from core.domain.exceptions import UploadPreparationError
from core.domain.ports.media_inspection_port import MediaInspectionPort
from core.domain.value_objects.media_inspection import MediaInspection


class FfprobeMediaInspectionProvider(MediaInspectionPort):
    def __init__(
        self, ffmpeg_binary: str = "ffmpeg", ffprobe_binary: str = "ffprobe"
    ) -> None:
        self._ffmpeg = ffmpeg_binary
        self._ffprobe = ffprobe_binary

    async def inspect(self, video_path: str) -> MediaInspection:
        path = Path(video_path)
        if not path.is_file() or path.stat().st_size <= 0:
            raise UploadPreparationError(
                f"Rendered video is missing or empty at '{video_path}'."
            )
        stdout = await self._run(
            [
                self._ffprobe,
                "-v", "error",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                str(path),
            ],
            context="inspecting upload video",
        )
        try:
            data = json.loads(stdout)
            streams = data["streams"]
            video = next(item for item in streams if item.get("codec_type") == "video")
            audio = next(
                (item for item in streams if item.get("codec_type") == "audio"),
                None,
            )
            media_format = data["format"]
            return MediaInspection(
                format_names=tuple(
                    name.strip()
                    for name in media_format.get("format_name", "").split(",")
                    if name.strip()
                ),
                duration_seconds=float(media_format.get("duration") or video.get("duration")),
                width=int(video["width"]),
                height=int(video["height"]),
                fps=self._parse_rate(video.get("avg_frame_rate") or "0/1"),
                video_codec=str(video.get("codec_name") or ""),
                pixel_format=(str(video.get("pix_fmt")) if video.get("pix_fmt") else None),
                audio_codec=str(audio.get("codec_name") or "") if audio else None,
                audio_sample_rate=(
                    int(audio["sample_rate"])
                    if audio and audio.get("sample_rate")
                    else None
                ),
                audio_bitrate=(
                    int(audio["bit_rate"])
                    if audio and audio.get("bit_rate")
                    else None
                ),
                file_size_bytes=int(media_format.get("size") or path.stat().st_size),
                color_primaries=(
                    str(video.get("color_primaries"))
                    if video.get("color_primaries")
                    else None
                ),
                color_transfer=(
                    str(video.get("color_transfer"))
                    if video.get("color_transfer")
                    else None
                ),
                color_space=(
                    str(video.get("color_space"))
                    if video.get("color_space")
                    else None
                ),
                color_range=(
                    str(video.get("color_range"))
                    if video.get("color_range")
                    else None
                ),
                field_order=(
                    str(video.get("field_order"))
                    if video.get("field_order")
                    else None
                ),
                audio_channels=(
                    int(audio["channels"])
                    if audio and audio.get("channels") is not None
                    else None
                ),
            )
        except (KeyError, TypeError, ValueError, StopIteration, json.JSONDecodeError) as exc:
            raise UploadPreparationError(
                f"Could not parse media inspection for '{video_path}': {exc}"
            ) from exc

    async def extract_frame(
        self, video_path: str, output_path: str, timestamp_seconds: float
    ) -> None:
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        await self._run(
            [
                self._ffmpeg,
                "-y",
                "-ss", f"{max(timestamp_seconds, 0.0):.3f}",
                "-i", video_path,
                "-frames:v", "1",
                "-q:v", "2",
                str(destination),
            ],
            context="extracting thumbnail selection frame",
        )
        if not destination.is_file() or destination.stat().st_size <= 0:
            raise UploadPreparationError(
                f"FFmpeg did not create thumbnail frame at '{output_path}'."
            )

    async def _run(self, command: list[str], *, context: str) -> str:
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise UploadPreparationError(
                f"Could not find binary '{command[0]}' while {context}."
            ) from exc
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            error = (stderr or b"").decode("utf-8", errors="replace")[-2000:]
            raise UploadPreparationError(
                f"Media tool failed while {context}: {error}"
            )
        return (stdout or b"").decode("utf-8", errors="replace")

    @staticmethod
    def _parse_rate(value: str) -> float:
        numerator, denominator = value.split("/", 1)
        denominator_value = float(denominator)
        return float(numerator) / denominator_value if denominator_value else 0.0
