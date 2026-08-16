"""Mandatory technical quality gate for rendered Shorts outputs."""
from __future__ import annotations

from core.domain.exceptions import RenderExecutionError
from core.domain.value_objects.media_inspection import MediaInspection
from core.domain.value_objects.media_quality_signals import MediaQualitySignals


class PostRenderQualityService:
    """Reject render outputs that are structurally unsuitable for Shorts."""

    def validate(
        self,
        inspection: MediaInspection,
        *,
        expected_duration_seconds: float,
        expected_width: int,
        expected_height: int,
    ) -> None:
        """Enforce container, streams, portrait profile, and duration bounds."""
        if "mp4" not in inspection.format_names:
            raise RenderExecutionError("Rendered output is not an MP4 container.")
        if inspection.width != expected_width or inspection.height != expected_height:
            raise RenderExecutionError("Rendered output does not match the portrait profile.")
        if inspection.fps <= 0 or not inspection.video_codec:
            raise RenderExecutionError("Rendered output has no usable video stream.")
        if inspection.pixel_format != "yuv420p":
            raise RenderExecutionError("Rendered output is not using the yuv420p pixel format.")
        if (
            inspection.color_primaries != "bt709"
            or inspection.color_transfer != "bt709"
            or inspection.color_space != "bt709"
        ):
            raise RenderExecutionError("Rendered output is missing complete BT.709 color metadata.")
        if inspection.field_order != "progressive":
            raise RenderExecutionError("Rendered output is not progressive scan.")
        if not inspection.audio_codec or not inspection.audio_sample_rate:
            raise RenderExecutionError("Rendered output has no usable audio stream.")
        if inspection.audio_sample_rate != 48_000:
            raise RenderExecutionError("Rendered output audio is not 48 kHz.")
        if inspection.audio_channels != 2:
            raise RenderExecutionError("Rendered output audio is not stereo.")
        if (inspection.audio_bitrate or 0) < 224_000:
            raise RenderExecutionError(
                "Rendered output measured AAC bitrate is below 224 kbps."
            )
        if inspection.file_size_bytes < 1_024:
            raise RenderExecutionError("Rendered output is implausibly small.")
        if abs(inspection.duration_seconds - expected_duration_seconds) > 0.75:
            raise RenderExecutionError("Rendered output duration drift exceeds 750ms.")

    def validate_content(
        self,
        signals: MediaQualitySignals,
        *,
        expected_duration_seconds: float,
    ) -> None:
        """Reject perceptual failures that container inspection cannot see."""
        if signals.opening_black_seconds > 0.10:
            raise RenderExecutionError("Rendered output opens on a black frame sequence.")
        if signals.total_black_seconds > max(0.35, expected_duration_seconds * 0.03):
            raise RenderExecutionError("Rendered output contains excessive black frames.")
        if signals.maximum_freeze_seconds > 4.0:
            raise RenderExecutionError("Rendered output contains an excessive frozen sequence.")
        if signals.maximum_silence_seconds > 1.75:
            raise RenderExecutionError("Rendered output contains an excessive silence gap.")
        if signals.integrated_lufs is None:
            raise RenderExecutionError("Rendered output loudness could not be measured.")
        if not -17.0 <= signals.integrated_lufs <= -13.0:
            raise RenderExecutionError(
                "Rendered output loudness is outside the -17 to -13 LUFS gate."
            )
        if signals.true_peak_dbfs is None:
            raise RenderExecutionError("Rendered output true peak could not be measured.")
        if signals.true_peak_dbfs > -1.0:
            raise RenderExecutionError("Rendered output true peak exceeds -1.0 dBFS.")
        if signals.clipping_detected:
            raise RenderExecutionError("Rendered output contains clipped audio samples.")
        if signals.leading_silence_seconds > 0.25:
            raise RenderExecutionError("Rendered output starts with excessive silence.")
        if signals.trailing_silence_seconds > 0.50:
            raise RenderExecutionError("Rendered output ends with excessive silence.")
        if signals.loudness_range_lu is not None and signals.loudness_range_lu > 14.0:
            raise RenderExecutionError("Rendered output loudness range is too wide for mobile playback.")
