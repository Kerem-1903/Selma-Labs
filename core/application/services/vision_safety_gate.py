import logging
from core.domain.entities.media_asset import MediaAsset
from core.domain.value_objects.scene import Scene
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

    async def evaluate(self, asset: MediaAsset, scene, context_text: str = "") -> bool:
        """
        Asks the Vision AI to score the semantic relevance of the asset.
        Returns True if the asset passes the gate, False if it is rejected.
        """
        logger.info(f"Evaluating asset {asset.provider_asset_id} through Vision Safety Gate...")

        # We leverage the existing scoring infrastructure which extracts frames and hits the Vision AI.
        # It typically returns a score between 0.0 and 1.0 based on narrative/visual alignment.
        score = await self.vision_scoring_service.score_asset(
            asset=asset,
            scene=scene,
            context_text=context_text
        )

        passed = score >= self.relevance_threshold
        if passed:
            logger.info(f"✅ Safety Gate PASSED: Score {score:.2f} >= {self.relevance_threshold}")
        else:
            logger.warning(f"❌ Safety Gate FAILED: Score {score:.2f} < {self.relevance_threshold}. Asset rejected.")

        return passed
