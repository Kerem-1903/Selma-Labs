from __future__ import annotations

from dataclasses import replace

import pytest

from core.application.services.post_render_quality_service import PostRenderQualityService
from core.domain.exceptions import RenderExecutionError
from core.domain.value_objects.media_quality_signals import MediaQualitySignals
from core.domain.value_objects.media_inspection import MediaInspection
from infrastructure.providers.render.ffmpeg_media_quality_analysis_provider import (
    FfmpegMediaQualityAnalysisProvider,
)


@pytest.mark.asyncio
async def test_ffmpeg_quality_analysis_parses_content_and_loudness(monkeypatch, tmp_path):
    video = tmp_path / "short.mp4"
    video.write_bytes(b"video")
    provider = FfmpegMediaQualityAnalysisProvider()

    async def fake_run(command, *, context):
        del context
        filter_value = command[command.index("-af") + 1] if "-af" in command else ""
        if "loudnorm=" in filter_value:
            return '{"input_i":"-15.10","input_tp":"-1.40","input_lra":"4.20","input_thresh":"-25.80"}'
        if "-vf" in command:
            return "black_start:0 black_end:0.08 black_duration:0.08\nfreeze_start:4 freeze_duration:1.25 freeze_end:5.25\n"
        return "silence_start:8 silence_end:8.9 silence_duration:0.9\nSummary:\n  I: -15.1 LUFS\n  Peak: -1.4 dBFS\n"

    monkeypatch.setattr(provider, "_run", fake_run)

    result = await provider.analyze(str(video))

    assert result.opening_black_seconds == 0.08
    assert result.maximum_freeze_seconds == 1.25
    assert result.maximum_silence_seconds == 0.9
    assert result.integrated_lufs == -15.1
    assert result.true_peak_dbfs == -1.4
    assert result.loudness_range_lu == 4.2
    assert result.adaptive_silence_threshold_db == -25.8


def test_post_render_content_gate_accepts_premium_signals():
    PostRenderQualityService().validate_content(
        MediaQualitySignals(0.0, 0.0, 1.0, 0.5, -15.0, -1.5),
        expected_duration_seconds=30.0,
    )


def _delivery_inspection() -> MediaInspection:
    return MediaInspection(
        format_names=("mp4",),
        duration_seconds=24.0,
        width=1080,
        height=1920,
        fps=30.0,
        video_codec="h264",
        pixel_format="yuv420p",
        audio_codec="aac",
        audio_sample_rate=48_000,
        audio_bitrate=320_000,
        file_size_bytes=8_000_000,
        color_primaries="bt709",
        color_transfer="bt709",
        color_space="bt709",
        color_range="tv",
        field_order="progressive",
        audio_channels=2,
    )


def test_post_render_structure_gate_accepts_master_delivery_profile():
    PostRenderQualityService().validate(
        _delivery_inspection(),
        expected_duration_seconds=24.0,
        expected_width=1080,
        expected_height=1920,
    )


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"pixel_format": "yuv444p"}, "yuv420p"),
        ({"color_transfer": None}, "BT.709"),
        ({"field_order": "tt"}, "progressive"),
        ({"audio_sample_rate": 44_100}, "48 kHz"),
        ({"audio_channels": 1}, "stereo"),
        ({"audio_bitrate": 192_000}, "bitrate"),
    ],
)
def test_post_render_structure_gate_blocks_unsafe_delivery(changes, message):
    with pytest.raises(RenderExecutionError, match=message):
        PostRenderQualityService().validate(
            replace(_delivery_inspection(), **changes),
            expected_duration_seconds=24.0,
            expected_width=1080,
            expected_height=1920,
        )


@pytest.mark.parametrize(
    ("signals", "message"),
    [
        (MediaQualitySignals(0.2, 0.2, 1.0, 0.5, -15.0, -1.5), "black"),
        (MediaQualitySignals(0.0, 0.0, 4.5, 0.5, -15.0, -1.5), "frozen"),
        (MediaQualitySignals(0.0, 0.0, 1.0, 2.0, -15.0, -1.5), "silence"),
        (MediaQualitySignals(0.0, 0.0, 1.0, 0.5, -19.0, -1.5), "loudness"),
        (MediaQualitySignals(0.0, 0.0, 1.0, 0.5, -15.0, -0.5), "true peak"),
    ],
)
def test_post_render_content_gate_rejects_perceptual_failures(signals, message):
    with pytest.raises(RenderExecutionError, match=message):
        PostRenderQualityService().validate_content(
            signals,
            expected_duration_seconds=30.0,
        )
