from __future__ import annotations

import pytest

from core.application.services.video_mastering_service import VideoMasteringService


async def test_mastering_refuses_a_missing_input_before_touching_ffmpeg(tmp_path):
    """Regression: a redundant in-function ``import os`` made ``os`` a local
    name for the whole method, so the first existence check raised
    ``UnboundLocalError`` on every call -- the service could never run at all.
    The guard must fire as a ``FileNotFoundError`` before FFmpeg is considered.
    """
    service = VideoMasteringService(ffmpeg_path="ffmpeg")

    with pytest.raises(FileNotFoundError):
        await service.apply_cinematic_mastering(
            input_video_path=str(tmp_path / "missing.mp4"),
            output_dir=str(tmp_path),
        )
