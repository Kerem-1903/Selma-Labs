"""
Unit tests for TimelineService.

Same no-network principle as every other service test in this codebase.
TimelineService is composed on top of a real VideoSearchService (not
mocked out) constructed with FakeVideoSourcePort/FakeStorage -- this
proves the composition actually works end-to-end through
VideoSearchService.download() rather than assuming its behavior, and
matches how the two services would be wired together for real in a future
scripts/create_timeline.py.
"""
from __future__ import annotations

import dataclasses

import pytest

from core.application.services.timeline_service import TimelineService
from core.application.services.video_search_service import VideoSearchService
from core.domain.entities.asset_match_plan import AssetMatchPlan
from core.domain.entities.media_asset import MediaAsset
from core.domain.exceptions import AssetDownloadError, ProviderTimeoutError, TimelineCreationError
from core.domain.ports.storage_port import StoragePort
from core.domain.ports.video_source_port import VideoSourcePort
from core.domain.value_objects.scene import Scene
from core.domain.value_objects.scene_asset_match import SceneAssetMatch
from core.domain.value_objects.storage_reference import StorageReference


def _scene(
    index: int = 0,
    narration: str = "A ship sails at night.",
    start_time: float = 0.0,
    end_time: float = 10.0,
) -> Scene:
    return Scene(
        index=index,
        narration=narration,
        search_keywords=["ship", "ocean"],
        detected_objects=["ship"],
        location="ocean",
        mood="tension",
        visual_priority="high",
        start_time=start_time,
        end_time=end_time,
    )


def _asset(asset_id: str = "pexels:1") -> MediaAsset:
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
        duration_seconds=10.0,
        fps=25.0,
        tags=["ship"],
        attribution="Video by Test User on Pexels",
        license="Pexels License",
    )


def _asset_match_plan(matches, plan_id: str | None = None) -> AssetMatchPlan:
    plan = AssetMatchPlan.create(scene_plan_id="scene-plan-1", matches=matches)
    if plan_id is not None:
        # Only AssetMatchPlan.create() generates ids; a test that needs a
        # deterministic one overrides the generated id on the frozen
        # dataclass via dataclasses.replace() instead.
        plan = dataclasses.replace(plan, id=plan_id)
    return plan


class FakeVideoSourcePort(VideoSourcePort):
    """In-memory VideoSourcePort. download() records every asset it was
    asked to fetch, and can optionally raise -- needed to prove
    TimelineService downloads exactly the selected (best-ranked) asset,
    nothing else, and that provider failures propagate."""

    def __init__(self, *, download_raises=None):
        self._download_raises = download_raises
        self.downloaded_asset_ids: list[str] = []

    async def search(self, query: str, max_results: int) -> list[MediaAsset]:  # pragma: no cover - unused
        return []

    async def download(self, asset: MediaAsset) -> bytes:
        self.downloaded_asset_ids.append(asset.id)
        if self._download_raises:
            raise self._download_raises
        return b"fake-video-bytes"


class FakeStorage(StoragePort):
    """In-memory StoragePort. Records every save() call."""

    def __init__(self):
        self.saved_keys: list[str] = []

    async def save(self, key: str, data: bytes, content_type: str) -> StorageReference:
        self.saved_keys.append(key)
        return StorageReference(key=key, path=f"/fake/{key}", size_bytes=len(data))


def _make_service(video_source: VideoSourcePort, storage: StoragePort) -> TimelineService:
    video_search_service = VideoSearchService(video_source, storage)
    return TimelineService(video_search_service)


@pytest.mark.asyncio
async def test_produces_one_clip_per_scene_in_order():
    matches = [
        SceneAssetMatch(scene=_scene(index=0), assets=[_asset("pexels:a")]),
        SceneAssetMatch(scene=_scene(index=1), assets=[_asset("pexels:b")]),
    ]
    plan = _asset_match_plan(matches)
    service = _make_service(FakeVideoSourcePort(), FakeStorage())

    timeline = await service.create(plan)

    assert len(timeline.clips) == 2
    assert timeline.clips[0].scene.index == 0
    assert timeline.clips[1].scene.index == 1


@pytest.mark.asyncio
async def test_selects_the_best_ranked_asset_per_scene():
    best = _asset("pexels:best")
    second = _asset("pexels:second")
    matches = [SceneAssetMatch(scene=_scene(), assets=[best, second])]
    plan = _asset_match_plan(matches)
    video_source = FakeVideoSourcePort()
    service = _make_service(video_source, FakeStorage())

    timeline = await service.create(plan)

    assert timeline.clips[0].asset.id == "pexels:best"
    # Only the selected (best-ranked) asset is downloaded, not every candidate.
    assert video_source.downloaded_asset_ids == ["pexels:best"]


@pytest.mark.asyncio
async def test_downloaded_clip_asset_has_local_path_set():
    matches = [SceneAssetMatch(scene=_scene(), assets=[_asset()])]
    plan = _asset_match_plan(matches)
    service = _make_service(FakeVideoSourcePort(), FakeStorage())

    timeline = await service.create(plan)

    assert timeline.clips[0].asset.local_path is not None


@pytest.mark.asyncio
async def test_timeline_references_asset_match_plan_id():
    matches = [SceneAssetMatch(scene=_scene(), assets=[_asset()])]
    plan = _asset_match_plan(matches, plan_id="plan-123")
    service = _make_service(FakeVideoSourcePort(), FakeStorage())

    timeline = await service.create(plan)

    assert timeline.asset_match_plan_id == "plan-123"


