import logging
import random
from core.domain.ports.video_source_port import VideoSourcePort
from core.domain.entities.media_asset import MediaAsset
from infrastructure.providers.video.pexels_provider import PexelsProvider
from infrastructure.providers.video.comfyui_video_provider import ComfyUIVideoProvider

logger = logging.getLogger(__name__)

class HybridBRollProvider(VideoSourcePort):
    """
    Intelligently blends AI-generated video (via ComfyUI) with real
    Stock B-Rolls (via Pexels) based on the query or random chance.
    """

    def __init__(self, pexels_key: str):
        self.pexels = PexelsProvider(api_key=pexels_key)
        self.ai = ComfyUIVideoProvider(api_url="http://127.0.0.1:8188", workflow_path="assets/comfyui_workflow.json")

    @property
    def name(self) -> str:
        return "Hybrid_AI_Broll"

    async def search(self, query: str, max_results: int) -> list[MediaAsset]:
        logger.info(f"Hybrid Provider processing query: '{query}'")
        results = []

        # Decide if this specific scene should use Real B-Roll or AI Generation
        # A simple heuristic: if query contains "real", "nature", "people", "stock" use Pexels
        # Otherwise, 50/50 chance to blend
        stock_keywords = ["real", "nature", "people", "city", "ocean", "landscape", "stock"]

        use_stock = any(k in query.lower() for k in stock_keywords) or random.random() > 0.5

        if use_stock:
            logger.info("Hybrid Engine decided: Real B-Roll (Pexels)")
            try:
                stock_results = await self.pexels.search(query, max_results)
                if stock_results:
                    results.extend(stock_results)
            except Exception as e:
                logger.warning(f"Stock search failed, falling back to AI. Error: {e}")
                use_stock = False

        if not results: # Fallback to AI if stock decision was false or yielded empty
            logger.info("Hybrid Engine decided: AI Generation (ComfyUI)")
            try:
                # VideoGenerationPort (Comfy) doesn't exactly map to search, so we mock a quick generation
                # In real scenario, it would trigger a queue and wait.
                # To satisfy VideoSourcePort, we generate 1 asset based on the query.
                # Since Comfy generation is slow, we might return a mock asset for testing unless strictly required.
                asset = await self.ai.generate_video(prompt=query)
                results.append(asset)
            except Exception as e:
                 logger.error(f"AI Generation failed: {e}")

        return results

    async def download(self, asset: MediaAsset) -> bytes:
        if asset.provider == "pexels":
            return await self.pexels.download(asset)
        elif asset.provider == "comfyui":
            # the original_url contains the local path downloaded by ComfyUIVideoProvider
            with open(asset.original_url, "rb") as f:
                return f.read()
        return b""
