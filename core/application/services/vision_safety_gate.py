import logging
from core.domain.entities.media_asset import MediaAsset
from core.application.services.vision_asset_scoring_service import VisionAssetScoringService

logger = logging.getLogger(__name__)

class VisionSafetyGate:
    """
    Quality gate that utilizes Vision AI to evaluate the semantic relevance
    of an asset to a scene. If the score is below the threshold, it is rejected.
    """
    def __init__(self, vision_scoring_service: VisionAssetScoringService, relevance_threshold: float = 0.70):
        self.vision_scoring_service = vision_scoring_service
        self.relevance_threshold = relevance_threshold

    async def evaluate(self, asset: MediaAsset, scene_or_intent, context_text: str = "") -> bool:
        """
        Asks the Vision AI to score the semantic relevance of the asset.
        Returns True if the asset passes the gate, False if it is rejected.
        """
        logger.info(f"Evaluating asset {asset.provider_asset_id} through Vision Safety Gate...")

        # Determine if we are scoring a Scene or a VisualIntent depending on the stage of the pipeline
        if hasattr(self.vision_scoring_service, 'score_visual_intent') and hasattr(scene_or_intent, 'primary_keyword'):
            # Fake a ScoredAsset list
            from core.domain.value_objects.asset_score import AssetScore, ScoredAsset
            fake_scored = [ScoredAsset(asset=asset, score=AssetScore(final_score=0.5))]
            res = await self.vision_scoring_service.score_visual_intent(scene_or_intent, fake_scored)
            score = res[0].adjusted_score
        else:
            score = await self.vision_scoring_service.score_asset(
                asset=asset,
                scene=scene_or_intent,
                context_text=context_text
            )

        passed = score >= self.relevance_threshold
        if passed:
            logger.info(f"✅ Safety Gate PASSED: Score {score:.2f} >= {self.relevance_threshold}")
        else:
            logger.warning(f"❌ Safety Gate FAILED: Score {score:.2f} < {self.relevance_threshold}. Asset rejected.")

        return passed
