from __future__ import annotations

import pytest

from infrastructure.providers.lipsync.liveportrait_adapter import LivePortraitAdapter
from infrastructure.storage.local_fs_storage import LocalFsStorage


@pytest.mark.asyncio
async def test_mock_liveportrait_persists_valid_passthrough_without_claiming_real_sync(tmp_path):
    storage = LocalFsStorage(str(tmp_path))
    video = b"\x00\x00\x00\x18ftypisom0000"
    await storage.save("motion/shot.mp4", video, "video/mp4")
    await storage.save("audio/dialogue.wav", b"RIFFaudio", "audio/wav")
    adapter = LivePortraitAdapter(storage=storage)

    output = await adapter.generate_lipsync_clip(
        "motion/shot.mp4", "audio/dialogue.wav", "lipsync/shot.mp4"
    )

    assert adapter.name == "liveportrait:mock-passthrough"
    assert output == "lipsync/shot.mp4"
    assert await storage.load(output) == video
