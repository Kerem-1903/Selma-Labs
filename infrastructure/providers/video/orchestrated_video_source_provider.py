from __future__ import annotations

from collections.abc import Mapping
from collections.abc import AsyncIterator

from core.application.ports.video_search_provider import VideoSearchProvider
from core.domain.entities.media_asset import MediaAsset
from core.domain.exceptions import AssetDownloadError
from core.domain.ports.video_source_port import VideoSourcePort


class OrchestratedVideoSourceProvider(VideoSourcePort):
    """Combines the newer search stack with provider-routed downloads."""

    def __init__(
        self,
        search_provider: VideoSearchProvider,
        download_providers: Mapping[str, VideoSourcePort],
    ) -> None:
        if not download_providers:
            raise ValueError("At least one download provider is required.")
        self._search_provider = search_provider
        self._download_providers: dict[str, VideoSourcePort] = {}
        for name, provider in download_providers.items():
            aliases = {name, getattr(provider, "provider_identity", "")}
            for alias in aliases:
                normalized = alias.strip().lower()
                if normalized:
                    self._download_providers[normalized] = provider

    async def search(self, query: str, max_results: int) -> list[MediaAsset]:
        results = await self._search_provider.search(query, max_results=max_results)
        return results[:max_results]

    async def download(self, asset: MediaAsset) -> bytes:
        provider = self._download_provider_for(asset)
        return await provider.download(asset)

    async def download_stream(self, asset: MediaAsset) -> AsyncIterator[bytes]:
        provider = self._download_provider_for(asset)
        async for chunk in provider.download_stream(asset):
            yield chunk

    def _download_provider_for(self, asset: MediaAsset) -> VideoSourcePort:
        provider = self._download_providers.get(asset.provider.strip().lower())
        if provider is None:
            raise AssetDownloadError(
                f"No download provider is registered for asset provider "
                f"'{asset.provider}'."
            )
        return provider
