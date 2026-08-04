"""
VideoSearchService — application-layer orchestration for visual asset
discovery.

Same division of responsibility as ScriptService/VoiceService: the provider
adapter's job is "talk to the catalog API and translate the response into
MediaAsset objects," this service's job is "decide whether the results are
usable, download the selected assets, and persist them via StoragePort." It
depends only on VideoSourcePort and StoragePort — never on a concrete
provider or storage backend.

Scope, per Sprint 3's brief: no semantic ranking, no scene matching, no AI
selection. "Selected assets" for this sprint means every asset the provider
returned (bounded by max_results) — narrowing that set down by relevance is
a later sprint's job, built on top of this service without changing its
public contract.

Sprint 5 addendum: ``search()`` was added alongside ``discover()``, not in
place of it. ``discover()``'s validation, empty-result handling, and
download/persist behavior are completely unchanged — both methods now share
a private ``_validate_and_search`` helper for the query/max_results
validation and the provider call, which is the only part of ``discover()``
that moved. ``search()`` exists for a caller (SceneAssetMatchingService)
that wants to see and rank candidates *before* deciding whether downloading
any of them is worthwhile — downloading every candidate for every scene
before ranking would be wasteful. Unlike ``discover()``, ``search()`` does
NOT raise when the provider returns zero results: for a per-scene caller,
"no candidates for this one scene" is a normal business outcome to record,
not a failure — whereas ``discover()`` is still used standalone (e.g. by
``scripts/search_assets.py``), where zero results for the only query in the
whole call genuinely is nothing to return, so it keeps raising.

Sprint 6 addendum: ``download()`` was added alongside ``search()``/
``discover()`` — a thin public wrapper around the same
``_download_and_persist`` this class already used internally inside
``discover()``. It exists for a caller (TimelineService) that has already
selected one specific MediaAsset (the best-ranked candidate from an
AssetMatchPlan) and needs exactly that asset downloaded and persisted —
without re-searching, and without downloading every other candidate for
that scene the way ``discover()`` would. This is a pure exposure of
existing logic, not new behavior: ``discover()``'s per-asset download step
was always this same code path.
"""
from __future__ import annotations

import logging

from core.domain.entities.media_asset import MediaAsset
from core.domain.exceptions import AssetDownloadError, VideoSearchError
from core.domain.ports.storage_port import StoragePort
from core.domain.ports.video_source_port import VideoSourcePort

logger = logging.getLogger("selma.video_search_service")

VIDEO_CONTENT_TYPE = "video/mp4"

# Generic sanity bounds, not provider-specific. 80 happens to match Pexels'
# own per_page ceiling; if a future provider supports a different range,
# that's a contained change here, not a reason to build a
# provider-declares-its-own-limits mechanism ahead of actually needing one.
MIN_MAX_RESULTS = 1
MAX_MAX_RESULTS = 80


