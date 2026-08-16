from __future__ import annotations

import asyncio
import shutil

import pytest

from infrastructure.providers.render.ffprobe_media_inspection_provider import (
    FfprobeMediaInspectionProvider,
)

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None

pytestmark = pytest.mark.skipif(
    not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed on PATH"
)


@pytest.mark.asyncio
async def test_inspects_video_and_extracts_thumbnail_frame(tmp_path):
    video = tmp_path / "short.mp4"
    frame = tmp_path / "frame.jpg"
    process = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=blue:s=180x320:d=0.6",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=0.6",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-x264-params", "colorprim=bt709:transfer=bt709:colormatrix=bt709:range=limited",
        "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
        "-c:a", "aac", "-ar", "48000", "-ac", "2", "-shortest",
        str(video),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await process.communicate()
    assert process.returncode == 0
    provider = FfprobeMediaInspectionProvider()

    inspection = await provider.inspect(str(video))
    await provider.extract_frame(str(video), str(frame), 0.2)

    assert inspection.width == 180
    assert inspection.height == 320
    assert inspection.video_codec == "h264"
    assert inspection.audio_codec == "aac"
    assert inspection.audio_sample_rate == 48000
    assert inspection.audio_channels == 2
    assert inspection.color_primaries == "bt709"
    assert inspection.color_transfer == "bt709"
    assert inspection.color_space == "bt709"
    assert inspection.field_order == "progressive"
    assert inspection.duration_seconds > 0
    assert frame.is_file()
    assert frame.stat().st_size > 0
