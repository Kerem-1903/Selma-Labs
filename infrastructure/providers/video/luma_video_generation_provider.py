import httpx
import logging
import asyncio
from core.domain.ports.video_generation_port import VideoGenerationPort
from core.domain.value_objects.video_generation_request import VideoGenerationRequest
from core.domain.entities.media_asset import MediaAsset

logger = logging.getLogger(__name__)

class LumaVideoGenerationProvider(VideoGenerationPort):
    """
    Integration for Luma Dream Machine API to generate high-quality B-Roll.
    """
    def __init__(self, api_key: str):
        self.api_key = api_key

    @property
    def name(self) -> str:
        return "luma_dream_machine"

    async def generate_video(self, request: VideoGenerationRequest) -> MediaAsset:
        # For legacy compatibility, extract prompt from constraints if present, otherwise build a generic one.
        prompt = request.generation_constraints.get("prompt", "A cinematic scene")

        logger.info(f"Triggering Text-to-Video generation using Luma for prompt: '{prompt[:50]}...'")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        payload = {
            "prompt": prompt,
            "aspect_ratio": "9:16",
            "loop": False
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            # 1. Start generation
            response = await client.post(
                "https://api.lumalabs.ai/dream-machine/v1/generations",
                headers=headers,
                json=payload
            )
            response.raise_from_status()
            job_data = response.json()
            generation_id = job_data["id"]

            # 2. Poll for completion
            max_retries = 60 # 5 minutes maximum
            retries = 0
            while retries < max_retries:
                poll_resp = await client.get(
                    f"https://api.lumalabs.ai/dream-machine/v1/generations/{generation_id}",
                    headers=headers
                )
                poll_resp.raise_from_status()
                status_data = poll_resp.json()

                state = status_data.get("state")
                if state == "completed":
                    video_url = status_data["assets"]["video"]
                    break
                elif state == "failed":
                    raise Exception(f"Luma generation failed for prompt: {prompt}")

                await asyncio.sleep(5.0)
                retries += 1

            if retries >= max_retries:
                raise Exception(f"Luma generation timed out for prompt: {prompt}")

        return MediaAsset(
            id="luma:" + generation_id,
            provider="luma_dream_machine",
            provider_asset_id=generation_id,
            media_type="video",
            original_url=video_url,
            width=1080,
            height=1920,
            duration_seconds=request.target_duration_seconds,
            fps=30.0
        )
