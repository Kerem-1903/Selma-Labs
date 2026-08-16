from __future__ import annotations

import pytest

from core.application.services.vision_asset_scoring_service import (
    VisionAssetScoringService,
)
from core.domain.entities.media_asset import MediaAsset
from core.domain.exceptions import LowVisionConfidenceError, VisualAssetNotFoundError
from core.domain.value_objects.asset_score import AssetScore
from core.domain.value_objects.scene import Scene
from core.domain.value_objects.scored_asset import ScoredAsset
from core.domain.value_objects.vision_analysis_result import VisionAnalysisResult
from core.domain.value_objects.visual_intent import VisualIntent


def _asset(asset_id: str) -> MediaAsset:
    return MediaAsset(
        id=asset_id,
        provider="pexels",
        provider_asset_id=asset_id,
        media_type="video",
        original_url=f"https://example.com/{asset_id}.mp4",
        thumbnail_url="https://example.com/thumb.jpg",
        width=1080,
        height=1920,
        duration_seconds=10.0,
        fps=30.0,
        tags=["ocean"],
        attribution="Test",
        license="Test",
    )


def _scene() -> Scene:
    return Scene(
        index=0,
        narration="A diver enters the deep ocean.",
        search_keywords=["diver", "deep ocean"],
        detected_objects=["diver"],
        location="ocean",
        mood="mysterious",
        visual_priority="high",
        start_time=0.0,
        end_time=5.0,
    )


class FakeFrameExtractor:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[str, int]] = []

    async def extract_frames(self, asset: MediaAsset, count: int) -> list[bytes]:
        self.calls.append((asset.id, count))
        if self.fail:
            raise RuntimeError("frame extraction failed")
        return [b"frame"] * count


class FakeVisionProvider:
    provider_identity = "fake:vision"

    def __init__(self, scores: dict[str, float]) -> None:
        self.scores = scores

    async def analyze(
        self, frame_bytes: list[bytes], scene_context: str
    ) -> VisionAnalysisResult:
        asset_id = scene_context.rsplit("Asset: ", 1)[-1] if "Asset: " in scene_context else ""
        score = self.scores.get(asset_id, 0.9)
        return VisionAnalysisResult(
            relevance_score=score,
            scene_type="documentary",
            lighting="natural",
            dominant_colors=["blue"],
            indoors=False,
            outdoors=True,
            camera_motion="slow",
            people_present=True,
            vehicles_present=False,
            confidence=1.0,
        )


class IntentVisionProvider(FakeVisionProvider):
    """Mock vision model with per-asset semantic evidence."""

    def __init__(self, results: dict[str, VisionAnalysisResult]) -> None:
        super().__init__({})
        self.results = results
        self.contexts: list[str] = []

    async def analyze(
        self, frame_bytes: list[bytes], scene_context: str
    ) -> VisionAnalysisResult:
        self.contexts.append(scene_context)
        asset_id = scene_context.rsplit("Asset: ", 1)[-1]
        return self.results[asset_id]


@pytest.mark.asyncio
async def test_rescores_only_top_candidates():
    extractor = FakeFrameExtractor()
    service = VisionAssetScoringService(
        frame_extractor=extractor,
        vision_provider=FakeVisionProvider({}),
        frames_per_asset=2,
        top_candidates=2,
        vision_weight=1.0,
    )
    candidates = [
        ScoredAsset(_asset("a"), AssetScore(0.8)),
        ScoredAsset(_asset("b"), AssetScore(0.7)),
        ScoredAsset(_asset("c"), AssetScore(0.6)),
    ]

    results = await service.score_scene(_scene(), candidates)

    assert extractor.calls == [("a", 2), ("b", 2)]
    assert results[-1].asset.id == "c"
    assert results[-1].score.final_score == 0.6


@pytest.mark.asyncio
async def test_vision_failure_preserves_heuristic_scores():
    service = VisionAssetScoringService(
        frame_extractor=FakeFrameExtractor(fail=True),
        vision_provider=FakeVisionProvider({}),
    )
    candidate = ScoredAsset(_asset("a"), AssetScore(0.72))

    results = await service.score_scene(_scene(), [candidate])

    assert results == [candidate]


