"""FFmpeg adapter for black/freeze/silence and EBU R128 measurements."""
from __future__ import annotations

import asyncio
import re
from pathlib import Path

from core.domain.exceptions import UploadPreparationError
from core.domain.ports.media_quality_analysis_port import MediaQualityAnalysisPort
from core.domain.value_objects.media_quality_signals import MediaQualitySignals


class FfmpegMediaQualityAnalysisProvider(MediaQualityAnalysisPort):
    def __init__(self, ffmpeg_binary: str = "ffmpeg") -> None:
        self._ffmpeg = ffmpeg_binary

    async def analyze(self, video_path: str) -> MediaQualitySignals:
        path = Path(video_path)
        if not path.is_file() or path.stat().st_size <= 0:
            raise UploadPreparationError(
                f"Rendered video is missing or empty at '{video_path}'."
            )
        loudness_log = await self._run(
            [
                self._ffmpeg, "-hide_banner", "-nostats", "-i", str(path),
                "-af", "loudnorm=I=-14:TP=-1.5:LRA=9:print_format=json",
                "-vn", "-f", "null", "-",
            ],
            context="measuring adaptive loudness",
        )
        integrated_lufs = self._json_metric(loudness_log, "input_i")
        true_peak_dbfs = self._json_metric(loudness_log, "input_tp")
        loudness_range = self._json_metric(loudness_log, "input_lra")
        measured_threshold = self._json_metric(loudness_log, "input_thresh")
        silence_threshold = max(-55.0, min(-25.0, measured_threshold or -45.0))
        video_log, audio_log = await asyncio.gather(
            self._run(
                [
                    self._ffmpeg, "-hide_banner", "-nostats", "-i", str(path),
                    "-vf", (
                        "blackdetect=d=0.10:pic_th=0.98,"
                        "freezedetect=n=-50dB:d=1.0,scdet=t=8"
                    ),
                    "-an", "-f", "null", "-",
                ],
                context="analyzing rendered video frames",
            ),
            self._run(
                [
                    self._ffmpeg, "-hide_banner", "-nostats", "-i", str(path),
                    "-af", f"silencedetect=n={silence_threshold:.2f}dB:d=0.5,ebur128=peak=true",
                    "-vn", "-f", "null", "-",
                ],
                context="analyzing rendered audio",
            ),
        )
        black_intervals = [
            (float(start), float(duration))
            for start, duration in re.findall(
                r"black_start:([\d.]+).*?black_duration:([\d.]+)",
                video_log,
            )
        ]
        freeze_durations = [
            float(value)
            for value in re.findall(r"freeze_duration:\s*([\d.]+)", video_log)
        ]
        silence_durations = [
            float(value)
            for value in re.findall(r"silence_duration:\s*([\d.]+)", audio_log)
        ]
        loudness_values = re.findall(r"\bI:\s*(-?[\d.]+)\s+LUFS", audio_log)
        peak_values = re.findall(r"\bPeak:\s*(-?[\d.]+)\s+dBFS", audio_log)
        silence_starts = [
            float(value) for value in re.findall(r"silence_start:\s*([\d.]+)", audio_log)
        ]
        silence_ends = [
            float(value) for value in re.findall(r"silence_end:\s*([\d.]+)", audio_log)
        ]
        leading_silence = (
            silence_ends[0]
            if silence_starts and silence_starts[0] <= 0.02 and silence_ends
            else 0.0
        )
        final_peak = (
            true_peak_dbfs
            if true_peak_dbfs is not None
            else float(peak_values[-1]) if peak_values else None
        )
        opening_black = max(
            (duration for start, duration in black_intervals if start <= 0.05),
            default=0.0,
        )
        scene_changes = tuple(
            dict.fromkeys(
                round(float(value), 4)
                for value in re.findall(r"lavfi\.scd\.time:\s*([\d.]+)", video_log)
            )
        )
        duration_seconds = self._duration_seconds(video_log)
        boundaries = (0.0, *scene_changes, duration_seconds)
        shot_durations = [
            max(0.0, right - left)
            for left, right in zip(boundaries, boundaries[1:])
        ]
        return MediaQualitySignals(
            opening_black_seconds=round(opening_black, 4),
            total_black_seconds=round(sum(duration for _, duration in black_intervals), 4),
            maximum_freeze_seconds=round(max(freeze_durations, default=0.0), 4),
            maximum_silence_seconds=round(max(silence_durations, default=0.0), 4),
            integrated_lufs=(
                integrated_lufs
                if integrated_lufs is not None
                else float(loudness_values[-1]) if loudness_values else None
            ),
            true_peak_dbfs=final_peak,
            loudness_range_lu=loudness_range,
            adaptive_silence_threshold_db=round(silence_threshold, 2),
            leading_silence_seconds=round(leading_silence, 4),
            trailing_silence_seconds=0.0,
            clipping_detected=(final_peak is not None and final_peak > -0.1),
            scene_change_timestamps_seconds=scene_changes,
            maximum_visual_stasis_seconds=round(max(shot_durations, default=0.0), 4),
            average_shot_duration_seconds=round(
                sum(shot_durations) / len(shot_durations)
                if shot_durations else 0.0,
                4,
            ),
        )

    @staticmethod
    def _json_metric(log: str, name: str) -> float | None:
        match = re.search(rf'"{re.escape(name)}"\s*:\s*"?(-?(?:\d+(?:\.\d+)?|inf))', log)
        if match is None or "inf" in match.group(1).casefold():
            return None
        return float(match.group(1))

    @staticmethod
    def _duration_seconds(log: str) -> float:
        match = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", log)
        if match is None:
            return 0.0
        hours, minutes, seconds = match.groups()
        return int(hours) * 3_600 + int(minutes) * 60 + float(seconds)

    async def _run(self, command: list[str], *, context: str) -> str:
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as error:
            raise UploadPreparationError(
                f"Could not find FFmpeg binary '{self._ffmpeg}' while {context}."
            ) from error
        _, stderr = await process.communicate()
        log = (stderr or b"").decode("utf-8", errors="replace")
        if process.returncode != 0:
            raise UploadPreparationError(
                f"FFmpeg failed while {context}: {log[-2000:]}"
            )
        return log
