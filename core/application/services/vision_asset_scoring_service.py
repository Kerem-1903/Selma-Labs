from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass, replace

from core.application.services.asset_diversity_service import AssetDiversityService
from core.domain.exceptions import LowVisionConfidenceError, VisualAssetNotFoundError
from core.domain.ports.frame_extraction_port import FrameExtractionPort
from core.domain.ports.vision_analysis_port import VisionAnalysisPort
from core.domain.value_objects.asset_score import AssetScore
from core.domain.value_objects.scene import Scene
from core.domain.value_objects.scored_asset import ScoredAsset
from core.domain.value_objects.vision_analysis_result import VisionAnalysisResult
from core.domain.value_objects.visual_intent import VisualIntent

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _IntentScoreOutcome:
    """Internal evidence retained until the strict quality gate is evaluated."""

    candidate: ScoredAsset
    confidence_score: float


class VisionAssetScoringService:
    """Rescore only the strongest heuristic candidates with AI Vision."""

    def __init__(
        self,
        frame_extractor: FrameExtractionPort,
        vision_provider: VisionAnalysisPort,
        frames_per_asset: int = 3,
        top_candidates: int = 3,
        max_concurrency: int = 2,
        vision_weight: float = 0.65,
        minimum_intent_confidence: float = 0.60,
    ) -> None:
        if frames_per_asset <= 0:
            raise ValueError("frames_per_asset must be greater than zero")
        if top_candidates <= 0:
            raise ValueError("top_candidates must be greater than zero")
        if max_concurrency <= 0:
            raise ValueError("max_concurrency must be greater than zero")
        if not 0.0 <= vision_weight <= 1.0:
            raise ValueError("vision_weight must be between 0.0 and 1.0")
        if not 0.0 <= minimum_intent_confidence <= 1.0:
            raise ValueError("minimum_intent_confidence must be between 0.0 and 1.0")
        self._frame_extractor = frame_extractor
        self._vision_provider = vision_provider
        self._frames_per_asset = frames_per_asset
        self._top_candidates = top_candidates
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._vision_weight = vision_weight
        self._minimum_intent_confidence = minimum_intent_confidence

    async def score_scene(
        self, scene: Scene, candidates: Sequence[ScoredAsset]
    ) -> list[ScoredAsset]:
        ordered = sorted(
            candidates,
            key=lambda candidate: candidate.score.final_score,
            reverse=True,
        )
        selected = ordered[: self._top_candidates]
        rescored = await asyncio.gather(
            *(self._score_candidate(scene, candidate) for candidate in selected)
        )
        by_asset_id = {candidate.asset.id: candidate for candidate in rescored}
        merged = [by_asset_id.get(candidate.asset.id, candidate) for candidate in ordered]
        return sorted(
            merged,
            key=lambda candidate: candidate.score.final_score,
            reverse=True,
        )

    async def score_visual_intent(
        self,
        intent: VisualIntent,
        candidates: Sequence[ScoredAsset],
    ) -> list[ScoredAsset]:
        """Score assets against mood and motion, then enforce a strict gate.

        Unlike the legacy ``score_scene`` method, an unavailable vision model
        never silently falls back to keyword ranking. Autonomous music videos
        must have positive visual evidence before they reach rendering.

        Raises:
            VisualAssetNotFoundError: No candidate could be visually analysed.
            LowVisionConfidenceError: The strongest analysed candidate does not
                reach the configured confidence threshold.
        """
        if not candidates:
            raise VisualAssetNotFoundError("No visual candidates were supplied.")

        ordered = sorted(
            candidates,
            key=lambda candidate: candidate.score.final_score,
            reverse=True,
        )
        outcomes = await asyncio.gather(
            *(
                self._score_intent_candidate(intent, candidate)
                for candidate in ordered[: self._top_candidates]
            )
        )
        analysed = [outcome for outcome in outcomes if outcome is not None]
        if not analysed:
            raise VisualAssetNotFoundError(
                "Vision analysis failed for every visual candidate."
            )

        accepted = [
            outcome
            for outcome in analysed
            if outcome.confidence_score >= self._minimum_intent_confidence
        ]
        if not accepted:
            best_outcome = max(
                analysed,
                key=lambda outcome: outcome.confidence_score,
            )
            raise LowVisionConfidenceError(
                "Best visual candidate confidence "
                f"({best_outcome.confidence_score:.2f}) is below the required "
                f"{self._minimum_intent_confidence:.2f}."
            )
        return sorted(
            [outcome.candidate for outcome in accepted],
            key=lambda candidate: candidate.score.final_score,
            reverse=True,
        )

    async def score_for_visual_intent(
        self,
        intent: VisualIntent,
        candidates: Sequence[ScoredAsset],
    ) -> list[ScoredAsset]:
        """Compatibility-friendly alias for intent-first orchestration code."""
        return await self.score_visual_intent(intent, candidates)

    async def _score_candidate(
        self, scene: Scene, candidate: ScoredAsset
    ) -> ScoredAsset:
        try:
            async with self._semaphore:
                frames = await self._frame_extractor.extract_frames(
                    candidate.asset, self._frames_per_asset
                )
                if not frames:
                    return candidate
                analysis = await self._vision_provider.analyze(
                    frames,
                    self._scene_context(scene),
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "Vision scoring failed for asset '%s'; using heuristic score.",
                candidate.asset.id,
            )
            return candidate

        base_score = self._clamp(candidate.score.final_score)
        confidence = self._clamp(analysis.confidence)
        relevance = self._clamp(analysis.relevance_score)
        confidence_adjusted_vision = relevance * confidence + base_score * (1.0 - confidence)
        final_score = (
            base_score * (1.0 - self._vision_weight)
            + confidence_adjusted_vision * self._vision_weight
        )
        return ScoredAsset(
            asset=candidate.asset,
            score=AssetScore(final_score=self._clamp(final_score)),
        )

    async def _score_intent_candidate(
        self,
        intent: VisualIntent,
        candidate: ScoredAsset,
    ) -> _IntentScoreOutcome | None:
        """Return a candidate only when vision supplied usable evidence."""
        try:
            async with self._semaphore:
                frames = await self._frame_extractor.extract_frames(
                    candidate.asset, self._frames_per_asset
                )
                if not frames:
                    return None
                analysis = await self._vision_provider.analyze(
                    frames,
                    self._intent_context(intent, candidate),
                )
                if self._violates_forbidden_concepts(intent, analysis):
                    return None
                if not self._required_subject_is_present(intent, analysis):
                    return None
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "Vision scoring failed for asset '%s'; rejecting it from intent scoring.",
                candidate.asset.id,
            )
            return None

        base_score = self._clamp(candidate.score.final_score)
        model_confidence = self._clamp(analysis.confidence)
        semantic_match = self._intent_match_score(intent, analysis)
        vision_score = semantic_match * model_confidence + base_score * (
            1.0 - model_confidence
        )
        final_score = (
            base_score * (1.0 - self._vision_weight)
            + vision_score * self._vision_weight
        )
        evidence = analysis.to_dict()
        metadata = {
            **candidate.asset.metadata,
            "vision_evidence": evidence,
            "perceptual_hashes": list(
                AssetDiversityService.fingerprint_frames(frames)
            ),
            "subject_pose": (
                analysis.subject_pose
                or " ".join(
                    [analysis.dominant_subject, *analysis.observed_actions[:1]]
                ).strip()
            ),
            "camera_angle": analysis.camera_angle or intent.shot_type,
            "background_signature": (
                analysis.background_signature
                or " ".join(
                    [analysis.scene_type, *analysis.dominant_colors[:2]]
                ).strip()
            ),
            "motion_energy": self._motion_energy(analysis),
        }
        rescored = ScoredAsset(
            asset=replace(candidate.asset, metadata=metadata),
            score=AssetScore(final_score=self._clamp(final_score)),
        )
        # Confidence is deliberately not the heuristic score. It means
        # "the vision model confidently observed mood/motion relevant to this
        # intent", preventing a highly ranked keyword result from bypassing
        # the autonomous quality gate.
        return _IntentScoreOutcome(
            candidate=rescored,
            confidence_score=self._clamp(model_confidence * semantic_match),
        )

    @staticmethod
    def _violates_forbidden_concepts(
        intent: VisualIntent, analysis: VisionAnalysisResult
    ) -> bool:
        forbidden = set(intent.forbidden_concepts)
        if analysis.people_present and forbidden.intersection({"face", "person", "people"}):
            return True
        if analysis.vehicles_present and forbidden.intersection({"vehicle", "vehicles"}):
            return True
        if analysis.text_present and forbidden.intersection({"text", "caption", "watermark"}):
            return True
        if analysis.logo_present and forbidden.intersection({"logo", "watermark"}):
            return True
        dominant = analysis.dominant_subject.casefold().strip()
        observed = " ".join(analysis.observed_subjects).casefold()
        if any(
            concept.casefold() in dominant or concept.casefold() in observed
            for concept in intent.forbidden_dominant_subjects
        ):
            return True
        return False

    @staticmethod
    def _required_subject_is_present(
        intent: VisualIntent,
        analysis: VisionAnalysisResult,
    ) -> bool:
        if not intent.required_subjects:
            return True
        primary_required = intent.required_subjects[0].casefold()
        observed = " ".join(
            [
                analysis.dominant_subject,
                analysis.scene_type,
                *analysis.observed_subjects,
            ]
        ).casefold()
        stems = {primary_required}
        if primary_required.endswith("es"):
            stems.add(primary_required[:-2])
        if primary_required.endswith("s"):
            stems.add(primary_required[:-1])
        return any(stem and stem in observed for stem in stems)

    @staticmethod
    def _scene_context(scene: Scene) -> str:
        return (
            f"Narration: {scene.narration}\n"
            f"Keywords: {', '.join(scene.search_keywords)}\n"
            f"Location: {scene.location or 'unspecified'}\n"
            f"Mood: {scene.mood or 'unspecified'}"
        )

    @staticmethod
    def _intent_context(intent: VisualIntent, candidate: ScoredAsset) -> str:
        """Build a provider-neutral vision prompt for a visual brief."""
        forbidden = ", ".join(intent.forbidden_concepts) or "none"
        return (
            f"Primary keyword: {intent.primary_keyword}\n"
            f"Supporting keywords: {', '.join(intent.secondary_keywords) or 'none'}\n"
            f"Mood: {intent.mood}\n"
            f"Motion: {intent.motion_type}\n"
            f"Narrative role: {intent.narrative_role}\n"
            f"Shot type: {intent.shot_type}\n"
            f"Narration evidence: {intent.narration_text or 'none'}\n"
            f"Visual job: {intent.visual_job}\n"
            f"Required subjects: {', '.join(intent.required_subjects) or 'none'}\n"
            f"Required actions: {', '.join(intent.required_actions) or 'none'}\n"
            f"Required relations: {', '.join(intent.required_relations) or 'none'}\n"
            f"Forbidden dominant subjects: "
            f"{', '.join(intent.forbidden_dominant_subjects) or 'none'}\n"
            f"Explanation mode: {intent.explanation_mode}\n"
            f"Timeline: {intent.start_ms}-{intent.end_ms} ms\n"
            f"Forbidden concepts: {forbidden}\n"
            f"Asset: {candidate.asset.id}"
        )

    @classmethod
    def _intent_match_score(
        cls,
        intent: VisualIntent,
        analysis: VisionAnalysisResult,
    ) -> float:
        """Combine generic relevance with deterministic mood/motion matching."""
        relevance = cls._clamp(analysis.relevance_score)
        mood_match = cls._mood_match(intent.mood, analysis)
        motion_match = cls._motion_match(intent.motion_type, analysis.camera_motion)
        subject_match = 1.0 if cls._required_subject_is_present(intent, analysis) else 0.0
        action_relation_match = cls._action_relation_match(intent, analysis)
        return cls._clamp(
            relevance * 0.35
            + subject_match * 0.30
            + mood_match * 0.15
            + motion_match * 0.10
            + action_relation_match * 0.10
        )

    @staticmethod
    def _action_relation_match(
        intent: VisualIntent,
        analysis: VisionAnalysisResult,
    ) -> float:
        requirements = [*intent.required_actions, *intent.required_relations]
        if not requirements:
            return 1.0
        observed = " ".join(
            [*analysis.observed_actions, *analysis.observed_relations]
        ).casefold()
        matches = sum(
            1 for requirement in requirements if requirement.casefold() in observed
        )
        # An explanatory overlay may supply an internal action that stock footage
        # cannot reveal. Reward observed evidence without rejecting the subject-safe
        # asset when the overlay is the declared explanation path.
        if intent.explanatory_required and not observed:
            return 0.5
        return matches / len(requirements)

    @staticmethod
    def _mood_match(mood: str, analysis: VisionAnalysisResult) -> float:
        """Infer broad cinematic mood from portable vision-analysis fields."""
        observed = " ".join(
            [analysis.scene_type, analysis.lighting, *analysis.dominant_colors]
        ).lower()
        vocabulary = {
            "energetic": ("energetic", "action", "concert", "sport", "vibrant", "dynamic"),
            "melancholic": ("melancholic", "dark", "blue", "rain", "moody", "low-key"),
            "reflective": (
                "reflective", "calm", "warm", "nature", "sunset", "quiet",
                "underwater", "ocean", "marine", "blue",
            ),
            "dark": ("dark", "night", "moody", "low-key"),
            "nostalgic": ("nostalgic", "vintage", "film", "warm"),
        }
        terms = vocabulary.get(mood, (mood,))
        return 1.0 if any(term in observed for term in terms) else 0.0

    @staticmethod
    def _motion_match(expected_motion: str, observed_motion: str) -> float:
        """Map provider-specific motion labels to a small domain vocabulary."""
        observed = (observed_motion or "").lower()
        if expected_motion == "fast-paced":
            terms = ("fast", "rapid", "dynamic", "quick", "handheld")
        elif expected_motion == "slow-motion":
            terms = ("slow", "static", "gentle", "still", "smooth")
        else:
            terms = ("steady", "smooth", "static", "slow", "stationary", "none")
        return 1.0 if any(term in observed for term in terms) else 0.0

    @classmethod
    def _motion_energy(cls, analysis: VisionAnalysisResult) -> float:
        if analysis.motion_energy is not None:
            return cls._clamp(float(analysis.motion_energy))
        observed = analysis.camera_motion.casefold()
        if any(term in observed for term in ("fast", "dynamic", "rapid", "tracking")):
            return 0.85
        if any(term in observed for term in ("static", "stationary", "locked")):
            return 0.15
        if any(term in observed for term in ("slow", "gentle", "minimal")):
            return 0.30
        return 0.55

    @staticmethod
    def _clamp(value: float) -> float:
        return max(0.0, min(1.0, float(value)))
