import asyncio
import os
import tempfile
from typing import List

from core.domain.entities.media_asset import MediaAsset
from core.domain.ports.frame_extraction_port import FrameExtractionPort


class FfmpegFrameExtractor(FrameExtractionPort):
    async def extract_frames(self, asset: MediaAsset, count: int) -> List[bytes]:
        if not asset.original_url or count <= 0:
            return []

        with tempfile.TemporaryDirectory() as temp_dir:
            out_pattern = os.path.join(temp_dir, "frame_%03d.jpg")
            duration = asset.duration_seconds if asset.duration_seconds and asset.duration_seconds > 0 else 10.0
            fps_val = max(0.1, count / duration)

            cmd = [
                "ffmpeg", "-y", "-i", asset.original_url,
                "-vf", f"fps={fps_val}",
                "-vframes", str(count),
                "-f", "image2",
                out_pattern
            ]

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            await proc.communicate()

            frames = []
            for i in range(1, count + 1):
                frame_path = os.path.join(temp_dir, f"frame_{i:03d}.jpg")
                if os.path.exists(frame_path):
                    with open(frame_path, "rb") as f:
                        frames.append(f.read())

            return frames
