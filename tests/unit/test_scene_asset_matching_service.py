"""
Unit tests for SceneAssetMatchingService.

Same no-network principle as every other service test in this codebase.
SceneAssetMatchingService is composed on top of a real VideoSearchService
(not mocked out) constructed with FakeVideoSourcePort/FakeStorage -- this
proves the composition actually works end-to-end through VideoSearchService
rather than assuming its behavior, and matches how the two services are
wired together for real in scripts/match_assets.py.
"""
from __future__ import annotations

import dataclasses

import pytest

from core.application.services.scene_asset_matching_service import (
    SceneAssetMatchingService,
)
from core.application.services.video_search_service import VideoSearchService
from core.domain.entities.media_asset import MediaAsset
from core.domain.entities.scene_plan import ScenePlan
from core.domain.exceptions import ProviderTimeoutError, SceneAssetMatchingError
from core.domain.ports.storage_port import StoragePort
from core.domain.ports.video_source_port import VideoSourcePort
from core.domain.value_objects.scene import Scene
from core.domain.value_objects.storage_reference import StorageReference


def _scene(
    index: int = 0,
    narration: str = "A ship sails at night.",
    keywords=None,
    start_time: float = 0.0,
    end_time: float = 10.0,
) -> Scene:
    return Scene(
        index=index,
        narration=narration,
        search_keywords=keywords if keywords is not None else ["ship", "ocean"],
        detected_objects=["ship"],
        location="ocean",
        mood="tension",
        visual_priority="high",
        start_time=start_time,
        end_time=end_time,
    )


def _scene_plan(scenes=None, scene_plan_id: str | None = None) -> ScenePlan:
    plan = ScenePlan.create(
        script_id="script-1",
        voice_track_id="voice-1",
        total_duration_seconds=10.0,
        provider_used="fake",
        scenes=scenes if scenes is not None else [_scene()],
    )
    if scene_plan_id is not None:
        # Only ScenePlan.create() generates ids; when a test needs a
        # deterministic one it overrides the generated id on the frozen
        # dataclass via dataclasses.replace() instead.
        plan = dataclasses.replace(plan, id=scene_plan_id)
    return plan


def _asset(
    asset_id: str = "pexels:1",
    tags=None,
    width: int | None = 1080,
    height: int | None = 1920,
    duration_seconds: float | None = 10.0,
) -> MediaAsset:
    native_id = asset_id.split(":", 1)[-1]
    return MediaAsset(
        id=asset_id,
        provider="pexels",
        provider_asset_id=native_id,
        media_type="video",
        original_url=f"https://videos.pexels.com/{asset_id}.mp4",
        thumbnail_url="https://images.pexels.com/thumb.jpeg",
        width=width,
        height=height,
        duration_seconds=duration_seconds,
        fps=25.0,
        tags=tags if tags is not None else ["ship"],
        attribution="Video by Test User on Pexels",
        license="Pexels License",
    )


class FakeVideoSourcePort(VideoSourcePort):
    """In-memory VideoSourcePort. Supports returning different assets per
    query, and optionally raising on search -- both needed to exercise
    per-scene behavior (some scenes match, some don't; a provider failure
    on any scene propagates)."""

    def __init__(self, *, assets_by_query=None, default_assets=None, search_raises=None):
        self._assets_by_query = assets_by_query or {}
        self._default_assets = default_assets if default_assets is not None else [_asset()]
        self._search_raises = search_raises
        self.queries_received: list[str] = []

    async def search(self, query: str, max_results: int) -> list[MediaAsset]:
        self.queries_received.append(query)
        if self._search_raises:
            raise self._search_raises
        return self._assets_by_query.get(query, self._default_assets)

    async def download(self, asset: MediaAsset) -> bytes:  # pragma: no cover - unused
        return b"fake-video-bytes"


class FakeStorage(StoragePort):
    """In-memory StoragePort. Records whether save() was ever called, so
    tests can assert matching never downloads anything."""

    def __init__(self):
        self.save_call_count = 0

    async def save(self, key: str, data: bytes, content_type: str) -> StorageReference:
        self.save_call_count += 1
        return StorageReference(key=key, path=f"/fake/{key}", size_bytes=len(data))


def _make_service(video_source: VideoSourcePort, storage: StoragePort, **kwargs):
    video_search_service = VideoSearchService(video_source, storage)
    return SceneAssetMatchingService(video_search_service, **kwargs)


@pytest.mark.asyncio
async def test_produces_one_match_per_scene_in_order():
    scenes = [_scene(index=0, keywords=["a"]), _scene(index=1, keywords=["b"])]
    plan = _scene_plan(scenes=scenes)
    service = _make_service(FakeVideoSourcePort(), FakeStorage())

    result = await service.match(plan)

    assert len(result.matches) == 2
    assert result.matches[0].scene.index == 0
    assert result.matches[1].scene.index == 1


@pytest.mark.asyncio
async def test_asset_match_plan_references_scene_plan_id():
    plan = _scene_plan(scene_plan_id="plan-123")
    service = _make_service(FakeVideoSourcePort(), FakeStorage())

    result = await service.match(plan)

    assert result.scene_plan_id == "plan-123"


@pytest.mark.asyncio
async def test_builds_query_from_scene_search_keywords():
    scenes = [_scene(keywords=["titanic ship", "harbor departure"])]
    plan = _scene_plan(scenes=scenes)
    video_source = FakeVideoSourcePort()
    service = _make_service(video_source, FakeStorage())

    await service.match(plan)

    assert video_source.queries_received == ["titanic ship harbor departure"]


