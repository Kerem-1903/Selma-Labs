from __future__ import annotations

import asyncio
import shutil
import subprocess
import wave

import pytest
from PIL import Image

from infrastructure.compositor.layered_compositor import LayeredCompositor
from infrastructure.storage.local_fs_storage import LocalFsStorage


@pytest.mark.asyncio
async def test_layered_compositor_creates_real_storage_backed_mp4(tmp_path):
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        pytest.skip("FFmpeg is not installed")
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    background = inputs / "background.png"
    character = inputs / "character.mp4"
    audio = inputs / "dialogue.wav"
    Image.new("RGB", (64, 64), (12, 18, 30)).save(background)
    await asyncio.to_thread(
        subprocess.run,
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=red:s=64x64:r=8:d=1",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(character),
        ],
        check=True,
    )
    with wave.open(str(audio), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b"\x00\x00" * 8000)

    storage = LocalFsStorage(str(tmp_path / "storage"))
    await storage.save("backgrounds/scene.png", background.read_bytes(), "image/png")
    await storage.save("motion/character.mp4", character.read_bytes(), "video/mp4")
    await storage.save("audio/dialogue.wav", audio.read_bytes(), "audio/wav")
    compositor = LayeredCompositor(
        storage=storage,
        ffmpeg_binary=ffmpeg,
        width=64,
        height=64,
        fps=8,
        timeout_seconds=30,
    )

    result = await compositor.compose_scene(
        "backgrounds/scene.png",
        "motion/character.mp4",
        "audio/dialogue.wav",
        "final/scene.mp4",
    )

    rendered = await storage.load(result)
    assert result == "final/scene.mp4"
    assert len(rendered) > 1000
    assert rendered[4:8] == b"ftyp"
