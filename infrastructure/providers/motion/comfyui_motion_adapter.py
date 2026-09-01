from __future__ import annotations

import asyncio
import copy
import json
import uuid
from pathlib import Path
from typing import Any

from core.application.services.candidate.candidate_evaluation_service import (
    CandidateEvaluationService,
)
from core.domain.entities.candidate.keyframe_candidate import CandidateStatus
from core.domain.entities.shot_animation import ShotMotionClip, ShotPlan
from core.domain.exceptions import MotionGenerationError, ProviderError
from core.domain.ports.motion_generator_port import (
    MotionGeneratorPort,
    ProgressCallback,
)
from core.domain.ports.storage_port import StoragePort
from core.domain.value_objects.render_config import RenderConfig
from infrastructure.providers.motion.comfyui_ws_client import ComfyUIWsClient
from infrastructure.storage.local_fs_storage import LocalFsStorage


class ComfyUIMotionAdapter(MotionGeneratorPort):
    """Convert an approved keyframe into motion with two chained samplers."""

    def __init__(
        self,
        server_address: str,
        cache_dir: str = "cache/motion",
        *,
        workflow_path: str | Path = "assets/comfyui_i2v_workflow.json",
        storage: StoragePort | None = None,
        client: ComfyUIWsClient | None = None,
        render_config: RenderConfig | None = None,
        candidate_evaluation_service: CandidateEvaluationService | None = None,
        cache_prefix: str = "motion/two-pass",
        timeout_seconds: float = 900.0,
    ) -> None:
        self._storage = storage or LocalFsStorage(cache_dir)
        self._client = client or ComfyUIWsClient(
            server_address, timeout_seconds=timeout_seconds
        )
        self._workflow_path = Path(workflow_path)
        self._config = render_config or RenderConfig(
            width=512,
            height=512,
            fps=8,
            seed=1903,
            sampler_name="euler",
            pass1_denoise=0.12,
            pass2_denoise=0.06,
        )
        self._candidate_evaluation_service = candidate_evaluation_service
        self._cache_prefix = cache_prefix.strip("/\\")
        if not self._cache_prefix:
            raise ValueError("Motion cache_prefix must not be empty.")

    @property
    def name(self) -> str:
        return "comfyui:two-pass-anime-motion"

    async def generate_motion_clip(
        self,
        shot_plan: ShotPlan,
        progress_callback: ProgressCallback | None = None,
    ) -> ShotMotionClip:
        if not shot_plan.keyframe_approved:
            raise MotionGenerationError(
                "Two-pass motion requires a keyframe approved through the human-review gate."
            )
        await self._verify_committed_candidate(shot_plan)
        if not await self._storage.exists(shot_plan.source_image_storage_key):
            raise MotionGenerationError(
                f"Approved source image '{shot_plan.source_image_storage_key}' was not found."
            )
        character_tags = (shot_plan.character_state.character_id,)
        frame_count = max(1, round(shot_plan.duration_seconds * self._config.fps))
        render_hash = self._config.compute_hash(
            shot_plan.prompt,
            character_tags,
            source_key=shot_plan.source_image_storage_key,
            frame_count=frame_count,
        )
        for extension in (".mp4", ".webm"):
            cached_key = f"{self._cache_prefix}/{shot_plan.id}/{render_hash}{extension}"
            if await self._storage.exists(cached_key):
                if progress_callback is not None:
                    progress_callback(1.0)
                return ShotMotionClip(
                    video_path=cached_key,
                    hash=render_hash,
                    seed=self._config.seed,
                    cached=True,
                    provider_asset_id=cached_key,
                )

        workflow = await asyncio.to_thread(self._load_workflow)
        source_bytes = await self._storage.load(shot_plan.source_image_storage_key)
        uploaded_name = await self._client.upload_image(
            source_bytes, shot_plan.source_image_storage_key
        )
        self._inject_shot(workflow, shot_plan, uploaded_name)
        self._install_second_pass(workflow)
        history = await self._client.queue_prompt_and_wait(
            workflow,
            client_id=uuid.uuid4().hex,
            progress_callback=progress_callback,
        )
        file_info = self._find_video_output(history)
        video_bytes = await self._client.download_output(file_info)
        filename = str(file_info["filename"])
        extension = Path(filename).suffix.casefold()
        content_type = {".mp4": "video/mp4", ".webm": "video/webm"}.get(extension)
        if content_type is None:
            raise ProviderError(f"Unsupported ComfyUI motion output: {filename}")
        self._validate_video(video_bytes, content_type)
        storage_key = f"{self._cache_prefix}/{shot_plan.id}/{render_hash}{extension}"
        stored = await self._storage.save(storage_key, video_bytes, content_type)
        if stored.key != storage_key:
            raise MotionGenerationError("Storage adapter changed the motion cache key.")
        prompt_id = str(history.get("prompt_id", "")).strip()
        return ShotMotionClip(
            video_path=storage_key,
            hash=render_hash,
            seed=self._config.seed,
            cached=False,
            provider_asset_id=filename,
            pass_prompt_ids=(prompt_id,) if prompt_id else (),
        )

    async def _verify_committed_candidate(self, shot_plan: ShotPlan) -> None:
        if self._candidate_evaluation_service is None:
            raise MotionGenerationError(
                "Two-pass motion requires a configured committed-candidate verifier."
            )
        candidate = await self._candidate_evaluation_service.get_approved_candidate_for_shot(
            shot_plan.id
        )
        if candidate is None or candidate.status != CandidateStatus.COMMITTED:
            raise MotionGenerationError(
                "Two-pass motion requires a candidate committed through the A7 review gate."
            )
        if candidate.storage_key != shot_plan.source_image_storage_key:
            raise MotionGenerationError(
                "The animation plan does not reference the committed candidate asset."
            )

    def _load_workflow(self) -> dict[str, Any]:
        try:
            parsed = json.loads(self._workflow_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ProviderError(
                f"Two-pass ComfyUI workflow could not be read: {self._workflow_path}"
            ) from error
        if not isinstance(parsed, dict) or not parsed:
            raise ProviderError("Two-pass ComfyUI workflow must contain a node object.")
        return parsed

    def _inject_shot(
        self,
        workflow: dict[str, Any],
        shot_plan: ShotPlan,
        uploaded_name: str,
    ) -> None:
        load_image = self._first_node(workflow, "LoadImage")
        if load_image is None:
            raise ProviderError("Two-pass workflow requires a LoadImage node.")
        load_image[1].setdefault("inputs", {})["image"] = uploaded_name

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
            raise ProviderError("Two-pass workflow requires a positive prompt node.")
        positive.setdefault("inputs", {})["text"] = shot_plan.prompt
        negative = next(
            (
                node
                for node in prompt_nodes
                if "negative" in str(node.get("_meta", {}).get("title", "")).casefold()
            ),
            None,
        )
        if negative is not None and shot_plan.negative_prompt.strip():
            negative.setdefault("inputs", {})["text"] = shot_plan.negative_prompt

        frame_count = max(1, round(shot_plan.duration_seconds * self._config.fps))
        for node in workflow.values():
            if not isinstance(node, dict):
                continue
            inputs = node.setdefault("inputs", {})
            if node.get("class_type") == "ImageScale":
                inputs.update({"width": self._config.width, "height": self._config.height})
            if node.get("class_type") == "RepeatLatentBatch" and "amount" in inputs:
                inputs["amount"] = frame_count
            for field in ("num_frames", "length", "frames"):
                if field in inputs:
                    inputs[field] = frame_count
            for field in ("fps", "frame_rate"):
                if field in inputs:
                    inputs[field] = self._config.fps

    def _install_second_pass(self, workflow: dict[str, Any]) -> None:
        first = next(
            (
                (node_id, node)
                for node_id, node in workflow.items()
                if isinstance(node, dict)
                and node.get("class_type") == "KSampler"
            ),
            None,
        )
        if first is None:
            raise ProviderError("Two-pass workflow requires a KSampler node.")
        first_id, first_node = first
        first_inputs = first_node.setdefault("inputs", {})
        first_inputs.update(
            {
                "seed": self._config.seed,
                "steps": self._config.sampling_steps,
                "cfg": self._config.guidance_scale,
                "sampler_name": self._config.sampler_name,
                "denoise": self._config.pass1_denoise,
            }
        )
        first_node.setdefault("_meta", {}).update(
            {"title": "SELMA motion pass 1", "selma_pass": 1}
        )
        second_id = "selma_motion_pass_2"
        if second_id in workflow:
            raise ProviderError("Workflow already contains SELMA's reserved pass-2 node ID.")
        second_node = copy.deepcopy(first_node)
        second_node["inputs"]["latent_image"] = [first_id, 0]
        second_node["inputs"]["denoise"] = self._config.pass2_denoise
        second_node["_meta"] = {"title": "SELMA identity refinement pass 2", "selma_pass": 2}
        for node_id, node in workflow.items():
            if node_id == first_id or not isinstance(node, dict):
                continue
            self._replace_node_reference(node.get("inputs", {}), first_id, second_id)
        workflow[second_id] = second_node

    @classmethod
    def _replace_node_reference(cls, value: Any, source_id: str, target_id: str) -> None:
        if isinstance(value, dict):
            for nested in value.values():
                cls._replace_node_reference(nested, source_id, target_id)
        elif isinstance(value, list):
            if len(value) == 2 and str(value[0]) == source_id and isinstance(value[1], int):
                value[0] = target_id
                return
            for nested in value:
                cls._replace_node_reference(nested, source_id, target_id)

    @staticmethod
    def _first_node(
        workflow: dict[str, Any], class_type: str
    ) -> tuple[str, dict[str, Any]] | None:
        return next(
            (
                (node_id, node)
                for node_id, node in workflow.items()
                if isinstance(node, dict) and node.get("class_type") == class_type
            ),
            None,
        )

    @staticmethod
    def _find_video_output(history: dict[str, Any]) -> dict[str, Any]:
        for output in history.get("outputs", {}).values():
            if not isinstance(output, dict):
                continue
            for field in ("videos", "gifs"):
                files = output.get(field)
                if isinstance(files, list) and files and isinstance(files[0], dict):
                    return dict(files[0])
        raise ProviderError("ComfyUI history did not contain a video output.")

    @staticmethod
    def _validate_video(data: bytes, content_type: str) -> None:
        valid = (
            content_type == "video/mp4" and len(data) >= 12 and data[4:8] == b"ftyp"
        ) or (content_type == "video/webm" and data.startswith(b"\x1aE\xdf\xa3"))
        if not valid:
            raise ProviderError("ComfyUI bytes do not match the declared video type.")
