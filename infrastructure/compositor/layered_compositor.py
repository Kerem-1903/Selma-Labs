from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path, PurePosixPath

from core.domain.exceptions import VideoAssemblyError
from core.domain.ports.scene_compositor_port import SceneCompositorPort
from core.domain.ports.storage_port import StoragePort
from infrastructure.storage.local_fs_storage import LocalFsStorage


class LayeredCompositor(SceneCompositorPort):
    """Compose a background, character clip, and dialogue track with FFmpeg."""

    def __init__(
        self,
        output_dir: str = "cache/compositor",
        *,
        storage: StoragePort | None = None,
        ffmpeg_binary: str = "ffmpeg",
        timeout_seconds: float = 300.0,
        width: int = 1080,
        height: int = 1920,
        fps: int = 24,
    ) -> None:
        if not ffmpeg_binary.strip():
            raise ValueError("FFmpeg binary must not be empty.")
        if timeout_seconds <= 0 or width <= 0 or height <= 0 or fps <= 0:
            raise ValueError("Compositor timing and dimensions must be positive.")
        self._storage = storage or LocalFsStorage(output_dir)
        self._ffmpeg = ffmpeg_binary
        self._timeout_seconds = timeout_seconds
        self._width = width
        self._height = height
        self._fps = fps

    async def compose_scene(
        self,
        background_image_path: str,
        character_video_path: str,
        audio_path: str,
        output_video_path: str,
    ) -> str:
        for key, label in (
            (background_image_path, "background"),
            (character_video_path, "character video"),
            (audio_path, "audio"),
            (output_video_path, "output"),
        ):
            self._validate_key(key, label)
        if PurePosixPath(output_video_path).suffix.casefold() != ".mp4":
            raise VideoAssemblyError("Layered compositor output must use the .mp4 suffix.")
        for key in (background_image_path, character_video_path, audio_path):
            if not await self._storage.exists(key):
                raise VideoAssemblyError(f"Compositor input '{key}' was not found.")

        background = await self._storage.load(background_image_path)
        character = await self._storage.load(character_video_path)
        audio = await self._storage.load(audio_path)
        if not background or not character or not audio:
            raise VideoAssemblyError("Compositor inputs must not be empty.")

        with tempfile.TemporaryDirectory(prefix="selma-composite-") as temp_dir:
            root = Path(temp_dir)
            background_file = root / f"background{self._safe_suffix(background_image_path, '.png')}"
            character_file = root / f"character{self._safe_suffix(character_video_path, '.mp4')}"
            audio_file = root / f"dialogue{self._safe_suffix(audio_path, '.wav')}"
            output_file = root / "scene.mp4"
            await asyncio.gather(
                asyncio.to_thread(background_file.write_bytes, background),
                asyncio.to_thread(character_file.write_bytes, character),
                asyncio.to_thread(audio_file.write_bytes, audio),
            )
            await self._run_ffmpeg(background_file, character_file, audio_file, output_file)
            try:
                rendered = await asyncio.to_thread(output_file.read_bytes)
            except OSError as error:
                raise VideoAssemblyError("FFmpeg did not create the composited scene.") from error
        if len(rendered) < 12 or rendered[4:8] != b"ftyp":
            raise VideoAssemblyError("Compositor produced an invalid MP4 file.")
        stored = await self._storage.save(output_video_path, rendered, "video/mp4")
        if stored.key != output_video_path:
            raise VideoAssemblyError("Storage adapter changed the compositor output key.")
        return stored.key

    async def _run_ffmpeg(
        self,
        background: Path,
        character: Path,
        audio: Path,
        output: Path,
    ) -> None:
        filter_graph = (
            f"[0:v]scale={self._width}:{self._height}:force_original_aspect_ratio=increase,"
            f"crop={self._width}:{self._height}[bg];"
            f"[1:v]fps={self._fps},scale={self._width}:{self._height}:"
            "force_original_aspect_ratio=decrease[character];"
            "[bg][character]overlay=(W-w)/2:(H-h)/2:shortest=1[video]"
        )
        command = (
            self._ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-loop",
            "1",
            "-i",
            str(background),
            "-i",
            str(character),
            "-i",
            str(audio),
            "-filter_complex",
            filter_graph,
            "-map",
            "[video]",
            "-map",
            "2:a:0",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(self._fps),
            "-c:a",
            "aac",
            "-shortest",
            "-movflags",
            "+faststart",
            str(output),
        )
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as error:
            raise VideoAssemblyError(f"FFmpeg executable was not found: {self._ffmpeg}") from error
        try:
            _, stderr = await asyncio.wait_for(
                process.communicate(), timeout=self._timeout_seconds
            )
        except asyncio.TimeoutError as error:
            process.kill()
            await process.communicate()
            raise VideoAssemblyError(
                f"Layered composition exceeded {self._timeout_seconds:g} seconds."
            ) from error
        if process.returncode != 0:
            detail = stderr.decode("utf-8", errors="replace")[-2000:].strip()
            raise VideoAssemblyError(f"FFmpeg layered composition failed: {detail}")

    @staticmethod
    def _validate_key(value: str, label: str) -> None:
        normalized = value.replace("\\", "/")
        path = PurePosixPath(normalized)
        if not normalized.strip() or path.is_absolute() or ".." in path.parts or ":" in value:
            raise VideoAssemblyError(f"Compositor {label} must be a portable storage key.")

    @staticmethod
    def _safe_suffix(key: str, fallback: str) -> str:
        suffix = PurePosixPath(key.replace("\\", "/")).suffix.casefold()
        if not suffix or len(suffix) > 10 or not suffix[1:].isalnum():
            return fallback
        return suffix
