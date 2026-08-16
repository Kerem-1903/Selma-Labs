from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

from core.domain.exceptions import AudioMixError
from core.domain.ports.audio_mix_port import AudioMixPort
from core.domain.value_objects.audio_mix_result import AudioMixResult


class FfmpegAudioMixProvider(AudioMixPort):
    def __init__(self, ffmpeg_binary: str = "ffmpeg") -> None:
        self._ffmpeg = ffmpeg_binary

    async def mix(
        self,
        *,
        narration_path: str,
        music_path: str,
        duration_seconds: float,
    ) -> AudioMixResult:
        if not Path(narration_path).is_file() or not Path(music_path).is_file():
            raise AudioMixError("Narration and licensed music files must both exist.")
        file_descriptor, output_path = tempfile.mkstemp(
            prefix="selma-premium-mix-",
            suffix=".m4a",
        )
        os.close(file_descriptor)
        fade_out_start = max(0.0, duration_seconds - 1.2)
        filter_graph = (
            f"[1:a]atrim=0:{duration_seconds},volume=0.18,"
            f"afade=t=in:st=0:d=0.8,afade=t=out:st={fade_out_start}:d=1.2[music];"
            "[music][0:a]sidechaincompress=threshold=0.025:ratio=8:attack=20:"
            "release=450[ducked];[0:a][ducked]amix=inputs=2:duration=first:"
            "dropout_transition=2,loudnorm=I=-14:TP=-1.5:LRA=9[mix]"
        )
        command = [
            self._ffmpeg,
            "-y",
            "-i",
            narration_path,
            "-stream_loop",
            "-1",
            "-i",
            music_path,
            "-filter_complex",
            filter_graph,
            "-map",
            "[mix]",
            "-t",
            str(duration_seconds),
            "-c:a",
            "aac",
            "-b:a",
            "384k",
            "-ar",
            "48000",
            "-ac",
            "2",
            output_path,
        ]
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise AudioMixError(f"FFmpeg binary not found: {self._ffmpeg}") from exc
        _, stderr = await process.communicate()
        if process.returncode != 0 or not Path(output_path).is_file():
            Path(output_path).unlink(missing_ok=True)
            message = (stderr or b"").decode("utf-8", errors="replace")[-1500:]
            raise AudioMixError(f"FFmpeg premium audio mix failed: {message}")
        return AudioMixResult(output_path=output_path)
