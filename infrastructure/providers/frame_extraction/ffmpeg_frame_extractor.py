import asyncio
import os
import tempfile
from pathlib import Path
from typing import List

import httpx

from core.domain.entities.media_asset import MediaAsset
from core.domain.exceptions import ProviderError
from core.domain.ports.frame_extraction_port import FrameExtractionPort


class FfmpegFrameExtractor(FrameExtractionPort):
    def __init__(
        self,
        ffmpeg_binary: str = "ffmpeg",
        max_width: int = 640,
        *,
        subprocess_timeout_seconds: float = 60.0,
        termination_grace_seconds: float = 5.0,
        thumbnail_timeout_seconds: float = 20.0,
        thumbnail_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if (
            subprocess_timeout_seconds <= 0
            or termination_grace_seconds <= 0
            or thumbnail_timeout_seconds <= 0
        ):
            raise ValueError("FFmpeg timeout values must be greater than zero.")
        self._ffmpeg_binary = ffmpeg_binary
        self._max_width = max_width
        self._subprocess_timeout_seconds = subprocess_timeout_seconds
        self._termination_grace_seconds = termination_grace_seconds
        self._thumbnail_timeout_seconds = thumbnail_timeout_seconds
        self._thumbnail_transport = thumbnail_transport

    async def extract_frames(self, asset: MediaAsset, count: int) -> List[bytes]:
        local_source = (
            str(Path(asset.local_path).resolve())
            if asset.local_path and Path(asset.local_path).is_file()
            else None
        )
        source = local_source or asset.original_url
        if not source or count <= 0:
            return []

        if asset.thumbnail_url and local_source is None:
            try:
                return [await self._download_thumbnail(asset.thumbnail_url)]
            except ProviderError:
                # A catalog thumbnail is an optimization. Preserve the video
                # extraction fallback when its CDN is temporarily unavailable.
                pass

        with tempfile.TemporaryDirectory() as temp_dir:
            out_pattern = os.path.join(temp_dir, "frame_%03d.jpg")
            duration = asset.duration_seconds if asset.duration_seconds and asset.duration_seconds > 0 else 10.0
            sample_rate = max(0.01, count / duration)

            cmd = [
                self._ffmpeg_binary, "-y",
                "-i", source,
                "-vf", f"fps={sample_rate:.6f},scale={self._max_width}:-2",
                "-frames:v", str(count),
                "-f", "image2",
                out_pattern
            ]

            _, stderr = await self._run(cmd)

            frames = []
            for i in range(1, count + 1):
                frame_path = os.path.join(temp_dir, f"frame_{i:03d}.jpg")
                if os.path.exists(frame_path):
                    with open(frame_path, "rb") as f:
                        frames.append(f.read())

            return frames

    async def _download_thumbnail(self, url: str) -> bytes:
        try:
            async with httpx.AsyncClient(
                timeout=self._thumbnail_timeout_seconds,
                follow_redirects=True,
                transport=self._thumbnail_transport,
            ) as client:
                response = await client.get(url)
                response.raise_for_status()
        except (httpx.HTTPError, httpx.TimeoutException) as error:
            raise ProviderError(f"Could not download visual thumbnail: {error}") from error
        if not response.content:
            raise ProviderError("Visual thumbnail download returned empty content.")
        return response.content

    async def _run(self, command: list[str]) -> tuple[bytes, bytes]:
        process: asyncio.subprocess.Process | None = None
        try:
            process = await asyncio.wait_for(
                asyncio.create_subprocess_exec(
                    *command,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE,
                ),
                timeout=self._subprocess_timeout_seconds,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=self._subprocess_timeout_seconds
            )
            if process.returncode != 0:
                error = (stderr or b"").decode("utf-8", errors="replace")[-1000:]
                raise ProviderError(f"FFmpeg frame extraction failed: {error}")
            return stdout or b"", stderr or b""
        except FileNotFoundError as error:
            raise ProviderError(
                f"Could not find FFmpeg binary '{self._ffmpeg_binary}'."
            ) from error
        except asyncio.TimeoutError as error:
            raise ProviderError("FFmpeg frame extraction timed out.") from error
        except asyncio.CancelledError:
            if process is not None:
                await asyncio.shield(self._stop_process(process))
            raise
        finally:
            if process is not None and process.returncode is None:
                await asyncio.shield(self._stop_process(process))

    async def _stop_process(self, process: asyncio.subprocess.Process) -> None:
        if process.returncode is not None:
            return
        try:
            process.terminate()
        except ProcessLookupError:
            return
        await asyncio.sleep(0.1)
        if process.returncode is None:
            try:
                await asyncio.wait_for(process.wait(), self._termination_grace_seconds)
            except asyncio.TimeoutError:
                process.kill()
        await process.communicate()
