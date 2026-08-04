"""
Unit tests for FfmpegRenderProvider.

Unlike PexelsProvider/ElevenLabsVoiceProvider (network-backed, mocked at
the httpx layer), FfmpegRenderProvider's external dependency is a *local*
subprocess, not a network call -- same category as LocalFsStorage's real
filesystem I/O, which that adapter's own test file already exercises for
real rather than mocking. Consistent with that precedent, these tests
invoke the real ``ffmpeg``/``ffprobe`` binaries against tiny synthetic
fixtures generated with FFmpeg's own ``lavfi`` test-source input (a solid
color video, a sine-wave tone) -- no real video/audio files, no network, no
API key, and no meaningful runtime cost. Skipped automatically in any
environment where FFmpeg isn't installed, since (unlike this project's
network-backed providers) there is no way to fake a local binary's absence
the way an API key can be faked.
"""
from __future__ import annotations

import asyncio
import dataclasses
import shutil

import pytest

from core.domain.entities.media_asset import MediaAsset
from core.domain.entities.timeline import Timeline
from core.domain.exceptions import RenderError
from core.domain.value_objects.scene import Scene
from core.domain.value_objects.timeline_clip import TimelineClip
from infrastructure.providers.render.ffmpeg_render_provider import FfmpegRenderProvider

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None

pytestmark = pytest.mark.skipif(
    not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed on PATH"
)


async def _make_fixture_clip(path, duration: float, color: str) -> None:
    process = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c={color}:s=320x240:d={duration}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(path),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await process.communicate()
    assert process.returncode == 0


async def _make_fixture_audio(path, duration: float) -> None:
    process = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
        "-c:a", "aac",
        str(path),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await process.communicate()
    assert process.returncode == 0


def _scene(index: int, start_time: float, end_time: float) -> Scene:
    return Scene(
        index=index,
        narration="narration",
        search_keywords=["kw"],
        detected_objects=[],
        location="",
        mood="",
        visual_priority="high",
        start_time=start_time,
        end_time=end_time,
    )


def _asset(local_path: str) -> MediaAsset:
    return MediaAsset(
        id="pexels:1",
        provider="pexels",
        provider_asset_id="1",
        media_type="video",
        original_url="https://videos.pexels.com/1.mp4",
        thumbnail_url="https://images.pexels.com/thumb.jpeg",
        width=320,
        height=240,
        duration_seconds=2.0,
        fps=25.0,
        tags=[],
        attribution="Test",
        license="Test License",
        local_path=local_path,
    )


@pytest.mark.asyncio
async def test_render_produces_a_playable_file_with_expected_properties(tmp_path):
    clip_a = tmp_path / "clip_a.mp4"
    clip_b = tmp_path / "clip_b.mp4"
    audio = tmp_path / "narration.aac"
    await _make_fixture_clip(clip_a, duration=1.0, color="red")
    await _make_fixture_clip(clip_b, duration=1.0, color="blue")
    await _make_fixture_audio(audio, duration=2.0)

    clips = [
        TimelineClip(scene=_scene(0, 0.0, 1.0), asset=_asset(str(clip_a))),
        TimelineClip(scene=_scene(1, 1.0, 2.0), asset=_asset(str(clip_b))),
    ]
    timeline = Timeline.create(asset_match_plan_id="plan-1", clips=clips)

    provider = FfmpegRenderProvider(output_width=160, output_height=120, fps=24)
    result = await provider.render(timeline, str(audio))

    try:
        assert result.width == 160
        assert result.height == 120
        # Total duration should be close to the sum of both clips (~2s),
        # within encoding/rounding tolerance.
        assert 1.5 <= result.duration_seconds <= 2.5
        import os

        assert os.path.exists(result.output_path)
        assert os.path.getsize(result.output_path) > 0
    finally:
        import os

        if os.path.exists(result.output_path):
            os.remove(result.output_path)


@pytest.mark.asyncio
async def test_raises_render_error_for_empty_timeline():
    timeline = Timeline.create(asset_match_plan_id="plan-1", clips=[])
    provider = FfmpegRenderProvider()

    with pytest.raises(RenderError, match="no clips"):
        await provider.render(timeline, "/nonexistent/narration.mp3")


@pytest.mark.asyncio
async def test_raises_render_error_for_missing_narration_audio(tmp_path):
    clip = tmp_path / "clip.mp4"
    await _make_fixture_clip(clip, duration=1.0, color="green")
    clips = [TimelineClip(scene=_scene(0, 0.0, 1.0), asset=_asset(str(clip)))]
    timeline = Timeline.create(asset_match_plan_id="plan-1", clips=clips)
    provider = FfmpegRenderProvider()

    with pytest.raises(RenderError, match="Narration audio file not found"):
        await provider.render(timeline, str(tmp_path / "does-not-exist.mp3"))


@pytest.mark.asyncio
async def test_raises_render_error_on_missing_ffmpeg_binary(tmp_path):
    clip = tmp_path / "clip.mp4"
    audio = tmp_path / "narration.aac"
    await _make_fixture_clip(clip, duration=1.0, color="green")
    await _make_fixture_audio(audio, duration=1.0)
    clips = [TimelineClip(scene=_scene(0, 0.0, 1.0), asset=_asset(str(clip)))]
    timeline = Timeline.create(asset_match_plan_id="plan-1", clips=clips)

    provider = FfmpegRenderProvider(ffmpeg_binary="ffmpeg-does-not-exist")

    with pytest.raises(RenderError, match="Could not find binary"):
        await provider.render(timeline, str(audio))


@pytest.mark.asyncio
async def test_raises_render_error_for_non_positive_scene_duration(tmp_path):
    clip = tmp_path / "clip.mp4"
    audio = tmp_path / "narration.aac"
    await _make_fixture_clip(clip, duration=1.0, color="green")
    await _make_fixture_audio(audio, duration=1.0)
    # end_time == start_time -> zero duration, must be rejected before
    # ever invoking ffmpeg on a degenerate trim.
    clips = [TimelineClip(scene=_scene(0, 1.0, 1.0), asset=_asset(str(clip)))]
    timeline = Timeline.create(asset_match_plan_id="plan-1", clips=clips)
    provider = FfmpegRenderProvider()

    with pytest.raises(RenderError, match="non-positive duration"):
        await provider.render(timeline, str(audio))
