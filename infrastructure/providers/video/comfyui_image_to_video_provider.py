from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Any

import aiohttp

from core.domain.exceptions import ProviderError, ProviderTimeoutError
from core.domain.ports.image_to_video_generation_port import ImageToVideoGenerationPort
from core.domain.ports.storage_port import StoragePort
from core.domain.value_objects.generated_video_clip import GeneratedVideoClip
from core.domain.value_objects.image_to_video_request import ImageToVideoRequest


class ComfyUIImageToVideoProvider(ImageToVideoGenerationPort):
    """Run a storage-backed image-to-video workflow through ComfyUI."""

    def __init__(
        self,
        *,
        api_url: str,
        workflow_path: str | Path,
        storage: StoragePort,
        timeout_seconds: float = 900.0,
        poll_interval_seconds: float = 2.0,
        session_factory: Callable[..., Any] = aiohttp.ClientSession,
    ) -> None:
        if not api_url.strip():
            raise ValueError("ComfyUI api_url must not be empty.")
        if timeout_seconds <= 0 or poll_interval_seconds <= 0:
            raise ValueError("ComfyUI timing settings must be greater than zero.")
        self._api_url = api_url.rstrip("/")
        self._workflow_path = Path(workflow_path)
        self._storage = storage
        self._timeout_seconds = timeout_seconds
        self._poll_interval_seconds = poll_interval_seconds
        self._session_factory = session_factory

    @property
    def name(self) -> str:
        return "comfyui:image-to-video"

    async def generate_video(self, request: ImageToVideoRequest) -> GeneratedVideoClip:
        workflow = await asyncio.to_thread(self._load_workflow)
        image_bytes = await self._storage.load(request.source_image_storage_key)
        if not image_bytes:
            raise ProviderError("Committed source image is empty.")
        async with self._session_factory() as session:
            uploaded_name = await self._upload_image(
                session, image_bytes, request.source_image_storage_key
            )
            self._inject_request(workflow, request, uploaded_name)
            prompt_id = await self._queue(session, workflow)
            history = await self._wait_for_history(session, prompt_id)
            file_info = self._find_video_output(history)
            video_bytes = await self._download(session, file_info)

        filename = str(file_info["filename"])
        suffix = Path(filename).suffix.casefold()
        content_type = {".mp4": "video/mp4", ".webm": "video/webm"}.get(suffix)
        if content_type is None:
            raise ProviderError(f"Unsupported ComfyUI video output: {filename}")
        return GeneratedVideoClip(
            video_bytes=video_bytes,
            content_type=content_type,
            width=request.width,
            height=request.height,
            duration_seconds=request.target_duration_seconds,
            fps=request.fps,
            provider_asset_id=filename,
            metadata={"prompt_id": prompt_id},
        )

    def _load_workflow(self) -> dict[str, Any]:
        try:
            parsed = json.loads(self._workflow_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ProviderError(
                f"ComfyUI I2V workflow could not be read: {self._workflow_path}"
            ) from error
        if not isinstance(parsed, dict):
            raise ProviderError("ComfyUI I2V workflow must contain an object.")
        return parsed

    async def _upload_image(
        self, session: Any, image_bytes: bytes, storage_key: str
    ) -> str:
        suffix = Path(storage_key).suffix.casefold()
        content_type = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
        }.get(suffix)
        if content_type is None:
            raise ProviderError("Committed source image type is unsupported by ComfyUI.")
        filename = f"selma-i2v-{uuid.uuid4().hex}{suffix}"
        form = aiohttp.FormData()
        form.add_field(
            "image", image_bytes, filename=filename, content_type=content_type
        )
        form.add_field("overwrite", "true")
        async with session.post(f"{self._api_url}/upload/image", data=form) as response:
            if response.status != 200:
                raise ProviderError(
                    f"ComfyUI source-image upload failed: {await response.text()}"
                )
            payload = await response.json()
        name = str(payload.get("name", filename))
        subfolder = str(payload.get("subfolder", "")).strip("/\\")
        return str(PurePosixPath(subfolder, name)) if subfolder else name

    @staticmethod
    def _inject_request(
        workflow: dict[str, Any], request: ImageToVideoRequest, uploaded_name: str
    ) -> None:
        load_nodes = [
            node
            for node in workflow.values()
            if isinstance(node, dict) and node.get("class_type") == "LoadImage"
        ]
        if not load_nodes:
            raise ProviderError("ComfyUI I2V workflow requires a LoadImage node.")
        load_nodes[0].setdefault("inputs", {})["image"] = uploaded_name

        prompt_nodes = [
            node
            for node in workflow.values()
            if isinstance(node, dict) and node.get("class_type") == "CLIPTextEncode"
        ]
        positive = next(
            (
                node
                for node in prompt_nodes
                if "negative" not in str(node.get("_meta", {}).get("title", "")).casefold()
            ),
            None,
        )
        if positive is None:
            raise ProviderError("ComfyUI I2V workflow requires a positive prompt node.")
        positive.setdefault("inputs", {})["text"] = (
            f"{request.motion_prompt}, camera motion: {request.camera_motion}"
        )

        frame_count = max(1, round(request.target_duration_seconds * request.fps))
        for node in workflow.values():
            if not isinstance(node, dict):
                continue
            inputs = node.setdefault("inputs", {})
            for field in ("num_frames", "length", "frames"):
                if field in inputs:
                    inputs[field] = frame_count
            for field in ("fps", "frame_rate"):
                if field in inputs:
                    inputs[field] = request.fps
            if request.seed is not None and node.get("class_type") in {
                "KSampler",
                "KSamplerAdvanced",
            }:
                if "seed" in inputs:
                    inputs["seed"] = request.seed
                if "noise_seed" in inputs:
                    inputs["noise_seed"] = request.seed

    async def _queue(self, session: Any, workflow: dict[str, Any]) -> str:
        async with session.post(
            f"{self._api_url}/prompt", json={"prompt": workflow}
        ) as response:
            if response.status != 200:
                raise ProviderError(f"ComfyUI queue failed: {await response.text()}")
            payload = await response.json()
        prompt_id = str(payload.get("prompt_id", ""))
        if not prompt_id:
            raise ProviderError("ComfyUI did not return a prompt ID.")
        return prompt_id

    async def _wait_for_history(self, session: Any, prompt_id: str) -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._timeout_seconds
        while loop.time() < deadline:
            async with session.get(
                f"{self._api_url}/history/{prompt_id}"
            ) as response:
                if response.status == 200:
                    payload = await response.json()
                    if prompt_id in payload:
                        return payload[prompt_id]
            await asyncio.sleep(self._poll_interval_seconds)
        raise ProviderTimeoutError(
            f"ComfyUI I2V generation timed out for prompt {prompt_id}."
        )

    @staticmethod
    def _find_video_output(history: dict[str, Any]) -> dict[str, Any]:
        for output in history.get("outputs", {}).values():
            if not isinstance(output, dict):
                continue
            for field in ("videos", "gifs"):
                files = output.get(field)
                if isinstance(files, list) and files:
                    return files[0]
        raise ProviderError("ComfyUI history did not contain a video output.")

    async def _download(self, session: Any, file_info: dict[str, Any]) -> bytes:
        params = {
            "filename": str(file_info["filename"]),
            "subfolder": str(file_info.get("subfolder", "")),
            "type": str(file_info.get("type", "output")),
        }
        async with session.get(f"{self._api_url}/view", params=params) as response:
            if response.status != 200:
                raise ProviderError("ComfyUI video download failed.")
            return await response.read()
