"""
Unit tests for VideoSearchService.

Same principle as Sprint 2's test_voice_service.py: these never touch the
network. FakeVideoSourcePort and FakeStorage are minimal in-memory
implementations of VideoSourcePort and StoragePort, proving both ports are
genuinely swappable and that VideoSearchService's business logic is
testable in isolation.
"""
from __future__ import annotations

import pytest

from core.application.services.video_search_service import VideoSearchService
from core.domain.entities.media_asset import MediaAsset
from core.domain.exceptions import (
    AssetDownloadError,
    ProviderTimeoutError,
    StorageError,
    VideoSearchError,
)
from core.domain.ports.storage_port import StoragePort
from core.domain.ports.video_source_port import VideoSourcePort
from core.domain.value_objects.storage_reference import StorageReference


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


class FakeVideoSourcePort(VideoSourcePort):
    """In-memory VideoSourcePort implementation for tests."""

    def __init__(
        self,
        *,
        assets=None,
        download_bytes: bytes = b"fake-video-bytes",
        search_raises=None,
        download_raises=None,
    ):
        self._assets = assets if assets is not None else [_asset()]
        self._download_bytes = download_bytes
        self._search_raises = search_raises
        self._download_raises = download_raises
        self.last_search: dict | None = None
        self.downloaded_assets: list[MediaAsset] = []

    async def search(self, query: str, max_results: int) -> list[MediaAsset]:
        self.last_search = {"query": query, "max_results": max_results}
        if self._search_raises:
            raise self._search_raises
        return self._assets

    async def download(self, asset: MediaAsset) -> bytes:
        self.downloaded_assets.append(asset)
        if self._download_raises:
            raise self._download_raises
        return self._download_bytes


class FakeStorage(StoragePort):
    """In-memory StoragePort implementation for tests."""

    def __init__(self, raises=None):
        self._raises = raises
        self.saved: list[dict] = []

    async def save(self, key: str, data: bytes, content_type: str) -> StorageReference:
        if self._raises:
            raise self._raises
        self.saved.append({"key": key, "data": data, "content_type": content_type})
        return StorageReference(key=key, path=f"/fake/{key}", size_bytes=len(data))


@pytest.mark.asyncio
async def test_discover_returns_assets_with_local_path_set():
    provider = FakeVideoSourcePort()
    storage = FakeStorage()
    service = VideoSearchService(provider, storage)

    assets = await service.discover("Titanic ship")

    assert len(assets) == 1
    assert assets[0].local_path == f"/fake/{storage.saved[0]['key']}"


@pytest.mark.asyncio
async def test_downloads_every_returned_asset():
    assets_in = [_asset("pexels:1"), _asset("pexels:2")]
    provider = FakeVideoSourcePort(assets=assets_in)
    storage = FakeStorage()
    service = VideoSearchService(provider, storage)

    result = await service.discover("Titanic ship")

    assert len(result) == 2
    assert len(storage.saved) == 2
    assert len(provider.downloaded_assets) == 2


@pytest.mark.asyncio
async def test_passes_query_and_max_results_to_provider():
    provider = FakeVideoSourcePort()
    service = VideoSearchService(provider, FakeStorage())

    await service.discover("Titanic ship", max_results=5)

    assert provider.last_search == {"query": "Titanic ship", "max_results": 5}


@pytest.mark.asyncio
async def test_rejects_empty_query():
    service = VideoSearchService(FakeVideoSourcePort(), FakeStorage())

    with pytest.raises(VideoSearchError, match="must not be empty"):
        await service.discover("   ")


@pytest.mark.asyncio
async def test_rejects_max_results_out_of_bounds():
    service = VideoSearchService(FakeVideoSourcePort(), FakeStorage())

    with pytest.raises(VideoSearchError, match="max_results"):
        await service.discover("Titanic ship", max_results=0)


@pytest.mark.asyncio
async def test_raises_when_provider_returns_no_results():
    provider = FakeVideoSourcePort(assets=[])
    service = VideoSearchService(provider, FakeStorage())

    with pytest.raises(VideoSearchError, match="No visual assets found"):
        await service.discover("a very obscure query")


@pytest.mark.asyncio
async def test_propagates_search_provider_errors_unchanged():
    provider = FakeVideoSourcePort(search_raises=ProviderTimeoutError("simulated timeout"))
    service = VideoSearchService(provider, FakeStorage())

    with pytest.raises(ProviderTimeoutError, match="simulated timeout"):
        await service.discover("Titanic ship")


@pytest.mark.asyncio
async def test_propagates_download_provider_errors_unchanged():
    provider = FakeVideoSourcePort(download_raises=ProviderTimeoutError("simulated timeout"))
    service = VideoSearchService(provider, FakeStorage())

    with pytest.raises(ProviderTimeoutError, match="simulated timeout"):
        await service.discover("Titanic ship")


@pytest.mark.asyncio
async def test_raises_asset_download_error_on_empty_bytes():
    provider = FakeVideoSourcePort(download_bytes=b"")
    service = VideoSearchService(provider, FakeStorage())

    with pytest.raises(AssetDownloadError, match="empty content"):
        await service.discover("Titanic ship")


