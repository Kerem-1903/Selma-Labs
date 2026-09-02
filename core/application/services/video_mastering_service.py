import asyncio
import logging
import os
import uuid
from typing import Optional

logger = logging.getLogger(__name__)

class VideoMasteringService:
    """
    Applies post-render cinematic quality enhancements.
    Features:
      - Color Grading: Enhances saturation, contrast, and applies slight sharpening.
      - Audio Mastering: Normalizes LUFS to YouTube standard (-14 LUFS) to ensure vocals pop.
    """

    def __init__(self, ffmpeg_path: str = "ffmpeg"):
        self.ffmpeg_path = ffmpeg_path

    async def apply_cinematic_mastering(
        self,
        input_video_path: str,
        output_dir: str,
        enhance_colors: bool = True,
        normalize_audio: bool = True,
    ) -> str:
        """
        Runs FFmpeg to master the video file.
        Returns the path to the newly mastered video.
        """
        if not os.path.exists(input_video_path):
            raise FileNotFoundError(f"Cannot master missing video: {input_video_path}")

        os.makedirs(output_dir, exist_ok=True)
        filename = f"mastered_{uuid.uuid4().hex[:8]}.mp4"
        output_video_path = os.path.join(output_dir, filename)

        # Base command
        cmd = [self.ffmpeg_path, "-y", "-i", input_video_path]

        # Video Filters (Color Grading & Sharpening)
        v_filter = ""
        if enhance_colors:
            v_filter = "eq=contrast=1.05:saturation=1.15,unsharp=3:3:1.0:3:3:0.0"
            cmd.extend(["-vf", v_filter])

        # Audio Filters (LUFS Normalization)
        a_filter = ""
        if normalize_audio:
            a_filter = "loudnorm=I=-14:LRA=11:TP=-1.0"
            cmd.extend(["-af", a_filter])

        # Encoding Settings
        cmd.extend([
            "-c:v", "libx264",
            "-crf", "18",
            "-preset", "fast",
            "-c:a", "aac",
            "-b:a", "192k",
            output_video_path
        ])

        import os
        kwargs = {}
        if os.name == "posix":
            kwargs["start_new_session"] = True

        logger.info(f"Applying Cinematic Mastering to {input_video_path}...")

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **kwargs
        )

        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=300)
        except asyncio.TimeoutError:
            if os.name == "posix":
                import signal
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
            else:
                process.terminate()
            raise RuntimeError("Cinematic Mastering failed due to FFmpeg timeout.")

        if process.returncode != 0:
            logger.error(f"FFmpeg Mastering failed: {stderr.decode()}")
            raise RuntimeError("Cinematic Mastering failed due to an FFmpeg error.")

        logger.info(f"Mastering successful: {output_video_path}")
        return output_video_path