class VideoSearchService:
    """Searches for visual assets via an injected provider, downloads and
    persists each result via an injected storage backend."""

    def __init__(self, provider: VideoSourcePort, storage: StoragePort) -> None:
        self._provider = provider
        self._storage = storage

    async def discover(self, query: str, max_results: int = 10) -> list[MediaAsset]:
        """Search for and download visual assets matching ``query``.

        Args:
            query: Free-text search query, e.g. "Titanic ship".
            max_results: Maximum number of assets to fetch and download.

        Returns:
            A list of MediaAsset objects, each with ``local_path`` set to
            where the downloaded file was persisted.

        Raises:
            VideoSearchError: Input was invalid, or the provider returned
                zero results for a valid query.
            ProviderError (and subclasses): Propagated unchanged from the
                adapter for auth/timeout/connection/quota failures during
                search or download — callers need the typed subclass to
                decide whether to retry.
            AssetDownloadError: A selected asset's content failed to
                download or was empty.
            StorageError: Persisting a downloaded asset failed.
        """
        assets = await self._validate_and_search(query, max_results)

        if not assets:
            raise VideoSearchError(
                f"No visual assets found for query: '{(query or '').strip()}'."
            )

        return [await self._download_and_persist(asset) for asset in assets]

    async def search(self, query: str, max_results: int = 10) -> list[MediaAsset]:
        """Search for visual assets matching ``query`` WITHOUT downloading
        or persisting them — the search phase of ``discover()`` on its own.

        Args:
            query: Free-text search query, e.g. "Titanic ship".
            max_results: Maximum number of candidates to fetch.

        Returns:
            A list of MediaAsset objects with ``local_path`` unset (None).
            May be empty if the provider genuinely has no matches for
            ``query`` — unlike ``discover()``, this is NOT treated as an
            error here, since a caller doing its own ranking/selection
            across many queries needs to distinguish "zero candidates for
            this one query" (a normal outcome to record and move on from)
            from "the request itself was invalid" (still raised below).

        Raises:
            VideoSearchError: Input was invalid (empty query, or
                max_results out of the supported range).
            ProviderError (and subclasses): Propagated unchanged from the
                adapter for auth/timeout/connection/quota failures —
                callers need the typed subclass to decide whether to
                retry.
        """
        return await self._validate_and_search(query, max_results)

    async def download(self, asset: MediaAsset) -> MediaAsset:
        """Download and persist one already-known ``asset``.

        Unlike ``discover()``, this does not search — the caller already
        has a specific MediaAsset in hand (e.g. the top-ranked candidate
        from an AssetMatchPlan) and wants exactly that one's content
        fetched and stored.

        Args:
            asset: A MediaAsset previously returned by ``search()`` or
                ``discover()`` (typically with ``local_path`` still None).

        Returns:
            A copy of ``asset`` with ``local_path`` set to where the
            downloaded file was persisted.

        Raises:
            ProviderError (and subclasses): Propagated unchanged from the
                adapter for auth/timeout/connection/quota failures during
                download — callers need the typed subclass to decide
                whether to retry.
            AssetDownloadError: The asset's content failed to download or
                was empty.
            StorageError: Persisting the downloaded asset failed.
        """
        return await self._download_and_persist(asset)

    async def _validate_and_search(self, query: str, max_results: int) -> list[MediaAsset]:
        query = (query or "").strip()
        if not query:
            raise VideoSearchError("Search query must not be empty.")

        if not (MIN_MAX_RESULTS <= max_results <= MAX_MAX_RESULTS):
            raise VideoSearchError(
                f"max_results must be between {MIN_MAX_RESULTS} and "
                f"{MAX_MAX_RESULTS}, got {max_results}."
            )

        logger.info(
            "video_search_started", extra={"query": query, "max_results": max_results}
        )

        assets = await self._provider.search(query=query, max_results=max_results)

        logger.info(
            "video_search_completed", extra={"query": query, "result_count": len(assets)}
        )

        return assets

    async def _download_and_persist(self, asset: MediaAsset) -> MediaAsset:
        data = await self._provider.download(asset)

        if not data:
            raise AssetDownloadError(
                f"Downloaded empty content for asset '{asset.id}' from "
                f"'{asset.original_url}'."
            )

        storage_key = self._build_storage_key(asset)
        reference = await self._storage.save(
            key=storage_key, data=data, content_type=VIDEO_CONTENT_TYPE
        )

        logger.info(
            "asset_downloaded",
            extra={"asset_id": asset.id, "local_path": reference.path},
        )

        return asset.with_local_path(reference.path)

    @staticmethod
    def _build_storage_key(asset: MediaAsset) -> str:
        # Every provider implemented so far (Pexels) only serves mp4 video
        # files. If a future provider serves other containers, this is a
        # small, contained change here — not a reason to add general
        # content-sniffing ahead of actually needing it.
        return f"video/{asset.provider}-{asset.provider_asset_id}.mp4"
