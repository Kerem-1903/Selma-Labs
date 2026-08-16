from __future__ import annotations

import pytest

from core.domain.entities.media_asset import MediaAsset
from core.domain.exceptions import AssetDownloadError
from infrastructure.providers.video.orchestrated_video_source_provider import (
    OrchestratedVideoSourceProvider,
)


def _asset(provider: str = "pexels") -> MediaAsset:
    return MediaAsset(
        id=f"{provider}:1",
        provider=provider,
        provider_asset_id="1",
        media_type="video",
        original_url="https://example.com/video.mp4",
        thumbnail_url="https://example.com/thumb.jpg",
        width=1080,
        height=1920,
        duration_seconds=10.0,
        fps=30.0,
        tags=["ocean"],
        attribution="Test",
        license="Test",
    )


class FakeSearchProvider:
    name = "search-stack"

    def __init__(self, results: list[MediaAsset]) -> None:
        self.results = results
        self.calls: list[tuple[str, int]] = []

    async def search(self, query: str, **kwargs) -> list[MediaAsset]:
        self.calls.append((query, kwargs["max_results"]))
        return self.results


class FakeDownloadProvider:
    provider_identity = "pexels:video_source"

    def __init__(self) -> None:
        self.downloaded: list[str] = []

    async def search(self, query: str, max_results: int) -> list[MediaAsset]:
        return []

    async def download(self, asset: MediaAsset) -> bytes:
        self.downloaded.append(asset.id)
        return b"video"


@pytest.mark.asyncio
async def test_search_delegates_to_search_stack_and_limits_results():
    search = FakeSearchProvider([_asset(), _asset(), _asset()])
    provider = OrchestratedVideoSourceProvider(
        search_provider=search,
        download_providers={"pexels": FakeDownloadProvider()},
    )

    results = await provider.search("ocean", 2)

    assert len(results) == 2
    assert search.calls == [("ocean", 2)]


@pytest.mark.asyncio
async def test_download_routes_using_provider_identity_alias():
    download_provider = FakeDownloadProvider()
    provider = OrchestratedVideoSourceProvider(
        search_provider=FakeSearchProvider([]),
        download_providers={"pexels": download_provider},
    )
    asset = _asset(provider="pexels:video_source")

    data = await provider.download(asset)

    assert data == b"video"
    assert download_provider.downloaded == [asset.id]


@pytest.mark.asyncio
async def test_download_rejects_unregistered_provider():
    provider = OrchestratedVideoSourceProvider(
        search_provider=FakeSearchProvider([]),
        download_providers={"pexels": FakeDownloadProvider()},
    )

    with pytest.raises(AssetDownloadError, match="No download provider"):
        await provider.download(_asset(provider="unknown"))