@pytest.mark.asyncio
async def test_total_duration_is_the_last_scenes_end_time():
    matches = [
        SceneAssetMatch(scene=_scene(index=0, start_time=0.0, end_time=5.0), assets=[_asset("pexels:a")]),
        SceneAssetMatch(scene=_scene(index=1, start_time=5.0, end_time=12.5), assets=[_asset("pexels:b")]),
    ]
    plan = _asset_match_plan(matches)
    service = _make_service(FakeVideoSourcePort(), FakeStorage())

    timeline = await service.create(plan)

    assert timeline.total_duration_seconds == 12.5


@pytest.mark.asyncio
async def test_timeline_metadata_defaults_to_empty_dict():
    matches = [SceneAssetMatch(scene=_scene(), assets=[_asset()])]
    plan = _asset_match_plan(matches)
    service = _make_service(FakeVideoSourcePort(), FakeStorage())

    timeline = await service.create(plan)

    assert timeline.metadata == {}
    assert timeline.clips[0].metadata == {}


@pytest.mark.asyncio
async def test_rejects_asset_match_plan_with_no_matches():
    plan = _asset_match_plan(matches=[])
    service = _make_service(FakeVideoSourcePort(), FakeStorage())

    with pytest.raises(TimelineCreationError, match="no scene matches"):
        await service.create(plan)


@pytest.mark.asyncio
async def test_fails_fast_when_any_scene_has_no_candidate_assets():
    matches = [
        SceneAssetMatch(scene=_scene(index=0), assets=[_asset("pexels:a")]),
        SceneAssetMatch(scene=_scene(index=1), assets=[]),
        SceneAssetMatch(scene=_scene(index=2), assets=[_asset("pexels:c")]),
    ]
    plan = _asset_match_plan(matches)
    video_source = FakeVideoSourcePort()
    service = _make_service(video_source, FakeStorage())

    with pytest.raises(TimelineCreationError, match=r"\[1\]"):
        await service.create(plan)

    # Fails validation before downloading anything.
    assert video_source.downloaded_asset_ids == []


@pytest.mark.asyncio
async def test_fail_fast_error_names_every_unmatched_scene():
    matches = [
        SceneAssetMatch(scene=_scene(index=0), assets=[]),
        SceneAssetMatch(scene=_scene(index=1), assets=[_asset()]),
        SceneAssetMatch(scene=_scene(index=2), assets=[]),
    ]
    plan = _asset_match_plan(matches)
    service = _make_service(FakeVideoSourcePort(), FakeStorage())

    with pytest.raises(TimelineCreationError, match=r"\[0, 2\]"):
        await service.create(plan)


@pytest.mark.asyncio
async def test_provider_errors_propagate_and_stop_processing():
    matches = [
        SceneAssetMatch(scene=_scene(index=0), assets=[_asset("pexels:a")]),
        SceneAssetMatch(scene=_scene(index=1), assets=[_asset("pexels:b")]),
    ]
    plan = _asset_match_plan(matches)
    video_source = FakeVideoSourcePort(download_raises=ProviderTimeoutError("simulated timeout"))
    service = _make_service(video_source, FakeStorage())

    with pytest.raises(ProviderTimeoutError, match="simulated timeout"):
        await service.create(plan)

    # Failed downloading the first scene's asset; the second was never attempted.
    assert video_source.downloaded_asset_ids == ["pexels:a"]


@pytest.mark.asyncio
async def test_empty_downloaded_content_raises_asset_download_error():
    matches = [SceneAssetMatch(scene=_scene(), assets=[_asset()])]
    plan = _asset_match_plan(matches)

    class EmptyDownloadPort(FakeVideoSourcePort):
        async def download(self, asset: MediaAsset) -> bytes:
            self.downloaded_asset_ids.append(asset.id)
            return b""

    service = _make_service(EmptyDownloadPort(), FakeStorage())

    with pytest.raises(AssetDownloadError):
        await service.create(plan)


@pytest.mark.asyncio
async def test_falls_back_to_next_candidate_on_asset_download_error():
    first = _asset("pexels:broken")
    second = _asset("pexels:working")
    plan = _asset_match_plan(
        [SceneAssetMatch(scene=_scene(), assets=[first, second])]
    )

    class FallbackDownloadPort(FakeVideoSourcePort):
        async def download(self, asset: MediaAsset) -> bytes:
            self.downloaded_asset_ids.append(asset.id)
            if asset.id == first.id:
                raise AssetDownloadError("broken asset")
            return b"fake-video-bytes"

    video_source = FallbackDownloadPort()
    video_search_service = VideoSearchService(video_source, FakeStorage())
    service = TimelineService(
        video_search_service, fallback_on_download_error=True
    )

    timeline = await service.create(plan)

    assert video_source.downloaded_asset_ids == [first.id, second.id]
    assert timeline.clips[0].asset.id == second.id


@pytest.mark.asyncio
async def test_timeline_to_dict_includes_clips_and_metadata():
    matches = [SceneAssetMatch(scene=_scene(index=0), assets=[_asset("pexels:a")])]
    plan = _asset_match_plan(matches)
    service = _make_service(FakeVideoSourcePort(), FakeStorage())

    timeline = await service.create(plan)
    data = timeline.to_dict()

    assert data["asset_match_plan_id"] == plan.id
    assert data["metadata"] == {}
    assert len(data["clips"]) == 1
    assert data["clips"][0]["scene_index"] == 0
    assert data["clips"][0]["asset"]["id"] == "pexels:a"
    assert data["clips"][0]["metadata"] == {}
