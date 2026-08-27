import logging
import asyncio
import os
import uuid
from typing import List

logger = logging.getLogger(__name__)

class ThumbnailGeneratorService:
    """
    Generates A/B thumbnails using FFmpeg to extract striking frames from the rendered video.
    """
    def __init__(self, ffmpeg_binary: str = "ffmpeg"):
        self.ffmpeg = ffmpeg_binary

    async def generate_ab_thumbnails(self, video_path: str, output_dir: str, texts: List[str]) -> List[str]:
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found for thumbnail extraction: {video_path}")

        os.makedirs(output_dir, exist_ok=True)
        thumbnail_paths = []

        timestamps = ["00:00:02.000", "00:00:08.000"]

        for i, (ts, text) in enumerate(zip(timestamps, texts)):
            if i >= 2: break
            out_path = os.path.join(output_dir, f"thumbnail_v{i+1}_{uuid.uuid4().hex[:8]}.jpg")

            cmd = [
                self.ffmpeg,
                "-y",
                "-ss", ts,
                "-i", video_path,
                "-vframes", "1",
                "-q:v", "2",
                out_path
            ]

            logger.info(f"Extracting thumbnail A/B variant {i+1} at {ts}")
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                logger.warning(f"Thumbnail generation failed: {stderr.decode()}")
            elif os.path.exists(out_path):
                thumbnail_paths.append(out_path)

        return thumbnail_paths
