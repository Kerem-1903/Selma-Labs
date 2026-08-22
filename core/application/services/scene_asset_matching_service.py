"""
SceneAssetMatchingService — application-layer orchestration for matching
visual asset candidates to each Scene in a ScenePlan.

Bridges Sprint 4's output (ScenePlan, where every Scene already carries
search_keywords) to Sprint 3's capability (VideoSourcePort-backed search),
per Sprint 3's own README: "narrowing that set down by relevance is a
later sprint's job, built on top of this service without changing its
public contract." This is that later sprint.

Scope, per Sprint 5's brief: only matching. No rendering, no editing, no
AI Vision, no publishing, no downloading beyond what VideoSearchService.
search() already does not do. Selecting one final asset per scene and
downloading it is Video Assembly's job (Sprint 6+), built on top of this
service's output without changing its public contract -- same pattern as
every prior sprint boundary in this codebase.

Architectural note: this service depends on VideoSearchService directly --
a concrete application-layer class, not a Port. This is a deliberate
exception to the "services depend only on Ports" pattern used everywhere
else in this codebase, and it's a narrow one: query-building here
(joining a Scene's search_keywords into a query string) is a deterministic
in-process transformation, not a call to an external system, so there is
no swappable boundary to hide behind a new Port -- introducing one (e.g. a
QueryBuilderPort) would be exactly the kind of premature abstraction this
project's MVP philosophy warns against. VideoSourcePort/StoragePort
swapping keeps working transparently through VideoSearchService, since
this service never touches those ports directly. If a second, unrelated
consumer of query-building logic ever appears, extracting it into a
standalone (still Port-free) helper module is a small, contained change --
not a reason to build one pre-emptively now.

Why ranking happens here and not inside VideoSearchService: VideoSearchService
owns "how do I search/download," this service owns "given a Scene's
intent, which of the candidates VideoSearchService found are actually
relevant" -- the same division of responsibility ScenePlanningService uses
for timing (the provider adapter does the AI work, the service decides
what's usable), applied to ranking instead.
"""
from __future__ import annotations

import logging
from dataclasses import replace

from core.application.services.asset_selection_service import AssetSelectionService
from core.application.services.video_search_service import VideoSearchService
from core.application.services.vision_asset_scoring_service import VisionAssetScoringService
from core.domain.entities.asset_match_plan import AssetMatchPlan
from core.domain.entities.media_asset import MediaAsset
from core.domain.entities.scene_plan import ScenePlan
from core.domain.exceptions import SceneAssetMatchingError
from core.domain.value_objects.scene import Scene
from core.domain.value_objects.scene_asset_match import SceneAssetMatch
from core.domain.value_objects.asset_score import AssetScore
from core.domain.value_objects.scored_asset import ScoredAsset

logger = logging.getLogger("selma.scene_asset_matching_service")

# How many search candidates to request per scene, before ranking. Deliberately
# separate from VideoSearchService's own MIN/MAX_MAX_RESULTS bounds -- this is
# a per-scene default appropriate for ranking a handful of candidates down to
# the best fit, not a hard protocol limit.
DEFAULT_CANDIDATES_PER_SCENE = 10

# --- Ranking weights (deterministic heuristics only -- no embeddings, no AI
# Vision, no semantic models; see this module's docstring and the README's
# Sprint 5 section for why). Each is a plain, explainable number of points
# added to a candidate's score; higher wins. Tunable constants, not a
# learned model -- changing one is a one-line, fully-inspectable edit.

# Dominant signal: how many of the scene's search_keywords appear (case-
# insensitively, whole-token) among the asset's tags.
KEYWORD_OVERLAP_WEIGHT = 10.0

# SELMA Shorts are vertical video; a portrait-oriented asset (height > width)
# fits the target format without cropping, so it's preferred over a
# landscape or square asset when other signals are equal.
PORTRAIT_ORIENTATION_BONUS = 3.0
SQUARE_ORIENTATION_BONUS = 1.0