@pytest.mark.asyncio
async def test_intent_scoring_requires_mood_and_motion_evidence():
    provider = IntentVisionProvider(
        {
            "energetic": VisionAnalysisResult(
                relevance_score=0.95,
                scene_type="dynamic concert action",
                lighting="vibrant",
                dominant_colors=["red"],
                indoors=False,
                outdoors=True,
                camera_motion="fast",
                people_present=True,
                vehicles_present=False,
                confidence=0.95,
            )
        }
    )
    service = VisionAssetScoringService(FakeFrameExtractor(), provider, vision_weight=1.0)
    candidate = ScoredAsset(_asset("energetic"), AssetScore(0.50))
    intent = VisualIntent(
        "concert",
        "energetic",
        "fast-paced",
        ("text", "logo"),
        ("stage",),
        0,
        1_500,
        "hook",
        "macro-close-up",
    )

    results = await service.score_visual_intent(intent, [candidate])

    assert results[0].asset.id == "energetic"
    assert results[0].score.final_score > candidate.score.final_score
    assert "Mood: energetic" in provider.contexts[0]
    assert "Motion: fast-paced" in provider.contexts[0]
    assert "Narrative role: hook" in provider.contexts[0]
    assert "Shot type: macro-close-up" in provider.contexts[0]
    assert results[0].asset.metadata["vision_evidence"]["camera_motion"] == "fast"
    assert results[0].asset.metadata["motion_energy"] == 0.85


def test_underwater_stationary_footage_matches_reflective_steady_brief():
    analysis = VisionAnalysisResult(
        relevance_score=1.0,
        scene_type="underwater wildlife",
        lighting="natural",
        dominant_colors=["blue"],
        indoors=False,
        outdoors=True,
        camera_motion="stationary",
        people_present=False,
        vehicles_present=False,
        confidence=1.0,
    )

    assert VisionAssetScoringService._mood_match("reflective", analysis) == 1.0
    assert VisionAssetScoringService._motion_match("steady", "stationary") == 1.0


@pytest.mark.asyncio
async def test_intent_scoring_rejects_low_confidence_visuals():
    provider = IntentVisionProvider(
        {
            "weak": VisionAnalysisResult(
                relevance_score=0.20,
                scene_type="documentary",
                lighting="natural",
                dominant_colors=["blue"],
                indoors=False,
                outdoors=True,
                camera_motion="slow",
                people_present=True,
                vehicles_present=False,
                confidence=0.20,
            )
        }
    )
    service = VisionAssetScoringService(FakeFrameExtractor(), provider)
    intent = VisualIntent("concert", "energetic", "fast-paced")

    with pytest.raises(LowVisionConfidenceError, match="below the required"):
        await service.score_visual_intent(intent, [ScoredAsset(_asset("weak"), AssetScore(0.9))])


@pytest.mark.asyncio
async def test_intent_scoring_filters_unverified_candidates_from_results():
    provider = IntentVisionProvider(
        {
            "unverified": VisionAnalysisResult(
                relevance_score=0.10,
                scene_type="documentary",
                lighting="natural",
                dominant_colors=["blue"],
                indoors=False,
                outdoors=True,
                camera_motion="slow",
                people_present=True,
                vehicles_present=False,
                confidence=0.20,
            ),
            "verified": VisionAnalysisResult(
                relevance_score=0.90,
                scene_type="dynamic concert",
                lighting="vibrant",
                dominant_colors=["red"],
                indoors=False,
                outdoors=True,
                camera_motion="fast",
                people_present=True,
                vehicles_present=False,
                confidence=0.90,
            ),
        }
    )
    service = VisionAssetScoringService(FakeFrameExtractor(), provider, top_candidates=2)
    intent = VisualIntent("concert", "energetic", "fast-paced")

    results = await service.score_visual_intent(
        intent,
        [
            ScoredAsset(_asset("unverified"), AssetScore(0.95)),
            ScoredAsset(_asset("verified"), AssetScore(0.70)),
        ],
    )

    assert [result.asset.id for result in results] == ["verified"]


