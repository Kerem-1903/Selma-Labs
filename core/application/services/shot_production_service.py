from typing import List, Optional
import logging
from core.domain.entities.shot_contract import ShotContract
from core.domain.entities.media_asset import MediaAsset
from core.domain.value_objects.video_generation_request import VideoGenerationRequest
from core.domain.value_objects.render_profile import RenderProfile
from core.domain.ports.video_generation_port import VideoGenerationPort

logger = logging.getLogger(__name__)

class ShotProductionService:
    """
    A8.1 Pilot Production: Orchestrates the generation of video shots with retry logic and basic cost tracking.
    """
    def __init__(self, video_generator: VideoGenerationPort, max_retries: int = 2):
        self._video_generator = video_generator
        self.max_retries = max_retries
        # Simple tracking: map shot_contract_id -> number of attempts
        self.cost_tracking = {}

    async def produce_shot(
        self,
        shot_contract: ShotContract,
        target_duration: float,
        profile: RenderProfile = RenderProfile.BALANCED,
        reference_images: Optional[List[str]] = None
    ) -> MediaAsset:
        """
        Attempts to generate a video for a shot contract.
        Will retry up to max_retries if generation fails.
        Tracks the number of attempts for basic cost analysis.
        """
        if reference_images is None:
            reference_images = []

        request = VideoGenerationRequest(
            shot_contract_id=shot_contract.id,
            target_duration_seconds=target_duration,
            reference_image_keys=reference_images,
            render_profile=profile
        )

        attempts = 0
        last_exception = None

        while attempts <= self.max_retries:
            attempts += 1
            self.cost_tracking[shot_contract.id] = self.cost_tracking.get(shot_contract.id, 0) + 1

            try:
                asset = await self._video_generator.generate_video(request)
                logger.info(f"Shot {shot_contract.id} generated successfully on attempt {attempts}.")
                return asset
            except Exception as e:
                logger.warning(f"Shot {shot_contract.id} generation failed on attempt {attempts}: {str(e)}")
                last_exception = e

        logger.error(f"Shot {shot_contract.id} failed after {attempts} attempts.")
        raise RuntimeError(f"Shot production failed after {self.max_retries} retries: {str(last_exception)}")

    def get_shot_cost(self, shot_contract_id: str) -> int:
        """Returns the number of generation attempts for a given shot."""
        return self.cost_tracking.get(shot_contract_id, 0)
