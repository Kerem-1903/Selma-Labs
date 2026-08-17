"""
Unit tests for RenderService.

Same no-network, fake-based principle as every other service test in this
codebase. FakeRenderPort never invokes real FFmpeg -- it writes a small
fake file to disk (RenderResult.output_path must point at something real,
since RenderService actually reads it) and returns a RenderResult
describing it. This proves RenderService's own orchestration (read temp
file -> persist via StoragePort -> clean up temp file -> assemble
RenderedVideo) without depending on FFmpeg being installed.
"""
from __future__ import annotations

import os

import pytest

from core.application.services.render_service import RenderService
from core.domain.entities.media_asset import MediaAsset
from core.domain.entities.timeline import Timeline
from core.domain.exceptions import RenderError, StorageError
from core.domain.ports.render_port import RenderPort
from core.domain.ports.storage_port import StoragePort
from core.domain.value_objects.render_result import RenderResult
from core.domain.value_objects.scene import Scene
from core.domain.value_objects.storage_reference import StorageReference
from core.domain.value_objects.timeline_clip import TimelineClip


def _scene(index: int = 0, start_time: float = 0.0, end_time: float = 5.0) -> Scene:
    return Scene(
        index=index,
        narration="A ship sails at night.",
        search_keywords=["ship", "ocean"],
        detected_objects=["ship"],
        location="ocean",
        mood="tension",
        visual_priority="high",
        start_time=start_time,
        end_time=end_time,
    )


def _asset(asset_id: str = "pexels:1", local_path: str = "/fake/video.mp4") -> MediaAsset:
    native_id = asset_id.split(":", 1)[-1]
    return MediaAsset(
        id=asset_id,
        provider="pexels",
        provider_asset_id=native_id,
        media_type="video",
        original_url=f"https://videos.pexels.com/{asset_id}.mp4",
        thumbnail_url="https://images.pexels.com/thumb.jpeg",
        width=1080,
        height=1920,
        duration_seconds=5.0,
        fps=25.0,
        tags=["ship"],
        attribution="Video by Test User on Pexels",
        license="Pexels License",
        local_path=local_path,
    )


def _timeline(clips=None, timeline_id: str | None = None) -> Timeline:
    if clips is None:
        clips = [TimelineClip(scene=_scene(), asset=_asset())]
    timeline = Timeline.create(asset_match_plan_id="plan-1", clips=clips)
    if timeline_id is not None:
        import dataclasses

        timeline = dataclasses.replace(timeline, id=timeline_id)
    return timeline


class FakeRenderPort(RenderPort):
    """In-memory-ish RenderPort. Writes a small real file to ``tmp_path``
    so RenderService's read-then-persist step has something genuine to
    read, without invoking FFmpeg. Records every (timeline, audio_path)
    pair it was asked to render."""

    def __init__(self, tmp_path, *, render_raises=None, output_bytes=b"fake-mp4-bytes"):
        self._tmp_path = tmp_path
        self._render_raises = render_raises
        self._output_bytes = output_bytes
        self.render_calls: list[tuple[str, str]] = []

    async def render(self, timeline: Timeline, narration_audio_path: str) -> RenderResult:
        self.render_calls.append((timeline.id, narration_audio_path))
        if self._render_raises:
            raise self._render_raises
        output_path = self._tmp_path / f"rendered-{timeline.id}.mp4"
        output_path.write_bytes(self._output_bytes)
        return RenderResult(
            output_path=str(output_path),
            duration_seconds=timeline.total_duration_seconds,
            width=1080,
            height=1920,
            fps=30.0,
        )


class FakeStorage(StoragePort):
    """In-memory StoragePort. Records every save() call."""

    def upload_file(self, file_stream, destination_path: str, content_type: str = "video/mp4") -> str:
        return f"fake://{destination_path}"

    def download_file(self, source_path: str, local_destination: str) -> bool:
        return True

    def delete_file(self, file_path: str) -> bool:
        return True

    def __init__(self):
        self.saved: list[tuple[str, bytes, str]] = []

    async def save(self, key: str, data: bytes, content_type: str) -> StorageReference:
        self.saved.append((key, data, content_type))
        return StorageReference(key=key, path=f"/fake/{key}", size_bytes=len(data))


class RaisingStorage(StoragePort):
    async def save(self, key: str, data: bytes, content_type: str) -> StorageReference:
        raise StorageError("disk full")

    def upload_file(self, file_stream, destination_path: str, content_type: str = "video/mp4") -> str:
        return f"fake://{destination_path}"

    def download_file(self, source_path: str, local_destination: str) -> bool:
        return True

    def delete_file(self, file_path: str) -> bool:
        return True


