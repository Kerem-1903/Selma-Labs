import httpx
from pathlib import Path

from core.domain.entities.media_asset import MediaAsset
from infrastructure.providers.frame_extraction.ffmpeg_frame_extractor import (
    FfmpegFrameExtractor,
)


async def test_frame_extractor_prefers_fast_catalog_thumbnail():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, content=b"jpeg-thumbnail")
    )
    extractor = FfmpegFrameExtractor(
        ffmpeg_binary="binary-must-not-be-called",
        thumbnail_transport=transport,
    )
    asset = MediaAsset(
        id="pexels:1",
        provider="pexels",
        original_url="https://video.example/large.mp4",
        thumbnail_url="https://images.example/thumb.jpeg",
    )

    frames = await extractor.extract_frames(asset, 3)

    assert frames == [b"jpeg-thumbnail"]


async def test_frame_extractor_samples_multiple_frames_from_downloaded_clip(tmp_path):
    clip = tmp_path / "clip.mp4"
    clip.touch()
    extractor = FfmpegFrameExtractor(ffmpeg_binary="fake-ffmpeg")
    commands: list[list[str]] = []

    async def fake_run(command):
        commands.append(command)
        pattern = Path(command[-1])
        for index in range(1, 4):
            Path(str(pattern).replace("%03d", f"{index:03d}")).write_bytes(
                f"frame-{index}".encode()
            )
        return b"", b""

    extractor._run = fake_run
    asset = MediaAsset(
        id="pexels:1",
        provider="pexels",
        original_url="https://video.example/large.mp4",
        thumbnail_url="https://images.example/thumb.jpeg",
        local_path=str(clip),
        duration_seconds=9.0,
    )

    frames = await extractor.extract_frames(asset, 3)

    assert frames == [b"frame-1", b"frame-2", b"frame-3"]
    assert any("fps=0.333333" in argument for argument in commands[0])
    assert commands[0][commands[0].index("-frames:v") + 1] == "3"