@pytest.mark.asyncio
async def test_intent_scoring_rejects_people_when_faces_are_forbidden():
    provider = IntentVisionProvider(
        {
            "person": VisionAnalysisResult(
                relevance_score=1.0,
                scene_type="underwater diver and octopus",
                lighting="natural",
                dominant_colors=["blue"],
                indoors=False,
                outdoors=True,
                camera_motion="steady",
                people_present=True,
                vehicles_present=False,
                confidence=1.0,
            ),
            "clean": VisionAnalysisResult(
                relevance_score=1.0,
                scene_type="underwater octopus",
                lighting="natural",
                dominant_colors=["blue"],
                indoors=False,
                outdoors=True,
                camera_motion="steady",
                people_present=False,
                vehicles_present=False,
                confidence=1.0,
            ),
        }
    )
    service = VisionAssetScoringService(
        FakeFrameExtractor(), provider, top_candidates=2
    )
    intent = VisualIntent(
        "octopus", "reflective", "steady", forbidden_concepts=("face",)
    )

    results = await service.score_visual_intent(
        intent,
        [
            ScoredAsset(_asset("person"), AssetScore(0.9)),
            ScoredAsset(_asset("clean"), AssetScore(0.8)),
        ],
    )

    assert [result.asset.id for result in results] == ["clean"]


@pytest.mark.asyncio
async def test_intent_scoring_rejects_unanalysable_candidates():
    service = VisionAssetScoringService(
        FakeFrameExtractor(fail=True),
        IntentVisionProvider({}),
    )
    intent = VisualIntent("rain", "melancholic", "slow-motion")

    with pytest.raises(VisualAssetNotFoundError, match="failed for every"):
        await service.score_visual_intent(intent, [ScoredAsset(_asset("a"), AssetScore(0.8))])


@pytest.mark.asyncio
async def test_semantic_intent_rejects_dominant_unrelated_species():
    provider = IntentVisionProvider(
        {
            "ray": VisionAnalysisResult(
                relevance_score=0.95,
                scene_type="underwater ray",
                lighting="blue",
                dominant_colors=["blue"],
                indoors=False,
                outdoors=True,
                camera_motion="steady",
                people_present=False,
                vehicles_present=False,
                confidence=0.98,
                dominant_subject="stingray",
                observed_subjects=["stingray"],
            ),
            "octopus": VisionAnalysisResult(
                relevance_score=0.90,
                scene_type="underwater octopus",
                lighting="blue",
                dominant_colors=["blue"],
                indoors=False,
                outdoors=True,
                camera_motion="steady",
                people_present=False,
                vehicles_present=False,
                confidence=0.95,
                dominant_subject="octopus",
                observed_subjects=["octopus"],
            ),
        }
    )
    service = VisionAssetScoringService(FakeFrameExtractor(), provider, top_candidates=2)
    intent = VisualIntent(
        "octopus",
        "reflective",
        "steady",
        required_subjects=("octopuses",),
        forbidden_dominant_subjects=("ray", "stingray", "shark"),
    )

    results = await service.score_visual_intent(
        intent,
        [
            ScoredAsset(_asset("ray"), AssetScore(0.95)),
            ScoredAsset(_asset("octopus"), AssetScore(0.80)),
        ],
    )

    assert [result.asset.id for result in results] == ["octopus"]


@pytest.mark.asyncio
async def test_subject_presence_cannot_be_inferred_from_underwater_setting_alone():
    provider = IntentVisionProvider(
        {
            "ocean": VisionAnalysisResult(
                relevance_score=1.0,
                scene_type="underwater reef",
                lighting="blue",
                dominant_colors=["blue"],
                indoors=False,
                outdoors=True,
                camera_motion="steady",
                people_present=False,
                vehicles_present=False,
                confidence=1.0,
                dominant_subject="coral reef",
                observed_subjects=["coral", "small fish"],
            )
        }
    )
    service = VisionAssetScoringService(FakeFrameExtractor(), provider)
    intent = VisualIntent(
        "octopus",
        "reflective",
        "steady",
        required_subjects=("octopus",),
    )

    with pytest.raises(VisualAssetNotFoundError, match="failed for every"):
        await service.score_visual_intent(
            intent,
            [ScoredAsset(_asset("ocean"), AssetScore(0.99))],
        )