@pytest.mark.asyncio
async def test_propagates_storage_errors_unchanged():
    provider = FakeVideoSourcePort()
    storage = FakeStorage(raises=StorageError("disk full"))
    service = VideoSearchService(provider, storage)

    with pytest.raises(StorageError, match="disk full"):
        await service.discover("Titanic ship")


@pytest.mark.asyncio
async def test_storage_key_includes_provider_and_native_asset_id():
    provider = FakeVideoSourcePort(assets=[_asset("pexels:12345")])
    storage = FakeStorage()
    service = VideoSearchService(provider, storage)

    await service.discover("Titanic ship")

    assert storage.saved[0]["key"] == "video/pexels-12345.mp4"
    assert storage.saved[0]["content_type"] == "video/mp4"


@pytest.mark.asyncio
async def test_provider_asset_id_and_metadata_survive_the_download_step():
    provider = FakeVideoSourcePort(assets=[_asset("pexels:12345")])
    service = VideoSearchService(provider, FakeStorage())

    assets = await service.discover("Titanic ship")

    assert assets[0].provider_asset_id == "12345"
    assert assets[0].metadata == {}


# --- search() (Sprint 5: search-only, no download/persist) ---


@pytest.mark.asyncio
async def test_search_returns_candidates_without_downloading_or_persisting():
    assets_in = [_asset("pexels:1"), _asset("pexels:2")]
    provider = FakeVideoSourcePort(assets=assets_in)
    storage = FakeStorage()
    service = VideoSearchService(provider, storage)

    result = await service.search("Titanic ship")

    assert result == assets_in
    assert all(asset.local_path is None for asset in result)
    assert provider.downloaded_assets == []
    assert storage.saved == []


@pytest.mark.asyncio
async def test_search_returns_empty_list_without_raising_when_no_matches():
    provider = FakeVideoSourcePort(assets=[])
    service = VideoSearchService(provider, FakeStorage())

    result = await service.search("a very obscure query")

    assert result == []


@pytest.mark.asyncio
async def test_search_still_validates_empty_query():
    service = VideoSearchService(FakeVideoSourcePort(), FakeStorage())

    with pytest.raises(VideoSearchError, match="must not be empty"):
        await service.search("   ")


@pytest.mark.asyncio
async def test_search_still_validates_max_results_out_of_bounds():
    service = VideoSearchService(FakeVideoSourcePort(), FakeStorage())

    with pytest.raises(VideoSearchError, match="max_results"):
        await service.search("Titanic ship", max_results=0)


@pytest.mark.asyncio
async def test_search_propagates_provider_errors_unchanged():
    provider = FakeVideoSourcePort(search_raises=ProviderTimeoutError("simulated timeout"))
    service = VideoSearchService(provider, FakeStorage())

    with pytest.raises(ProviderTimeoutError, match="simulated timeout"):
        await service.search("Titanic ship")


@pytest.mark.asyncio
async def test_search_passes_query_and_max_results_to_provider():
    provider = FakeVideoSourcePort()
    service = VideoSearchService(provider, FakeStorage())

    await service.search("Titanic ship", max_results=3)

    assert provider.last_search == {"query": "Titanic ship", "max_results": 3}


# --- download() (Sprint 6: download a specific, already-known asset) ---


@pytest.mark.asyncio
async def test_download_persists_the_given_asset_and_sets_local_path():
    provider = FakeVideoSourcePort()
    storage = FakeStorage()
    service = VideoSearchService(provider, storage)
    candidate = _asset("pexels:12345")

    result = await service.download(candidate)

    assert result.local_path == f"/fake/{storage.saved[0]['key']}"
    assert len(storage.saved) == 1
    assert provider.downloaded_assets == [candidate]


@pytest.mark.asyncio
async def test_download_does_not_call_search():
    provider = FakeVideoSourcePort()
    service = VideoSearchService(provider, FakeStorage())

    await service.download(_asset("pexels:12345"))

    assert provider.last_search is None


@pytest.mark.asyncio
async def test_download_raises_asset_download_error_on_empty_bytes():
    provider = FakeVideoSourcePort(download_bytes=b"")
    service = VideoSearchService(provider, FakeStorage())

    with pytest.raises(AssetDownloadError, match="empty content"):
        await service.download(_asset())


@pytest.mark.asyncio
async def test_download_propagates_provider_errors_unchanged():
    provider = FakeVideoSourcePort(download_raises=ProviderTimeoutError("simulated timeout"))
    service = VideoSearchService(provider, FakeStorage())

    with pytest.raises(ProviderTimeoutError, match="simulated timeout"):
        await service.download(_asset())


@pytest.mark.asyncio
async def test_download_propagates_storage_errors_unchanged():
    provider = FakeVideoSourcePort()
    storage = FakeStorage(raises=StorageError("disk full"))
    service = VideoSearchService(provider, storage)

    with pytest.raises(StorageError, match="disk full"):
        await service.download(_asset())


@pytest.mark.asyncio
async def test_download_uses_the_same_storage_key_convention_as_discover():
    provider = FakeVideoSourcePort()
    storage = FakeStorage()
    service = VideoSearchService(provider, storage)

    await service.download(_asset("pexels:12345"))

    assert storage.saved[0]["key"] == "video/pexels-12345.mp4"
    assert storage.saved[0]["content_type"] == "video/mp4"