@pytest.mark.asyncio
async def test_render_persists_output_and_returns_rendered_video(tmp_path):
    render_port = FakeRenderPort(tmp_path)
    storage = FakeStorage()
    service = RenderService(render_port, storage)
    timeline = _timeline()

    rendered_video = await service.render(timeline, "/fake/narration.mp3")

    assert rendered_video.timeline_id == timeline.id
    assert rendered_video.duration_seconds == timeline.total_duration_seconds
    assert rendered_video.width == 1080
    assert rendered_video.height == 1920
    assert rendered_video.fps == 30.0
    assert rendered_video.size_bytes == len(b"fake-mp4-bytes")
    assert len(storage.saved) == 1
    saved_key, saved_data, saved_content_type = storage.saved[0]
    assert saved_key == f"render/{rendered_video.id}.mp4"
    assert saved_data == b"fake-mp4-bytes"
    assert saved_content_type == "video/mp4"
    assert rendered_video.video_path == f"/fake/{saved_key}"


@pytest.mark.asyncio
async def test_render_passes_narration_audio_path_not_a_voice_track(tmp_path):
    render_port = FakeRenderPort(tmp_path)
    service = RenderService(render_port, FakeStorage())
    timeline = _timeline()

    await service.render(timeline, "/fake/narration.mp3")

    assert render_port.render_calls == [(timeline.id, "/fake/narration.mp3")]


@pytest.mark.asyncio
async def test_render_cleans_up_temp_output_file(tmp_path):
    render_port = FakeRenderPort(tmp_path)
    service = RenderService(render_port, FakeStorage())
    timeline = _timeline()

    rendered_video = await service.render(timeline, "/fake/narration.mp3")

    temp_path = tmp_path / f"rendered-{timeline.id}.mp4"
    assert not temp_path.exists()
    assert rendered_video is not None  # sanity: render still succeeded


@pytest.mark.asyncio
async def test_rejects_timeline_with_no_clips(tmp_path):
    timeline = _timeline(clips=[])
    service = RenderService(FakeRenderPort(tmp_path), FakeStorage())

    with pytest.raises(RenderError, match="no clips"):
        await service.render(timeline, "/fake/narration.mp3")


@pytest.mark.asyncio
async def test_rejects_empty_narration_audio_path(tmp_path):
    service = RenderService(FakeRenderPort(tmp_path), FakeStorage())
    timeline = _timeline()

    with pytest.raises(RenderError, match="narration_audio_path"):
        await service.render(timeline, "")

    with pytest.raises(RenderError, match="narration_audio_path"):
        await service.render(timeline, "   ")


@pytest.mark.asyncio
async def test_render_port_error_propagates_and_nothing_is_persisted(tmp_path):
    render_port = FakeRenderPort(tmp_path, render_raises=RenderError("ffmpeg exploded"))
    storage = FakeStorage()
    service = RenderService(render_port, storage)
    timeline = _timeline()

    with pytest.raises(RenderError, match="ffmpeg exploded"):
        await service.render(timeline, "/fake/narration.mp3")

    assert storage.saved == []


@pytest.mark.asyncio
async def test_storage_error_propagates_unchanged(tmp_path):
    render_port = FakeRenderPort(tmp_path)
    service = RenderService(render_port, RaisingStorage())
    timeline = _timeline()

    with pytest.raises(StorageError, match="disk full"):
        await service.render(timeline, "/fake/narration.mp3")


@pytest.mark.asyncio
async def test_raises_if_render_result_output_path_missing(tmp_path):
    class MissingFileRenderPort(RenderPort):
        async def render(self, timeline: Timeline, narration_audio_path: str) -> RenderResult:
            return RenderResult(
                output_path=str(tmp_path / "does-not-exist.mp4"),
                duration_seconds=5.0,
                width=1080,
                height=1920,
                fps=30.0,
            )

    service = RenderService(MissingFileRenderPort(), FakeStorage())
    timeline = _timeline()

    with pytest.raises(RenderError, match="could not be read"):
        await service.render(timeline, "/fake/narration.mp3")


@pytest.mark.asyncio
async def test_raises_if_render_result_output_is_empty(tmp_path):
    render_port = FakeRenderPort(tmp_path, output_bytes=b"")
    service = RenderService(render_port, FakeStorage())
    timeline = _timeline()

    with pytest.raises(RenderError, match="empty file"):
        await service.render(timeline, "/fake/narration.mp3")


@pytest.mark.asyncio
async def test_rendered_video_ids_are_unique_across_calls(tmp_path):
    render_port = FakeRenderPort(tmp_path)
    storage = FakeStorage()
    service = RenderService(render_port, storage)

    first = await service.render(_timeline(timeline_id="t1"), "/fake/narration.mp3")
    second = await service.render(_timeline(timeline_id="t2"), "/fake/narration.mp3")

    assert first.id != second.id
    assert {key for key, _, _ in storage.saved} == {
        f"render/{first.id}.mp4",
        f"render/{second.id}.mp4",
    }
