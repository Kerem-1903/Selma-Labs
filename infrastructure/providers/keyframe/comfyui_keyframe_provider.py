from __future__ import annotations

import asyncio
import hashlib
import io
import json
import logging
import re
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Any, ClassVar

import aiohttp
from PIL import Image

from core.domain.exceptions import (
    ProviderConnectionError,
    ProviderError,
    ProviderTimeoutError,
)
from core.domain.ports.keyframe_generation_port import KeyframeGenerationPort
from core.domain.ports.storage_port import StoragePort
from core.domain.value_objects.generated_keyframe import GeneratedKeyframe
from core.domain.value_objects.keyframe_generation_request import (
    KeyframeGenerationRequest,
)

logger = logging.getLogger(__name__)


class ComfyUIKeyframeProvider(KeyframeGenerationPort):
    """Generate a still image through ComfyUI's HTTP API.

    Character references remain provider-neutral storage keys until this adapter
    loads their bytes and uploads them into ComfyUI's own input directory.
    """

    _SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")
    _CONTENT_TYPES: ClassVar[dict[str, str]] = {
        ".jpeg": "image/jpeg",
        ".jpg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }

    def __init__(
        self,
        *,
        api_url: str,
        workflow_path: str | Path,
        storage: StoragePort,
        checkpoint_name: str = "sd_xl_base_1.0.safetensors",
        character_lora_name: str = "",
        character_lora_trigger_token: str = "",
        character_lora_strength_model: float = 0.8,
        character_lora_strength_clip: float = 0.8,
        timeout_seconds: float = 300.0,
        poll_interval_seconds: float = 1.0,
        session_factory: Callable[..., Any] = aiohttp.ClientSession,
    ) -> None:
        if not api_url.strip():
            raise ValueError("ComfyUI api_url must not be empty.")
        if timeout_seconds <= 0:
            raise ValueError("ComfyUI timeout_seconds must be greater than zero.")
        if poll_interval_seconds <= 0:
            raise ValueError("ComfyUI poll_interval_seconds must be greater than zero.")
        for field_name, value in (
            ("character_lora_strength_model", character_lora_strength_model),
            ("character_lora_strength_clip", character_lora_strength_clip),
        ):
            if not 0.0 <= value <= 2.0:
                raise ValueError(f"{field_name} must be between 0 and 2.")
        self._api_url = api_url.rstrip("/")
        self._workflow_path = Path(workflow_path)
        self._storage = storage
        self._checkpoint_name = checkpoint_name.strip()
        self._character_lora_name = character_lora_name.strip()
        self._character_lora_trigger_token = character_lora_trigger_token.strip()
        self._character_lora_strength_model = character_lora_strength_model
        self._character_lora_strength_clip = character_lora_strength_clip
        self._timeout_seconds = timeout_seconds
        self._poll_interval_seconds = poll_interval_seconds
        self._session_factory = session_factory

    @property
    def name(self) -> str:
        return "comfyui:keyframe"

    async def generate_keyframe(
        self, request: KeyframeGenerationRequest
    ) -> GeneratedKeyframe:
        workflow = await self._load_workflow()
        self._inject_typed_constraints(workflow, request)
        selected_references = self._select_character_references(request)
        reference_nodes = self._connected_reference_nodes(workflow)
        if selected_references and len(reference_nodes) < len(selected_references):
            raise ProviderError(
                "ComfyUI workflow does not contain enough connected SELMA reference nodes."
            )
        pose_storage_key = str(
            request.visual_constraints.get("pose_storage_key", "")
        ).strip()
        lora_metadata, base_model_source = self._select_character_lora(
            workflow, request
        )
        self._select_identity_conditioning(
            workflow,
            use_reference=bool(selected_references),
            base_model_source=base_model_source,
        )
        controlnet_type = str(
            request.visual_constraints.get("controlnet_type", "openpose")
        ).strip()
        self._select_pose_conditioning(
            workflow,
            request,
            use_pose=bool(pose_storage_key),
            controlnet_type=controlnet_type,
        )
        pose_nodes = self._connected_nodes_for_role(workflow, "pose_control_image")
        if pose_storage_key and len(pose_nodes) != 1:
            raise ProviderError(
                "ComfyUI workflow must contain one connected SELMA pose-control image node."
            )

        timeout = aiohttp.ClientTimeout(total=self._timeout_seconds)
        try:
            async with self._session_factory(timeout=timeout) as session:
                for node_id, (asset_id, storage_key) in zip(
                    reference_nodes, selected_references
                ):
                    uploaded_name = await self._upload_reference(
                        session, storage_key=storage_key
                    )
                    workflow[node_id]["inputs"]["image"] = uploaded_name
                if pose_storage_key:
                    uploaded_pose = await self._upload_reference(
                        session, storage_key=pose_storage_key
                    )
                    workflow[pose_nodes[0]]["inputs"]["image"] = uploaded_pose
                self._select_latent_source(
                    workflow, use_reference=bool(selected_references)
                )
                prompt_id = await self._queue_prompt(session, workflow)
                history = await self._wait_for_completion(session, prompt_id)
                filename, subfolder, folder_type = self._find_output_image(
                    workflow, history
                )
                image_bytes, response_content_type = await self._download_image(
                    session,
                    filename=filename,
                    subfolder=subfolder,
                    folder_type=folder_type,
                )
        except asyncio.TimeoutError as error:
            raise ProviderTimeoutError(
                f"ComfyUI generation timed out after {self._timeout_seconds:g} seconds."
            ) from error
        except aiohttp.ClientError as error:
            raise ProviderConnectionError(f"ComfyUI connection failed: {error}") from error

        content_type = self._content_type_for(filename, response_content_type)
        width, height = self._image_dimensions(image_bytes)
        return GeneratedKeyframe(
            image_bytes=image_bytes,
            content_type=content_type,
            width=width,
            height=height,
            provider_asset_id=filename,
            metadata={
                "prompt_id": prompt_id,
                "reference_asset_ids": [item[0] for item in selected_references],
                "reference_storage_keys": [item[1] for item in selected_references],
                "pose_storage_key": pose_storage_key or None,
                "character_lora": lora_metadata,
            },
        )

    async def _load_workflow(self) -> dict[str, Any]:
        try:
            raw = await asyncio.to_thread(self._workflow_path.read_text, encoding="utf-8")
            workflow = json.loads(raw)
        except FileNotFoundError as error:
            raise ProviderError(
                f"ComfyUI workflow was not found: {self._workflow_path}"
            ) from error
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ProviderError(
                f"ComfyUI workflow is not readable JSON: {self._workflow_path}"
            ) from error
        if not isinstance(workflow, dict) or not workflow:
            raise ProviderError("ComfyUI workflow must contain an API-format node object.")
        return workflow

    def _inject_typed_constraints(
        self, workflow: dict[str, Any], request: KeyframeGenerationRequest
    ) -> None:
        positive_node = self._node_for_role(workflow, "positive_prompt", "CLIPTextEncode")
        if positive_node is None:
            raise ProviderError("ComfyUI workflow has no positive prompt node.")
        positive_node[1]["inputs"]["text"] = self._build_positive_prompt(request)

        negative_node = self._node_for_role(workflow, "negative_prompt")
        if negative_node is not None:
            existing = str(negative_node[1].get("inputs", {}).get("text", "")).strip()
            values = [*request.negative_prompts]
            if existing:
                values.append(existing)
            negative_node[1]["inputs"]["text"] = ", ".join(dict.fromkeys(values))

        sampler = self._node_for_role(workflow, "sampler", "KSampler")
        if sampler is None:
            raise ProviderError("ComfyUI workflow has no sampler node.")
        if request.seed is not None:
            sampler[1]["inputs"]["seed"] = request.seed
        sampler_overrides = {
            "sampling_steps": "steps",
            "guidance_scale": "cfg",
            "sampler_name": "sampler_name",
            "scheduler": "scheduler",
        }
        for source_key, input_key in sampler_overrides.items():
            if source_key in request.visual_constraints:
                sampler[1]["inputs"][input_key] = request.visual_constraints[
                    source_key
                ]
        try:
            steps = int(sampler[1]["inputs"]["steps"])
            guidance_scale = float(sampler[1]["inputs"]["cfg"])
        except (KeyError, TypeError, ValueError) as error:
            raise ProviderError("Sampler steps and guidance scale must be numeric.") from error
        if not 1 <= steps <= 150 or not 0.0 < guidance_scale <= 30.0:
            raise ProviderError("Sampler steps or guidance scale is outside safe bounds.")
        sampler[1]["inputs"]["steps"] = steps
        sampler[1]["inputs"]["cfg"] = guidance_scale

        checkpoint = self._node_for_role(
            workflow, "checkpoint", "CheckpointLoaderSimple"
        )
        if checkpoint is not None and self._checkpoint_name:
            checkpoint[1]["inputs"]["ckpt_name"] = self._checkpoint_name

        target_nodes = [
            node
            for node in workflow.values()
            if node.get("_meta", {}).get("selma_role") == "target_size"
            or node.get("class_type") == "EmptyLatentImage"
        ]
        for node in target_nodes:
            node["inputs"]["width"] = request.width
            node["inputs"]["height"] = request.height

        identity_adapter = self._node_for_role(workflow, "identity_adapter")
        identity_strength = request.visual_constraints.get("identity_strength")
        if identity_adapter is not None and identity_strength is not None:
            identity_adapter[1]["inputs"]["weight"] = float(identity_strength)
        if identity_adapter is not None:
            self._inject_identity_mode(identity_adapter[1], request)

        pose_control = self._node_for_role(workflow, "pose_control")
        pose_strength = request.visual_constraints.get("pose_strength")
        if pose_control is not None and pose_strength is not None:
            pose_control[1]["inputs"]["strength"] = float(pose_strength)

    @staticmethod
    def _build_positive_prompt(request: KeyframeGenerationRequest) -> str:
        values: list[str] = []
        explicit_prompt = request.visual_constraints.get("prompt")
        if explicit_prompt:
            values.append(str(explicit_prompt).strip())
        for key in ("primary_action", "secondary_actions"):
            value = request.action_constraints.get(key)
            if isinstance(value, list):
                values.extend(str(item).strip() for item in value if str(item).strip())
            elif value:
                values.append(str(value).strip())
        for source, keys in (
            (request.camera_constraints, ("angle", "lens", "movement")),
            (
                request.visual_constraints,
                (
                    "lighting",
                    "environment_style",
                    "weather",
                    "composition_contract",
                ),
            ),
        ):
            values.extend(str(source[key]).strip() for key in keys if source.get(key))

        identity_contract = request.visual_constraints.get("identity_contract", {})
        if isinstance(identity_contract, dict):
            for name, raw_value in identity_contract.items():
                entries = raw_value if isinstance(raw_value, (list, tuple)) else (raw_value,)
                values.extend(
                    f"locked {name}: ({str(entry).strip()}:1.25)"
                    for entry in entries
                    if str(entry).strip()
                )

        for condition in request.character_conditioning:
            character_id = str(condition.get("character_id", "")).strip()
            if character_id:
                values.append(f"character {character_id}")
            identity = condition.get("identity_constraints", {})
            if isinstance(identity, dict):
                values.extend(
                    str(value).strip()
                    for value in identity.values()
                    if isinstance(value, str) and value.strip()
                )
            style = condition.get("style_profile", {})
            if isinstance(style, dict) and style.get("base_style"):
                values.append(str(style["base_style"]).strip())
            state = condition.get("continuity_state", {})
            if isinstance(state, dict):
                for key in ("active_outfit_id", "emotion", "location"):
                    if state.get(key):
                        values.append(str(state[key]).strip())
                for key in ("injuries", "held_objects"):
                    entries = state.get(key, [])
                    if isinstance(entries, list):
                        values.extend(str(entry).strip() for entry in entries if str(entry).strip())

        prompt = ", ".join(dict.fromkeys(value for value in values if value))
        if not prompt:
            raise ProviderError("Keyframe request contains no usable visual constraints.")
        return prompt

    def _select_character_references(
        self, request: KeyframeGenerationRequest
    ) -> list[tuple[str, str]]:
        key_by_asset_id = dict(
            zip(request.reference_asset_ids, request.reference_storage_keys)
        )
        preferred_views = self._preferred_views(
            str(request.camera_constraints.get("angle", ""))
        )
        selected: list[tuple[str, str]] = []
        for condition in request.character_conditioning:
            references = condition.get("references", [])
            if not isinstance(references, list):
                continue
            valid = [
                reference
                for reference in references
                if isinstance(reference, dict)
                and reference.get("asset_id") in key_by_asset_id
            ]
            chosen = next(
                (
                    reference
                    for view in preferred_views
                    for reference in valid
                    if reference.get("view") == view
                ),
                valid[0] if valid else None,
            )
            if chosen is not None:
                asset_id = str(chosen["asset_id"])
                selected.append((asset_id, key_by_asset_id[asset_id]))

        if not selected and request.reference_asset_ids:
            selected.append(
                (request.reference_asset_ids[0], request.reference_storage_keys[0])
            )
        return selected

    @staticmethod
    def _preferred_views(angle: str) -> tuple[str, ...]:
        normalized = angle.casefold()
        if "close" in normalized:
            return ("FACE_CLOSEUP", "THREE_QUARTER_LEFT", "FRONT")
        if "profile" in normalized or "side" in normalized:
            return ("PROFILE_LEFT", "PROFILE_RIGHT", "THREE_QUARTER_LEFT")
        if "wide" in normalized or "full" in normalized:
            return ("FULL_BODY", "FRONT", "THREE_QUARTER_LEFT")
        return ("THREE_QUARTER_LEFT", "FRONT", "FACE_CLOSEUP", "FULL_BODY")

    async def _upload_reference(
        self, session: Any, *, storage_key: str
    ) -> str:
        data = await self._storage.load(storage_key)
        if not data:
            raise ProviderError(f"Character reference '{storage_key}' is empty.")
        suffix = PurePosixPath(storage_key.replace("\\", "/")).suffix.casefold()
        content_type = self._CONTENT_TYPES.get(suffix, "application/octet-stream")
        digest = hashlib.sha256(storage_key.encode("utf-8")).hexdigest()[:12]
        original_name = PurePosixPath(storage_key.replace("\\", "/")).name
        safe_name = self._SAFE_FILENAME.sub("-", original_name) or "reference.png"
        filename = f"selma-{digest}-{safe_name}"
        form = aiohttp.FormData()
        form.add_field("image", data, filename=filename, content_type=content_type)
        form.add_field("type", "input")
        form.add_field("overwrite", "true")
        async with session.post(f"{self._api_url}/upload/image", data=form) as response:
            if response.status not in {200, 201}:
                raise ProviderError(
                    f"ComfyUI reference upload failed ({response.status}): "
                    f"{await response.text()}"
                )
            payload = await response.json()
        name = str(payload.get("name", "")).strip()
        if not name:
            raise ProviderError("ComfyUI reference upload returned no filename.")
        if str(payload.get("type", "input")) != "input":
            raise ProviderError("ComfyUI reference upload did not create an input asset.")
        subfolder = str(payload.get("subfolder", "")).strip().strip("/\\")
        return f"{subfolder}/{name}" if subfolder else name

    async def _queue_prompt(self, session: Any, workflow: dict[str, Any]) -> str:
        async with session.post(
            f"{self._api_url}/prompt", json={"prompt": workflow}
        ) as response:
            if response.status != 200:
                raise ProviderError(
                    f"ComfyUI queue failed ({response.status}): {await response.text()}"
                )
            payload = await response.json()
        prompt_id = str(payload.get("prompt_id", "")).strip()
        if not prompt_id:
            raise ProviderError("ComfyUI queue response contained no prompt_id.")
        return prompt_id

    async def _wait_for_completion(self, session: Any, prompt_id: str) -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._timeout_seconds
        while loop.time() < deadline:
            async with session.get(f"{self._api_url}/history/{prompt_id}") as response:
                if response.status != 200:
                    raise ProviderError(
                        f"ComfyUI history failed ({response.status}): {await response.text()}"
                    )
                payload = await response.json()
            history = payload.get(prompt_id)
            if isinstance(history, dict):
                status = history.get("status", {})
                if isinstance(status, dict) and status.get("status_str") == "error":
                    raise ProviderError(f"ComfyUI execution failed for prompt '{prompt_id}'.")
                if history.get("outputs"):
                    return history
            await asyncio.sleep(self._poll_interval_seconds)
        raise ProviderTimeoutError(
            f"ComfyUI generation timed out after {self._timeout_seconds:g} seconds."
        )

    async def _download_image(
        self,
        session: Any,
        *,
        filename: str,
        subfolder: str,
        folder_type: str,
    ) -> tuple[bytes, str]:
        params = {"filename": filename, "subfolder": subfolder, "type": folder_type}
        async with session.get(f"{self._api_url}/view", params=params) as response:
            if response.status != 200:
                raise ProviderError(
                    f"ComfyUI image download failed ({response.status}): "
                    f"{await response.text()}"
                )
            return await response.read(), str(response.headers.get("Content-Type", ""))

    def _find_output_image(
        self, workflow: dict[str, Any], history: dict[str, Any]
    ) -> tuple[str, str, str]:
        outputs = history.get("outputs", {})
        output_nodes = [node_id for node_id, _ in self._nodes_for_role(workflow, "output")]
        if not output_nodes:
            output_nodes = [
                node_id
                for node_id, node in workflow.items()
                if node.get("class_type") == "SaveImage"
            ]
        for node_id in output_nodes:
            images = outputs.get(node_id, {}).get("images", [])
            if images:
                image = images[0]
                return (
                    str(image["filename"]),
                    str(image.get("subfolder", "")),
                    str(image.get("type", "output")),
                )
        raise ProviderError("ComfyUI history contained no image from the output node.")

    def _connected_reference_nodes(self, workflow: dict[str, Any]) -> list[str]:
        return self._connected_nodes_for_role(workflow, "reference_image")

    def _connected_nodes_for_role(
        self, workflow: dict[str, Any], role: str
    ) -> list[str]:
        reachable: set[str] = set()

        def visit(node_id: str) -> None:
            if node_id in reachable or node_id not in workflow:
                return
            reachable.add(node_id)
            for value in workflow[node_id].get("inputs", {}).values():
                if (
                    isinstance(value, list)
                    and len(value) == 2
                    and str(value[0]) in workflow
                ):
                    visit(str(value[0]))

        output_ids = [node_id for node_id, _ in self._nodes_for_role(workflow, "output")]
        if not output_ids:
            output_ids = [
                node_id
                for node_id, node in workflow.items()
                if node.get("class_type") == "SaveImage"
            ]
        for output_id in output_ids:
            visit(output_id)
        return [
            node_id
            for node_id, _ in self._nodes_for_role(workflow, role)
            if node_id in reachable
        ]

    def _select_identity_conditioning(
        self,
        workflow: dict[str, Any],
        *,
        use_reference: bool,
        base_model_source: list[Any],
    ) -> None:
        sampler = self._node_for_role(workflow, "sampler", "KSampler")
        checkpoint = self._node_for_role(
            workflow, "checkpoint", "CheckpointLoaderSimple"
        )
        identity_adapter = self._node_for_role(workflow, "identity_adapter")
        if sampler is None or checkpoint is None:
            raise ProviderError(
                "ComfyUI identity workflow requires sampler and checkpoint nodes."
            )
        if use_reference:
            if identity_adapter is None:
                raise ProviderError("ComfyUI workflow has no identity-adapter node.")
            sampler[1]["inputs"]["model"] = [identity_adapter[0], 0]
        else:
            sampler[1]["inputs"]["model"] = list(base_model_source)

    def _select_character_lora(
        self,
        workflow: dict[str, Any],
        request: KeyframeGenerationRequest,
    ) -> tuple[dict[str, Any] | None, list[Any]]:
        checkpoint = self._node_for_role(
            workflow, "checkpoint", "CheckpointLoaderSimple"
        )
        if checkpoint is None:
            raise ProviderError("ComfyUI workflow has no checkpoint node.")
        checkpoint_model = [checkpoint[0], 0]
        checkpoint_clip = [checkpoint[0], 1]
        lora = self._node_for_role(workflow, "character_lora")
        name = str(
            request.visual_constraints.get(
                "character_lora_name", self._character_lora_name
            )
        ).strip()
        if not name:
            self._rewire_clip_inputs(workflow, checkpoint_clip)
            identity_loader = self._identity_loader(workflow)
            if identity_loader is not None:
                identity_loader[1]["inputs"]["model"] = checkpoint_model
            return None, checkpoint_model
        if lora is None:
            raise ProviderError("ComfyUI workflow has no character-LoRA node.")
        trigger_token = str(
            request.visual_constraints.get(
                "character_lora_trigger_token",
                self._character_lora_trigger_token,
            )
        ).strip()
        if not trigger_token:
            raise ProviderError(
                "Character LoRA requires a non-empty trigger token."
            )

        strength_model = float(
            request.visual_constraints.get(
                "character_lora_strength_model",
                self._character_lora_strength_model,
            )
        )
        strength_clip = float(
            request.visual_constraints.get(
                "character_lora_strength_clip",
                self._character_lora_strength_clip,
            )
        )
        if not 0.0 <= strength_model <= 2.0 or not 0.0 <= strength_clip <= 2.0:
            raise ProviderError("Character LoRA strengths must be between 0 and 2.")
        lora[1]["inputs"].update(
            {
                "lora_name": name,
                "strength_model": strength_model,
                "strength_clip": strength_clip,
                "model": checkpoint_model,
                "clip": checkpoint_clip,
            }
        )
        lora_model = [lora[0], 0]
        lora_clip = [lora[0], 1]
        self._rewire_clip_inputs(workflow, lora_clip)
        positive = self._node_for_role(workflow, "positive_prompt", "CLIPTextEncode")
        if positive is None:
            raise ProviderError("ComfyUI workflow has no positive prompt node.")
        prompt = str(positive[1]["inputs"].get("text", "")).strip()
        if trigger_token.casefold() not in prompt.casefold():
            positive[1]["inputs"]["text"] = f"{trigger_token}, {prompt}"
        identity_loader = self._identity_loader(workflow)
        if identity_loader is not None:
            identity_loader[1]["inputs"]["model"] = lora_model
        return (
            {
                "name": name,
                "trigger_token": trigger_token,
                "strength_model": strength_model,
                "strength_clip": strength_clip,
            },
            lora_model,
        )

    def _rewire_clip_inputs(
        self, workflow: dict[str, Any], clip_source: list[Any]
    ) -> None:
        for role in ("positive_prompt", "negative_prompt"):
            node = self._node_for_role(workflow, role)
            if node is not None:
                node[1]["inputs"]["clip"] = list(clip_source)

    def _node_for_role_by_class(
        self, workflow: dict[str, Any], class_type: str
    ) -> tuple[str, dict[str, Any]] | None:
        return next(
            (
                (node_id, node)
                for node_id, node in workflow.items()
                if node.get("class_type") == class_type
            ),
            None,
        )

    def _identity_loader(
        self, workflow: dict[str, Any]
    ) -> tuple[str, dict[str, Any]] | None:
        """Return either the visual or FaceID IP-Adapter loader.

        Workflows should mark the loader explicitly. Class fallbacks keep older
        exported ComfyUI API workflows compatible.
        """
        loader = self._node_for_role(workflow, "identity_loader")
        if loader is not None:
            return loader
        for class_type in (
            "IPAdapterUnifiedLoaderFaceID",
            "IPAdapterUnifiedLoader",
        ):
            loader = self._node_for_role_by_class(workflow, class_type)
            if loader is not None:
                return loader
        return None

    @staticmethod
    def _inject_identity_mode(
        identity_adapter: dict[str, Any], request: KeyframeGenerationRequest
    ) -> None:
        inputs = identity_adapter["inputs"]
        mode = str(request.visual_constraints.get("identity_mode", "balanced"))
        if mode == "identity_only":
            inputs.update(
                {
                    "weight_type": "weak input",
                    "combine_embeds": "average",
                    "start_at": 0.0,
                    "end_at": 0.65,
                    "embeds_scaling": "K+V w/ C penalty",
                }
            )
        elif mode != "balanced":
            raise ProviderError(f"Unknown identity conditioning mode: {mode!r}.")

        overrides = {
            "identity_weight_type": "weight_type",
            "identity_combine_embeds": "combine_embeds",
            "identity_start_at": "start_at",
            "identity_end_at": "end_at",
            "identity_embeds_scaling": "embeds_scaling",
        }
        for source_key, input_key in overrides.items():
            if source_key in request.visual_constraints:
                inputs[input_key] = request.visual_constraints[source_key]
        if (
            "weight_faceidv2" in inputs
            and "identity_faceidv2_strength" in request.visual_constraints
        ):
            faceidv2_strength = float(
                request.visual_constraints["identity_faceidv2_strength"]
            )
            if not -1.0 <= faceidv2_strength <= 5.0:
                raise ProviderError(
                    "FaceID v2 identity strength must be between -1 and 5."
                )
            inputs["weight_faceidv2"] = faceidv2_strength
        try:
            start_at = float(inputs["start_at"])
            end_at = float(inputs["end_at"])
        except (KeyError, TypeError, ValueError) as error:
            raise ProviderError(
                "Identity conditioning start/end values must be numeric."
            ) from error
        if not 0.0 <= start_at <= end_at <= 1.0:
            raise ProviderError(
                "Identity conditioning must satisfy 0 <= start_at <= end_at <= 1."
            )
        inputs["start_at"] = start_at
        inputs["end_at"] = end_at

    def _select_pose_conditioning(
        self,
        workflow: dict[str, Any],
        request: KeyframeGenerationRequest,
        *,
        use_pose: bool,
        controlnet_type: str = "openpose",
    ) -> None:
        pose_control = self._node_for_role(workflow, "pose_control")
        if pose_control is None:
            if use_pose:
                raise ProviderError("ComfyUI workflow has no pose-control node.")
            return

        if use_pose and controlnet_type != "openpose":
            raise ProviderError(
                f"Unsupported keyframe ControlNet type: {controlnet_type!r}."
            )

        sampler = self._node_for_role(workflow, "sampler", "KSampler")
        positive = self._node_for_role(workflow, "positive_prompt", "CLIPTextEncode")
        negative = self._node_for_role(workflow, "negative_prompt")
        if sampler is None or positive is None or negative is None:
            raise ProviderError(
                "ComfyUI pose workflow requires sampler, positive and negative nodes."
            )
        if use_pose:
            sampler[1]["inputs"]["positive"] = [pose_control[0], 0]
            sampler[1]["inputs"]["negative"] = [pose_control[0], 1]
            # Adjust strength if node allows
            if "strength" in pose_control[1]["inputs"]:
                pose_strength = request.visual_constraints.get("pose_strength")
                pose_control[1]["inputs"]["strength"] = float(pose_strength) if pose_strength is not None else 0.8
        else:
            sampler[1]["inputs"]["positive"] = [positive[0], 0]
            sampler[1]["inputs"]["negative"] = [negative[0], 0]

    def _select_latent_source(
        self, workflow: dict[str, Any], *, use_reference: bool
    ) -> None:
        sampler = self._node_for_role(workflow, "sampler", "KSampler")
        if sampler is None:
            raise ProviderError("ComfyUI workflow has no sampler node.")
        role = "reference_latent" if use_reference else "empty_latent"
        source = self._node_for_role(workflow, role)
        if source is None:
            raise ProviderError(f"ComfyUI workflow has no {role} node.")
        sampler[1]["inputs"]["latent_image"] = [source[0], 0]

    @staticmethod
    def _nodes_for_role(
        workflow: dict[str, Any], role: str
    ) -> list[tuple[str, dict[str, Any]]]:
        return [
            (node_id, node)
            for node_id, node in workflow.items()
            if node.get("_meta", {}).get("selma_role") == role
        ]

    def _node_for_role(
        self,
        workflow: dict[str, Any],
        role: str,
        fallback_class: str | None = None,
    ) -> tuple[str, dict[str, Any]] | None:
        matches = self._nodes_for_role(workflow, role)
        if matches:
            return matches[0]
        if fallback_class is not None:
            return next(
                (
                    (node_id, node)
                    for node_id, node in workflow.items()
                    if node.get("class_type") == fallback_class
                ),
                None,
            )
        return None

    @classmethod
    def _content_type_for(cls, filename: str, response_content_type: str) -> str:
        normalized = response_content_type.split(";", 1)[0].strip().casefold()
        if normalized in cls._CONTENT_TYPES.values():
            return normalized
        suffix = PurePosixPath(filename).suffix.casefold()
        try:
            return cls._CONTENT_TYPES[suffix]
        except KeyError as error:
            raise ProviderError(f"Unsupported ComfyUI image format: {filename}") from error

    @staticmethod
    def _image_dimensions(data: bytes) -> tuple[int, int]:
        try:
            with Image.open(io.BytesIO(data)) as image:
                dimensions = image.size
                image.verify()
                return dimensions
        except Exception as error:
            raise ProviderError("ComfyUI returned invalid image bytes.") from error
