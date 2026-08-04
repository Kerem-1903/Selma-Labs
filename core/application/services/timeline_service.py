"""
TimelineService — application-layer orchestration for turning a ranked
AssetMatchPlan into a downloadable, ordered Timeline.

Bridges Sprint 5's output (AssetMatchPlan, where every SceneAssetMatch
already carries its candidates ranked best-first) to Sprint 3's download
capability (VideoSearchService.download(), added in Sprint 6 alongside
this service). This is the "Timeline Creation" stage of the roadmap,
deliberately scoped separately from "Video Assembly" (Sprint 7+, actual
rendering) per the Sprint 6 design review.

Scope, per Sprint 6's brief: select one asset per scene (the best-ranked
candidate already computed by SceneAssetMatchingService — no new scoring
logic here) and download only that one. No rendering, no editing, no
transitions, no effects. Turning a Timeline into an actual video file is
Sprint 7's job, built on top of this service's output without changing its
public contract — same pattern as every prior sprint boundary in this
codebase.

Architectural note: this service depends on VideoSearchService directly —
a concrete application-layer class, not a Port. Same deliberate, narrow
exception SceneAssetMatchingService already established and documented:
"pick assets[0] and download it" is an in-process decision over data
already inside the application, not a call to a new external system, so
there is no swappable boundary to hide behind a new Port.

Fail-fast policy: if any scene in the AssetMatchPlan has no candidate
assets (SceneAssetMatch.has_matches is False), Timeline creation raises
immediately and names every such scene, rather than producing a Timeline
with a gap in it. See TimelineCreationError's docstring for the full
reasoning — a hole in a Timeline becomes a hole in the rendered video,
which is worse than stopping now.
"""
from __future__ import annotations

import logging

from core.application.services.video_search_service import VideoSearchService
from core.domain.entities.asset_match_plan import AssetMatchPlan
from core.domain.entities.timeline import Timeline
from core.domain.exceptions import TimelineCreationError
from core.domain.value_objects.timeline_clip import TimelineClip

logger = logging.getLogger("selma.timeline_service")


class TimelineService:
    """Selects the best-ranked asset for every scene in an AssetMatchPlan,
    downloads it via an injected VideoSearchService, and assembles an
    ordered Timeline."""

    def __init__(self, video_search_service: VideoSearchService) -> None:
        self._video_search_service = video_search_service

    async def create(self, asset_match_plan: AssetMatchPlan) -> Timeline:
        """Produce a Timeline from ``asset_match_plan``.

        Args:
            asset_match_plan: The AssetMatchPlan whose best-ranked
                candidate per scene will be downloaded and assembled, in
                the same order as ``asset_match_plan.matches``.

        Returns:
            A Timeline with one TimelineClip per scene, each holding the
            downloaded (``local_path`` set) MediaAsset that was ranked
            first for that scene.

        Raises:
            TimelineCreationError: ``asset_match_plan`` has no matches at
                all, or one or more scenes have no candidate assets.
            ProviderError (and subclasses): Propagated unchanged from the
                underlying VideoSourcePort adapter for auth/timeout/
                connection/quota failures during any scene's download --
                these stop processing immediately.
            AssetDownloadError: A selected asset's content failed to
                download or was empty.
            StorageError: Persisting a downloaded asset failed.
        """
        if not asset_match_plan.matches:
            raise TimelineCreationError(
                "AssetMatchPlan has no scene matches to build a Timeline from."
            )

        unmatched_indices = [
            match.scene.index
            for match in asset_match_plan.matches
            if not match.has_matches
        ]
        if unmatched_indices:
            raise TimelineCreationError(
                "Cannot create a Timeline: the following scenes have no "
                f"candidate assets: {unmatched_indices}. Broaden the scene's "
                "search keywords, or provide a fallback asset, then retry."
            )

        logger.info(
            "timeline_creation_started",
            extra={
                "asset_match_plan_id": asset_match_plan.id,
                "scene_count": len(asset_match_plan.matches),
            },
        )

        clips: list[TimelineClip] = []
        for match in asset_match_plan.matches:
            selected = match.assets[0]
            downloaded = await self._video_search_service.download(selected)
            clips.append(TimelineClip(scene=match.scene, asset=downloaded))

            logger.info(
                "clip_created",
                extra={
                    "asset_match_plan_id": asset_match_plan.id,
                    "scene_index": match.scene.index,
                    "asset_id": downloaded.id,
                },
            )

        timeline = Timeline.create(
            asset_match_plan_id=asset_match_plan.id, clips=clips
        )

        logger.info(
            "timeline_creation_completed",
            extra={
                "asset_match_plan_id": asset_match_plan.id,
                "timeline_id": timeline.id,
                "clip_count": len(timeline.clips),
                "total_duration_seconds": timeline.total_duration_seconds,
            },
        )

        return timeline
