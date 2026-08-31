from __future__ import annotations

import shutil
import subprocess
from datetime import datetime, timezone

import pytest

from core.application.services.video_assembler_service import VideoAssemblerService
from core.domain.entities.shot_motion_clip import ShotMotionClip
from core.domain.exceptions import VideoAssemblyError
from core.domain.value_objects.render_profile import RenderProfile
from infrastructure.storage.local_fs_storage import LocalFsStorage


def _clip(identifier: str, storage_key: str, *, approved: bool) -> ShotMotionClip:
    value = ShotMotionClip(
        id=identifier,
        shot_contract_id=f"shot-{identifier}",
        storyboard_id=f"board-{identifier}",
        storyboard_frame_id=f"frame-{identifier}",
        candidate_id=f"candidate-{identifier}",
        source_image_storage_key=f"storyboards/{identifier}/frame.png",
        storage_key=storage_key,
        content_type="video/mp4",
        provider="fake:i2v",
        provider_asset_id=f"provider-{identifier}",
        width=320,
        height=240,
        duration_seconds=0.5,
        fps=8,
        created_at=datetime.now(timezone.utc),
        render_profile="DRAFT",
    )
    return value.approve() if approved else value


@pytest.mark.asyncio
async def test_pending_clip_cannot_reach_ffmpeg(tmp_path):
    storage = LocalFsStorage(str(tmp_path))
    service = VideoAssemblerService(storage=storage)

    with pytest.raises(VideoAssemblyError, match="Only approved"):
        await service.assemble_sequence(
            clips=[_clip("one", "motion/one.mp4", approved=False)],
            output_storage_key="pilot/output.mp4",
        )


@pytest.mark.asyncio
@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is unavailable")
async def test_real_ffmpeg_normalizes_and_assembles_different_clips(tmp_path):
    storage = LocalFsStorage(str(tmp_path / "storage"))
    clips = []
    for index, (size, rate, color) in enumerate(
        (("320x240", "8", "red"), ("640x360", "12", "blue")), start=1
    ):
        source = tmp_path / f"source-{index}.mp4"
        subprocess.run(
            [
                "ffmpeg", "-nostdin", "-y", "-f", "lavfi", "-i",
                f"color=c={color}:s={size}:r={rate}:d=0.5",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source),
            ],
            check=True,
            capture_output=True,
        )
        key = f"motion/source-{index}.mp4"
        await storage.save(key, source.read_bytes(), "video/mp4")
        clips.append(_clip(str(index), key, approved=True))

    result = await VideoAssemblerService(storage=storage).assemble_sequence(
        clips=clips,
        output_storage_key="pilot/episode-zero.mp4",
        profile=RenderProfile.DRAFT,
    )

    data = await storage.load(result.storage_key)
    assert data[4:8] == b"ftyp"
    assert result.clip_ids == ("1", "2")
    assert result.width == 512
    assert result.height == 288
    assert result.duration_seconds == 1.0
