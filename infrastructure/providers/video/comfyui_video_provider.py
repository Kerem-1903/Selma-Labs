import aiohttp
import asyncio
import logging
import json
import uuid
import os
from core.domain.ports.video_generation_port import VideoGenerationPort
from core.domain.entities.media_asset import MediaAsset
from core.domain.exceptions import ProviderError

logger = logging.getLogger(__name__)

class ComfyUIVideoProvider(VideoGenerationPort):
    """
    Connects to a local or remote ComfyUI instance to generate AI videos (Text-to-Video).
    It uses a predefined workflow JSON where the text prompt node is dynamically updated.
    """

    def __init__(self, api_url: str = "http://127.0.0.1:8188", workflow_path: str = "assets/comfyui_workflow.json", output_dir: str = "output/comfyui"):
        self.api_url = api_url.rstrip('/')
        self.workflow_path = workflow_path
        self.output_dir = output_dir
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

    @property
    def name(self) -> str:
        return "ComfyUI"

    async def _queue_prompt(self, workflow: dict) -> str:
        """Sends the workflow to ComfyUI and returns the prompt_id."""
        payload = {"prompt": workflow}
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.api_url}/prompt", json=payload) as response:
                if response.status != 200:
                    text = await response.text()
                    raise ProviderError(f"ComfyUI queue failed: {text}")
                data = await response.json()
                return data["prompt_id"]

    async def _wait_for_completion(self, prompt_id: str) -> dict:
        """Polls ComfyUI history to get the output filenames."""
        async with aiohttp.ClientSession() as session:
            while True:
                async with session.get(f"{self.api_url}/history/{prompt_id}") as response:
                    if response.status == 200:
                        data = await response.json()
                        if prompt_id in data:
                            # Workflow finished
                            return data[prompt_id]
                await asyncio.sleep(2.0)

    async def _download_video(self, filename: str, subfolder: str, folder_type: str) -> str:
        """Downloads the generated video from ComfyUI to local storage."""
        params = {"filename": filename, "subfolder": subfolder, "type": folder_type}

        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.api_url}/view", params=params) as response:
                if response.status != 200:
                    raise ProviderError("Failed to download video from ComfyUI")

                content = await response.read()
                local_path = os.path.join(self.output_dir, filename)
                with open(local_path, "wb") as f:
                    f.write(content)
                return local_path

    async def generate_video(
        self,
        prompt: str,
        duration_seconds: float = 5.0,
        image_path: str | None = None,
        video_path: str | None = None,
    ) -> MediaAsset:
        logger.info(f"Generating video with ComfyUI. Prompt: '{prompt}'")

        try:
            with open(self.workflow_path, "r") as f:
                workflow = json.load(f)
        except FileNotFoundError:
            raise ProviderError(f"ComfyUI workflow file not found at {self.workflow_path}")

                # --- DYNAMIC V2V / I2V INJECTION ---
        # If the user selected V2V/I2V, we must also inject their source media path.
        # Assuming node "10" is a LoadImage or LoadVideo node in the specific V2V workflow.
        # This will look at the global settings to see if V2V is active and use the first user asset.
        from config.settings import get_settings
        settings = get_settings()
        if hasattr(settings, "comfyui_mode") and settings.comfyui_mode == "v2v":
            upload_dir = "output/user_uploads/videos"
            if os.path.exists(upload_dir):
                # Sort files by creation time to get the most recently uploaded one instead of arbitrary order
                files = [f for f in os.listdir(upload_dir) if f.endswith(('.mp4', '.mov'))]
                if files:
                    files.sort(key=lambda x: os.path.getmtime(os.path.join(upload_dir, x)), reverse=True)
                    source_video = os.path.join(upload_dir, files[0])
                    for node_id, node_data in workflow.items():
                        if node_data.get("class_type") in ["LoadVideo", "VHS_LoadVideo"]:
                            node_data["inputs"]["video"] = source_video
                            logger.info(f"Injected source video {source_video} into V2V workflow.")
                            break

        if hasattr(settings, "comfyui_mode") and settings.comfyui_mode == "i2v":
            if hasattr(settings, "i2v_image_path") and settings.i2v_image_path:
                source_image = settings.i2v_image_path
                for node_id, node_data in workflow.items():
                    if node_data.get("class_type") in ["LoadImage"]:
                        node_data["inputs"]["image"] = source_image
                        logger.info(f"Injected source image {source_image} into I2V workflow.")
                        break

        # --- DYNAMIC PROMPT INJECTION ---
        # Note: ComfyUI workflows have node IDs (e.g., "6", "15").
        # You MUST edit this section to match your specific workflow's Text Prompt Node ID.
        # Here we assume node "6" is a CLIPTextEncode node and has the "text" field.
        found_node = False
        for node_id, node_data in workflow.items():
            if node_data.get("class_type") == "CLIPTextEncode":
                # Inject the prompt
                node_data["inputs"]["text"] = prompt
                found_node = True
                break # We just update the first text encoder we find for this example

        if not found_node:
            logger.warning("Could not find a CLIPTextEncode node in the ComfyUI workflow to inject the prompt.")

        if image_path or video_path:
            input_classes = {"LoadImage"} if image_path else {"LoadVideo", "VHS_LoadVideo"}
            input_value = os.path.basename(image_path or video_path or "")
            for node_data in workflow.values():
                if node_data.get("class_type") in input_classes:
                    field = "image" if image_path else "video"
                    node_data.setdefault("inputs", {})[field] = input_value
                    break
            else:
                expected = "LoadImage" if image_path else "LoadVideo/VHS_LoadVideo"
                raise ProviderError(f"ComfyUI workflow has no {expected} node for the selected input.")

        try:
            # 1. Queue it
            prompt_id = await self._queue_prompt(workflow)
            logger.info(f"ComfyUI Prompt queued. ID: {prompt_id}. Waiting for generation (this may take minutes)...")

            # 2. Wait
            result = await self._wait_for_completion(prompt_id)

            # 3. Extract output (assuming a VideoCombine node saves an mp4)
            outputs = result.get("outputs", {})
            video_filename = None
            subfolder = ""
            folder_type = ""

            for node_id, node_output in outputs.items():
                if "gifs" in node_output: # VideoCombine often puts mp4s in 'gifs' array
                    file_info = node_output["gifs"][0]
                    video_filename = file_info["filename"]
                    subfolder = file_info.get("subfolder", "")
                    folder_type = file_info.get("type", "output")
                    break

            if not video_filename:
                raise ProviderError("No video output found in ComfyUI history result.")

            # 4. Download it locally
            logger.info(f"Video generated: {video_filename}. Downloading...")
            local_path = await self._download_video(video_filename, subfolder, folder_type)

            # 5. Return MediaAsset
            return MediaAsset(
                id=str(uuid.uuid4()),
                provider="comfyui",
                provider_asset_id=video_filename,
                media_type="video",
                original_url=local_path, # We treat the local downloaded path as original_url for processing
                description=prompt,
                duration_seconds=duration_seconds, # Approximated based on request
                width=1080,
                height=1920,
                fps=30
            )

        except Exception as e:
            logger.error(f"ComfyUI generation failed: {e}")
            raise ProviderError(f"ComfyUI Error: {str(e)}")

    async def generate_from_image(self, prompt: str, image_path: str, duration_seconds: float = 5.0) -> MediaAsset:
        return await self.generate_video(prompt, duration_seconds, image_path=image_path)

    async def generate_from_video(self, prompt: str, video_path: str, duration_seconds: float = 5.0) -> MediaAsset:
        return await self.generate_video(prompt, duration_seconds, video_path=video_path)
