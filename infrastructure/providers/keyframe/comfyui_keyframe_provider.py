import asyncio
import json
import logging
import uuid
import base64
import os
import aiohttp

from core.domain.exceptions import ProviderError
from core.domain.ports.keyframe_generation_port import KeyframeGenerationPort
from core.domain.value_objects.generated_keyframe import GeneratedKeyframe
from core.domain.value_objects.keyframe_generation_request import KeyframeGenerationRequest

logger = logging.getLogger(__name__)

class ComfyUIKeyframeProvider(KeyframeGenerationPort):
    def __init__(self, api_url: str, workflow_path: str):
        self.api_url = api_url.rstrip("/")
        self.workflow_path = workflow_path

    @property
    def name(self) -> str:
        return "comfyui_keyframe"

    async def _queue_prompt(self, workflow: dict) -> str:
        """Sends the workflow to ComfyUI and returns the prompt_id."""
        payload = {"prompt": workflow}
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(f"{self.api_url}/prompt", json=payload) as response:
                    if response.status != 200:
                        text = await response.text()
                        raise ProviderError(f"ComfyUI queue failed: {text}")
                    data = await response.json()
                    return data["prompt_id"]
            except aiohttp.ClientError as e:
                raise ProviderError(f"ComfyUI connection error: {e}")

    async def _wait_for_completion(self, prompt_id: str, timeout: int = 300) -> dict:
        """Polls ComfyUI history to get the output filenames with a timeout."""
        start_time = asyncio.get_event_loop().time()
        async with aiohttp.ClientSession() as session:
            while True:
                if asyncio.get_event_loop().time() - start_time > timeout:
                    raise ProviderError(f"ComfyUI generation timed out after {timeout} seconds for prompt_id: {prompt_id}")
                try:
                    async with session.get(f"{self.api_url}/history/{prompt_id}") as response:
                        if response.status == 200:
                            data = await response.json()
                            if prompt_id in data:
                                return data[prompt_id]
                except aiohttp.ClientError as e:
                    logger.warning(f"Error polling ComfyUI: {e}. Retrying...")
                await asyncio.sleep(1.0)

    async def _download_image(self, filename: str, subfolder: str, folder_type: str) -> bytes:
        """Downloads the generated image from ComfyUI to memory."""
        params = {"filename": filename, "subfolder": subfolder, "type": folder_type}
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.api_url}/view", params=params) as response:
                if response.status != 200:
                    raise ProviderError("Failed to download image from ComfyUI")
                return await response.read()

    async def generate_keyframe(self, request: KeyframeGenerationRequest) -> GeneratedKeyframe:
        try:
            with open(self.workflow_path, "r") as f:
                workflow = json.load(f)
        except FileNotFoundError:
            raise ProviderError(f"ComfyUI workflow file not found at {self.workflow_path}")
        except json.JSONDecodeError:
            raise ProviderError(f"ComfyUI workflow file at {self.workflow_path} is invalid JSON")

        prompt_text = request.visual_constraints.get("prompt")
        if not prompt_text:
            # P1: A5 requests may not have a "prompt", fallback to generic scene
            prompt_text = "A cinematic scene"

        # Inject prompt into the first CLIPTextEncode node
        found_node = False
        for node_id, node_data in workflow.items():
            if node_data.get("class_type") == "CLIPTextEncode":
                if not found_node or node_data["inputs"].get("text", "") == "":
                    node_data["inputs"]["text"] = prompt_text
                    found_node = True
                    break

        if not found_node:
            logger.warning("Could not find a CLIPTextEncode node in the ComfyUI workflow to inject the prompt.")

        # P1: Inject character references into LoadImage nodes if any
        if request.reference_storage_keys:
            ref_idx = 0
            for node_id, node_data in workflow.items():
                if node_data.get("class_type") == "LoadImage" and ref_idx < len(request.reference_storage_keys):
                    # We assume the storage keys are directly accessible or we're using a convention.
                    # For now, we'll just inject the key (e.g., path/to/image.png)
                    node_data["inputs"]["image"] = request.reference_storage_keys[ref_idx]
                    ref_idx += 1

        try:
            prompt_id = await self._queue_prompt(workflow)
            result = await self._wait_for_completion(prompt_id)

            outputs = result.get("outputs", {})
            image_filename = None
            subfolder = ""
            folder_type = ""

            for node_id, node_output in outputs.items():
                if "images" in node_output:
                    file_info = node_output["images"][0]
                    image_filename = file_info["filename"]
                    subfolder = file_info.get("subfolder", "")
                    folder_type = file_info.get("type", "output")
                    break

            if not image_filename:
                raise ProviderError("No image output found in ComfyUI history result.")

            image_bytes = await self._download_image(image_filename, subfolder, folder_type)

            return GeneratedKeyframe(
                image_bytes=image_bytes,
                content_type="image/png" if image_filename.endswith(".png") else "image/jpeg",
                width=request.width,
                height=request.height,
                provider_asset_id=image_filename,
            )

        except ProviderError:
            raise
        except Exception as e:
            logger.error(f"ComfyUI generation failed: {e}")
            raise ProviderError(f"ComfyUI Error: {str(e)}")