# An asset that's at least as long as the scene it would cover needs no
# looping; a shorter asset gets partial credit proportional to how much of
# the scene it actually covers.
DURATION_COVERAGE_WEIGHT = 2.0


class SceneAssetMatchingService:
    """Matches and ranks visual asset candidates for every Scene in a
    ScenePlan, via an injected VideoSearchService."""

    def __init__(
        self,
        video_search_service: VideoSearchService,
        candidates_per_scene: int = DEFAULT_CANDIDATES_PER_SCENE,
        asset_selection_service: AssetSelectionService | None = None,
        vision_scoring_service: VisionAssetScoringService | None = None
    ) -> None:
        self._video_search_service = video_search_service
        self._candidates_per_scene = candidates_per_scene
        self._asset_selection_service = asset_selection_service
        self._vision_scoring_service = vision_scoring_service

    async def match(self, scene_plan: ScenePlan) -> AssetMatchPlan:
        """Produce a ranked AssetMatchPlan for every scene in ``scene_plan``.

        Args:
            scene_plan: The ScenePlan whose scenes will each be searched
                for visual candidates, using that scene's search_keywords.

        Returns:
            An AssetMatchPlan with one SceneAssetMatch per input scene, in
            the same order. A scene with no matching candidates still
            produces a SceneAssetMatch with ``assets == []`` -- see this
            module's docstring on why that's a business outcome, not an
            error, and does not stop the remaining scenes from being
            processed.

        Raises:
            SceneAssetMatchingError: ``scene_plan`` has no scenes to match
                against.
            ProviderError (and subclasses): Propagated unchanged from the
                underlying VideoSourcePort adapter for auth/timeout/
                connection/quota failures during any scene's search --
                these are real failures, not "no results," and stop
                processing immediately rather than being recorded as an
                empty match.
            VideoSearchError: A scene's built query or the configured
                candidate count was invalid. Not expected in practice
                since ScenePlanningService already guarantees every Scene
                has non-empty search_keywords, but not assumed blindly --
                same defensive-validation posture every service in this
                codebase takes toward its inputs.
        """
        if not scene_plan.scenes:
            raise SceneAssetMatchingError(
                "ScenePlan has no scenes to match assets for."
            )

        logger.info(
            "scene_asset_matching_started",
            extra={
                "scene_plan_id": scene_plan.id,
                "scene_count": len(scene_plan.scenes),
            },
        )

        if self._asset_selection_service is None and self._vision_scoring_service is None:
            matches = await self._match_legacy(scene_plan)
            return self._finish_plan(scene_plan, matches)

        timeline_candidates: list[tuple[Scene, list[ScoredAsset]]] = []
        for scene in scene_plan.scenes:
            query = self._build_query(scene)
            candidates = await self._video_search_service.search(
                query=query, max_results=self._candidates_per_scene
            )
            scored = self._score_candidates(candidates, scene)
            if self._vision_scoring_service is not None:
                scored = await self._vision_scoring_service.score_scene(scene, scored)
            timeline_candidates.append((scene, scored))

            logger.info(
                "scene_matched",
                extra={
                    "scene_plan_id": scene_plan.id,
                    "scene_index": scene.index,
                    "candidate_count": len(scored),
                },
            )

        if self._asset_selection_service is not None:
            selected = self._asset_selection_service.select_for_timeline(timeline_candidates)
            matches = [
                SceneAssetMatch(
                    scene=scene,
                    assets=[
                        replace(
                            candidate.original.asset,
                            score=candidate.adjusted_score,
                        )
                        for candidate in candidates
                    ],
                )
                for scene, candidates in selected
            ]
        else:
            matches = [
                SceneAssetMatch(
                    scene=scene,
                    assets=[replace(item.asset, score=item.score.final_score) for item in candidates],
                )
                for scene, candidates in timeline_candidates
            ]

        return self._finish_plan(scene_plan, matches)

    async def _match_legacy(self, scene_plan: ScenePlan) -> list[SceneAssetMatch]:
        matches: list[SceneAssetMatch] = []
        for scene in scene_plan.scenes:
            query = self._build_query(scene)
            candidates = await self._video_search_service.search(
                query=query, max_results=self._candidates_per_scene
            )
            ranked = self._rank(candidates, scene)
            matches.append(SceneAssetMatch(scene=scene, assets=ranked))

            logger.info(
                "scene_matched",
                extra={
                    "scene_plan_id": scene_plan.id,
                    "scene_index": scene.index,
                    "candidate_count": len(ranked),
                },
            )
        return matches

    @staticmethod
    def _finish_plan(
        scene_plan: ScenePlan, matches: list[SceneAssetMatch]
    ) -> AssetMatchPlan:

        logger.info(
            "scene_asset_matching_completed",
            extra={
                "scene_plan_id": scene_plan.id,
                "matched_scene_count": sum(1 for m in matches if m.has_matches),
                "unmatched_scene_count": sum(1 for m in matches if not m.has_matches),
            },
        )

        return AssetMatchPlan.create(scene_plan_id=scene_plan.id, matches=matches)

    @staticmethod
    def _build_query(scene: Scene) -> str:
        """Deterministically build a search query from a scene's keywords.

        Not a Port: this is an internal, in-process transformation of data
        already inside the application, not a call to an external system
        -- see this module's docstring for the full reasoning.
        """
        return " ".join(scene.search_keywords)

    @classmethod
    def _rank(cls, assets: list[MediaAsset], scene: Scene) -> list[MediaAsset]:
        """Sort candidates best-first using deterministic heuristics.

        Stable sort: candidates with equal scores keep the provider's
        original relative order rather than being reshuffled arbitrarily.
        """
        return sorted(assets, key=lambda asset: cls._score(asset, scene), reverse=True)

    @classmethod
    def _score_candidates(
        cls, assets: list[MediaAsset], scene: Scene
    ) -> list[ScoredAsset]:
        maximum = (
            max(len({keyword.strip().lower() for keyword in scene.search_keywords if keyword.strip()}), 1)
            * KEYWORD_OVERLAP_WEIGHT
            + PORTRAIT_ORIENTATION_BONUS
            + DURATION_COVERAGE_WEIGHT
        )
        scored = [
            ScoredAsset(
                asset=asset,
                score=AssetScore(final_score=min(cls._score(asset, scene) / maximum, 1.0)),
            )
            for asset in assets
        ]
        return sorted(scored, key=lambda item: item.score.final_score, reverse=True)

    @staticmethod
    def _score(asset: MediaAsset, scene: Scene) -> float:
        score = 0.0

        scene_keywords = SceneAssetMatchingService._terms(scene.search_keywords)
        asset_tags = SceneAssetMatchingService._terms(asset.tags)
        overlap = len(scene_keywords & asset_tags)
        score += overlap * KEYWORD_OVERLAP_WEIGHT

        if asset.width is not None and asset.height is not None:
            if asset.height > asset.width:
                score += PORTRAIT_ORIENTATION_BONUS
            elif asset.height == asset.width:
                score += SQUARE_ORIENTATION_BONUS
            # landscape (height < width): no bonus.

        scene_duration = max(scene.end_time - scene.start_time, 0.0)
        if asset.duration_seconds is not None and scene_duration > 0:
            if asset.duration_seconds >= scene_duration:
                score += DURATION_COVERAGE_WEIGHT
            else:
                coverage_ratio = asset.duration_seconds / scene_duration
                score += DURATION_COVERAGE_WEIGHT * coverage_ratio

        return score

    @staticmethod
    def _terms(values: list[str]) -> set[str]:
        terms: set[str] = set()
        for value in values:
            cleaned = value.strip().lower()
            if not cleaned:
                continue
            terms.add(cleaned)
            terms.update(cleaned.split())
        return terms
