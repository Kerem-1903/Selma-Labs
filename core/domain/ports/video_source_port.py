"""
VideoSourcePort — the contract every visual-asset source provider must
satisfy.

Same role as VoiceGeneratorPort/ScriptGeneratorPort: VideoSearchService
depends only on this interface, never on a concrete provider like Pexels,
Pixabay, or Mixkit. Adding a new provider means writing one new adapter
class and a branch in config/provider_registry.py — no other file changes.

Two responsibilities live on this Port, not in the application layer:
  - search(): query the provider's catalog and translate its response into
    provider-independent MediaAsset objects. Provider-specific response
    shapes (e.g. Pexels' raw JSON) must never leave the adapter.
  - download(): fetch the raw bytes for one previously-returned MediaAsset.
    Kept on the Port rather than assumed to be "just an HTTP GET" in
    VideoSearchService, because not every provider necessarily serves
    plain, unauthenticated file URLs (some require signed URLs or extra
    headers) — the adapter is the only place that should need to know.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from core.domain.entities.media_asset import MediaAsset


class VideoSourcePort(ABC):
    """Searches for and retrieves visual assets from an external catalog."""

    @abstractmethod
    async def search(self, query: str, max_results: int) -> list[MediaAsset]:
        """Search for visual assets matching ``query``.

        No ranking, scoring, or filtering beyond whatever the provider
        itself applies — semantic ranking and scene matching belong to
        later sprints, built on top of this method's output.

        Args:
            query: Free-text search query, e.g. "Titanic ship".
            max_results: Maximum number of assets to return.

        Returns:
            A list of MediaAsset objects, each with ``local_path`` unset
            (None) — nothing has been downloaded yet at this point. May be
            empty if the provider genuinely has no matches.

        Raises:
            ProviderAuthError: Credentials invalid/missing.
            ProviderTimeoutError: Provider did not respond in time.
            ProviderConnectionError: Could not reach the provider at all.
            ProviderQuotaExceededError: Rate limit or quota exceeded.
            ProviderError: Any other provider-side failure.
        """
        raise NotImplementedError

    @abstractmethod
    async def download(self, asset: MediaAsset) -> bytes:
        """Fetch the raw binary content for a previously-searched asset.

        Args:
            asset: A MediaAsset previously returned by ``search`` on this
                same provider (implementations typically use
                ``asset.original_url``).

        Returns:
            Raw bytes of the asset's media file.

        Raises:
            ProviderTimeoutError: Provider did not respond in time.
            ProviderConnectionError: Could not reach the provider at all.
            ProviderQuotaExceededError: Rate limit or quota exceeded.
            AssetDownloadError: The response was invalid (e.g. non-200
                status, or an empty body).
            ProviderError: Any other provider-side failure.
        """
        raise NotImplementedError
