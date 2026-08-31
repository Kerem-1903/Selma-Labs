from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path, PurePosixPath

from core.domain.entities.shot_motion_clip import MotionClipStatus, ShotMotionClip
from core.domain.exceptions import VideoAssemblyError
from core.domain.ports.storage_port import StoragePort
from core.domain.value_objects.assembled_video import AssembledVideo
from core.domain.value_objects.render_profile import RenderProfile


class VideoAssemblerService:
    """Normalize and concatenate only human-approved, storage-backed clips."""

    def __init__(
        self,
        *,
        storage: StoragePort,
        ffmpeg_binary: str = "ffmpeg",
        timeout_seconds: float = 300.0,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("FFmpeg timeout must be greater than zero.")
        self._storage = storage
        self._ffmpeg_binary = ffmpeg_binary
        self._timeout_seconds = timeout_seconds

    async def assemble_sequence(
        self,
        *,
        clips: list[ShotMotionClip],
        output_storage_key: str,
        profile: RenderProfile = RenderProfile.FINAL,
    ) -> AssembledVideo:
        if not clips:
            raise ValueError("No motion clips were provided for assembly.")
        output_path = PurePosixPath(output_storage_key.replace("\\", "/"))
        if (
            output_path.is_absolute()
            or ".." in output_path.parts
            or ":" in output_storage_key
            or output_path.suffix.casefold() != ".mp4"
        ):
            raise ValueError("Assembly output must be a portable .mp4 storage key.")
        pending = [clip.id for clip in clips if clip.status != MotionClipStatus.APPROVED]
        if pending:
            raise VideoAssemblyError(
                "Only approved motion clips may be assembled; blocked: "
                + ", ".join(pending)
            )
        missing = [clip.storage_key for clip in clips if not await self._storage.exists(clip.storage_key)]
        if missing:
            raise VideoAssemblyError(
                "Motion clip assets were not found: " + ", ".join(missing)
            )
        if shutil.which(self._ffmpeg_binary) is None and not Path(self._ffmpeg_binary).is_file():
            raise VideoAssemblyError(f"FFmpeg executable was not found: {self._ffmpeg_binary}")

        settings = profile.settings
        crf = {
            RenderProfile.DRAFT: "28",
            RenderProfile.BALANCED: "22",
            RenderProfile.FINAL: "18",
        }[profile]
        with tempfile.TemporaryDirectory(prefix="selma-assembler-") as temp_name:
            temp = Path(temp_name)
            normalized: list[Path] = []
            for index, clip in enumerate(clips):
                source = temp / f"source-{index:04d}.bin"
                source.write_bytes(await self._storage.load(clip.storage_key))
                target = temp / f"normalized-{index:04d}.mp4"
                await self._run_ffmpeg(
                    "-nostdin",
                    "-y",
                    "-i",
                    str(source),
                    "-an",
                    "-vf",
                    (
                        f"scale={settings.width}:{settings.height}:"
                        "force_original_aspect_ratio=decrease,"
                        f"pad={settings.width}:{settings.height}:"
                        "(ow-iw)/2:(oh-ih)/2:color=black,"
                        f"fps={settings.fps:g}"
                    ),
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-crf",
                    crf,
                    "-pix_fmt",
                    "yuv420p",
                    "-movflags",
                    "+faststart",
                    str(target),
                )
                normalized.append(target)

            concat_list = temp / "concat-list.txt"
            concat_list.write_text(
                "".join(f"file '{path.as_posix()}'\n" for path in normalized),
                encoding="utf-8",
            )
            assembled_path = temp / "assembled.mp4"
            await self._run_ffmpeg(
                "-nostdin",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_list),
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                str(assembled_path),
            )
            output_bytes = assembled_path.read_bytes()

        if len(output_bytes) < 12 or output_bytes[4:8] != b"ftyp":
            raise VideoAssemblyError("FFmpeg did not produce a valid MP4 output.")
        stored = await self._storage.save(
            output_storage_key, output_bytes, "video/mp4"
        )
        if stored.key != output_storage_key:
            raise VideoAssemblyError("Storage adapter returned a different assembly key.")
        return AssembledVideo(
            storage_key=output_storage_key,
            content_type="video/mp4",
            clip_ids=tuple(clip.id for clip in clips),
            profile=profile,
            width=settings.width,
            height=settings.height,
            fps=settings.fps,
            duration_seconds=sum(clip.duration_seconds for clip in clips),
            size_bytes=len(output_bytes),
        )

    async def _run_ffmpeg(self, *arguments: str) -> None:
        process = await asyncio.create_subprocess_exec(
            self._ffmpeg_binary,
            *arguments,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr = await asyncio.wait_for(
                process.communicate(), timeout=self._timeout_seconds
            )
        except asyncio.TimeoutError as error:
            process.kill()
            await process.communicate()
            raise VideoAssemblyError(
                f"FFmpeg exceeded the {self._timeout_seconds:g}s timeout."
            ) from error
        if process.returncode != 0:
            detail = stderr.decode("utf-8", errors="replace")[-2000:]
            raise VideoAssemblyError(f"FFmpeg assembly failed: {detail}")