@pytest.mark.asyncio
async def test_matching_never_downloads_or_persists_candidates():
    plan = _scene_plan(scenes=[_scene()])
    storage = FakeStorage()
    service = _make_service(FakeVideoSourcePort(), storage)

    result = await service.match(plan)

    assert storage.save_call_count == 0
    assert all(asset.local_path is None for m in result.matches for asset in m.assets)


@pytest.mark.asyncio
async def test_scene_with_no_matching_assets_is_recorded_not_raised():
    scenes = [_scene(index=0, keywords=["found"]), _scene(index=1, keywords=["notfound"])]
    plan = _scene_plan(scenes=scenes)
    video_source = FakeVideoSourcePort(
        assets_by_query={"found": [_asset()], "notfound": []}
    )
    service = _make_service(video_source, FakeStorage())

    result = await service.match(plan)

    assert result.matches[0].has_matches is True
    assert result.matches[1].has_matches is False
    assert result.matches[1].assets == []


@pytest.mark.asyncio
async def test_processing_continues_after_a_scene_has_no_matches():
    scenes = [
        _scene(index=0, keywords=["notfound"]),
        _scene(index=1, keywords=["found"]),
    ]
    plan = _scene_plan(scenes=scenes)
    video_source = FakeVideoSourcePort(
        assets_by_query={"notfound": [], "found": [_asset()]}
    )
    service = _make_service(video_source, FakeStorage())

    result = await service.match(plan)

    assert len(result.matches) == 2
    assert result.matches[0].assets == []
    assert len(result.matches[1].assets) == 1


@pytest.mark.asyncio
async def test_rejects_scene_plan_with_no_scenes():
    plan = _scene_plan(scenes=[])
    service = _make_service(FakeVideoSourcePort(), FakeStorage())

    with pytest.raises(SceneAssetMatchingError, match="no scenes"):
        await service.match(plan)


@pytest.mark.asyncio
async def test_provider_errors_propagate_and_stop_processing():
    scenes = [_scene(index=0, keywords=["a"]), _scene(index=1, keywords=["b"])]
    plan = _scene_plan(scenes=scenes)
    video_source = FakeVideoSourcePort(search_raises=ProviderTimeoutError("simulated timeout"))
    service = _make_service(video_source, FakeStorage())

    with pytest.raises(ProviderTimeoutError, match="simulated timeout"):
        await service.match(plan)

    # Failed on the first scene; the second scene's query was never sent.
    assert video_source.queries_received == ["a"]


@pytest.mark.asyncio
async def test_respects_configured_candidates_per_scene():
    plan = _scene_plan(scenes=[_scene()])
    video_source = FakeVideoSourcePort()

    captured_max_results = {}

    class CapturingPort(FakeVideoSourcePort):
        async def search(self, query: str, max_results: int):
            captured_max_results["value"] = max_results
            return await super().search(query, max_results)

    service = _make_service(CapturingPort(), FakeStorage(), candidates_per_scene=3)
    await service.match(plan)

    assert captured_max_results["value"] == 3


# --- Ranking heuristics ---


@pytest.mark.asyncio
async def test_ranks_higher_keyword_overlap_first():
    scenes = [_scene(keywords=["ship", "ocean", "harbor"])]
    plan = _scene_plan(scenes=scenes)
    low_overlap = _asset("pexels:low", tags=["ship"])
    high_overlap = _asset("pexels:high", tags=["ship", "ocean", "harbor"])
    video_source = FakeVideoSourcePort(default_assets=[low_overlap, high_overlap])
    service = _make_service(video_source, FakeStorage())

    result = await service.match(plan)

    ranked_ids = [asset.id for asset in result.matches[0].assets]
    assert ranked_ids == ["pexels:high", "pexels:low"]


@pytest.mark.asyncio
async def test_ranks_portrait_orientation_above_landscape_when_keywords_tie():
    scenes = [_scene(keywords=["ship"])]
    plan = _scene_plan(scenes=scenes)
    landscape = _asset("pexels:landscape", tags=["ship"], width=1920, height=1080)
    portrait = _asset("pexels:portrait", tags=["ship"], width=1080, height=1920)
    video_source = FakeVideoSourcePort(default_assets=[landscape, portrait])
    service = _make_service(video_source, FakeStorage())

    result = await service.match(plan)

    ranked_ids = [asset.id for asset in result.matches[0].assets]
    assert ranked_ids == ["pexels:portrait", "pexels:landscape"]


@pytest.mark.asyncio
async def test_ranks_longer_duration_coverage_above_shorter_when_tied_otherwise():
    scenes = [_scene(keywords=["ship"], start_time=0.0, end_time=10.0)]
    plan = _scene_plan(scenes=scenes)
    short_clip = _asset("pexels:short", tags=["ship"], duration_seconds=2.0)
    full_clip = _asset("pexels:full", tags=["ship"], duration_seconds=10.0)
    video_source = FakeVideoSourcePort(default_assets=[short_clip, full_clip])
    service = _make_service(video_source, FakeStorage())

    result = await service.match(plan)

    ranked_ids = [asset.id for asset in result.matches[0].assets]
    assert ranked_ids == ["pexels:full", "pexels:short"]


@pytest.mark.asyncio
async def test_ranking_handles_missing_dimensions_and_duration_gracefully():
    scenes = [_scene(keywords=["ship"])]
    plan = _scene_plan(scenes=scenes)
    incomplete = _asset("pexels:incomplete", tags=["ship"], width=None, height=None, duration_seconds=None)
    video_source = FakeVideoSourcePort(default_assets=[incomplete])
    service = _make_service(video_source, FakeStorage())

    # Should not raise despite missing width/height/duration.
    result = await service.match(plan)

    assert len(result.matches[0].assets) == 1
