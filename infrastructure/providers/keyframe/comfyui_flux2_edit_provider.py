"""Source-led FLUX.2 Klein edit dialect for the character turnaround.

The seven-view IP-Adapter dialect treats identity as an embedding to be blended
and drives geometry with pose templates. This dialect does the opposite: the
approved canonical image *is* Picture 1 and the only thing the model may change
is the viewpoint. The prompt therefore comes from
``CharacterIdentityPromptService.build_flux2_edit_prompt`` and reaches the graph
as prose rather than tag soup.

Everything that is not graph shaping -- model locking, preflight, watchdog,
thermal guard, reference upload, output retrieval, provenance metadata -- is
inherited from ``ComfyUIKeyframeProvider`` so both dialects share one transport.
"""

from __future__ import annotations

from typing import Any, ClassVar

import aiohttp

from core.domain.exceptions import ProviderError
from core.domain.value_objects.keyframe_generation_request import (
    KeyframeGenerationRequest,
)
from core.domain.value_objects.production_infra import ModelLock
from infrastructure.providers.keyframe.comfyui_keyframe_provider import (
    ComfyUIKeyframeProvider,
)


class ComfyUIFlux2EditProvider(ComfyUIKeyframeProvider):
    """Run one source-led edit per view on a locked FLUX.2 Klein checkpoint."""

    #: Roles the FLUX.2 lock must provide, with their loader input key.
    _LOCKED_LOADERS: ClassVar[tuple[tuple[str, str], ...]] = (
        ("diffusion_model", "unet_name"),
        ("text_encoder", "clip_name"),
        ("vae", "vae_name"),
    )

    #: Prompt/editing contract this engine implements. A tournament compares
    #: variants only when they all report the same contract.
    EDIT_CONTRACT: ClassVar[str] = "source-led-delta-edit-v1"

    @property
    def name(self) -> str:
        return "comfyui:flux2-edit"

    @property
    def edit_contract(self) -> str:
        return self.EDIT_CONTRACT

    def __init__(
        self,
        *,
        api_url: str,
        workflow_path,
        storage,
        model_lock: ModelLock,
        timeout_seconds: float = 600.0,
        poll_interval_seconds: float = 1.0,
        session_factory=aiohttp.ClientSession,
        preflight_service=None,
        watchdog=None,
        thermal_guard=None,
        vram_probe=None,
    ) -> None:
        for role, _input_key in self._LOCKED_LOADERS:
            model_lock.entry(role)
        super().__init__(
            api_url=api_url,
            workflow_path=workflow_path,
            storage=storage,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            session_factory=session_factory,
            model_lock=model_lock,
            preflight_service=preflight_service,
            watchdog=watchdog,
            thermal_guard=thermal_guard,
            vram_probe=vram_probe,
        )

    # ------------------------------------------------------------------
    # Graph shaping
    # ------------------------------------------------------------------
    def _locked_checkpoint_name(self, model_lock: ModelLock | None) -> str:
        """The diffusion model is this dialect's base checkpoint."""
        if model_lock is None:
            return ""
        return model_lock.entry("diffusion_model").filename

    def _seed_slot(
        self, workflow: dict[str, Any]
    ) -> tuple[tuple[str, dict[str, Any]] | None, str]:
        return self._node_for_role(workflow, "noise", "RandomNoise"), "noise_seed"

    def _inject_locked_models(self, workflow: dict[str, Any]) -> None:
        if self._model_lock is None:
            raise ProviderError("FLUX.2 edit requires a model lock.")
        for role, input_key in self._LOCKED_LOADERS:
            node = self._node_for_role_by_class(
                workflow,
                {
                    "diffusion_model": "UNETLoader",
                    "text_encoder": "CLIPLoader",
                    "vae": "VAELoader",
                }[role],
            )
            if node is None:
                raise ProviderError(
                    f"FLUX.2 workflow has no loader node for role '{role}'."
                )
            node[1]["inputs"][input_key] = self._model_lock.entry(role).filename
        # A FLUX.2 edit graph must never carry SDXL-era loaders: mixing them
        # would silently invalidate the lock's provenance claim.
        for class_type in (
            "CheckpointLoaderSimple",
            "ControlNetLoader",
            "IPAdapterUnifiedLoader",
            "IPAdapterUnifiedLoaderFaceID",
        ):
            if self._node_for_role_by_class(workflow, class_type) is not None:
                raise ProviderError(
                    f"FLUX.2 edit workflow must not contain a {class_type} node."
                )

    def _inject_typed_constraints(
        self, workflow: dict[str, Any], request: KeyframeGenerationRequest
    ) -> None:
        constraints = request.visual_constraints
        edit_prompt = str(constraints.get("image_edit_prompt", "")).strip()
        if not edit_prompt:
            raise ProviderError(
                "FLUX.2 edit requires visual_constraints['image_edit_prompt']."
            )
        positive = self._node_for_role(
            workflow, "positive_prompt", "CLIPTextEncode"
        )
        if positive is None:
            raise ProviderError("ComfyUI workflow has no positive prompt node.")
        positive[1]["inputs"]["text"] = self._compose_edit_text(
            edit_prompt, request, constraints
        )

        negative = self._node_for_role(workflow, "negative_prompt")
        if negative is None:
            raise ProviderError("ComfyUI workflow has no negative prompt node.")
        if negative[1].get("class_type") != "ConditioningZeroOut":
            raise ProviderError(
                "FLUX.2 edit expects an inert ConditioningZeroOut negative branch."
            )

        width = int(request.width)
        height = int(request.height)
        if width <= 0 or height <= 0:
            raise ProviderError("FLUX.2 edit requires positive target dimensions.")

        noise = self._node_for_role(workflow, "noise", "RandomNoise")
        if noise is None:
            raise ProviderError("ComfyUI workflow has no noise node.")
        noise[1]["inputs"]["noise_seed"] = int(request.seed or 0)

        scheduler = self._node_for_role(workflow, "scheduler", "Flux2Scheduler")
        if scheduler is None:
            raise ProviderError("ComfyUI workflow has no sigma-schedule node.")
        steps = int(
            constraints.get(
                "sampling_steps", scheduler[1]["inputs"].get("steps", 4)
            )
        )
        if not 1 <= steps <= 50:
            raise ProviderError("FLUX.2 edit steps must be between 1 and 50.")
        scheduler[1]["inputs"].update(
            {"steps": steps, "width": width, "height": height}
        )

        latent = self._node_for_role(
            workflow, "empty_latent", "EmptyFlux2LatentImage"
        )
        if latent is None:
            raise ProviderError("ComfyUI workflow has no empty-latent node.")
        latent[1]["inputs"]["width"] = width
        latent[1]["inputs"]["height"] = height

        guider = self._node_for_role(workflow, "guider", "CFGGuider")
        if guider is None:
            raise ProviderError("ComfyUI workflow has no guider node.")
        cfg = float(constraints.get("guidance_scale", guider[1]["inputs"]["cfg"]))
        if not 0.0 < cfg <= 30.0:
            raise ProviderError("FLUX.2 edit guidance scale is outside safe bounds.")
        guider[1]["inputs"]["cfg"] = cfg

        megapixels = float(constraints.get("image_edit_megapixels", 1.0))
        if not 0.1 <= megapixels <= 4.0:
            raise ProviderError("FLUX.2 edit megapixels must be between 0.1 and 4.")
        for _node_id, scale in self._nodes_for_role(workflow, "reference_scale"):
            scale["inputs"]["megapixels"] = megapixels

    @staticmethod
    def _compose_edit_text(
        edit_prompt: str,
        request: KeyframeGenerationRequest,
        constraints: dict[str, Any],
    ) -> str:
        """Return the single instruction text this dialect conditions on.

        FLUX.2 Klein is guidance-distilled and runs at cfg 1.0, where negative
        conditioning is mathematically inert. Prohibitions therefore have to
        live in the instruction itself when they are wanted at all. The default
        is to leave the proven prompt untouched so the baseline reproduces.
        """
        mode = str(constraints.get("image_edit_negative_mode", "omit")).strip()
        if mode not in {"omit", "append"}:
            raise ProviderError(
                "image_edit_negative_mode must be 'omit' or 'append'."
            )
        if mode == "omit":
            return edit_prompt
        negatives = constraints.get("image_edit_negative_prompts") or (
            request.negative_prompts
        )
        values = [
            str(item).strip() for item in negatives if str(item).strip()
        ]
        if not values:
            return edit_prompt
        return f"{edit_prompt} Avoid: {', '.join(dict.fromkeys(values))}."

    def _connected_reference_nodes(self, workflow: dict[str, Any]) -> list[str]:
        """Return reference loaders in graph order, not dict order."""
        reachable = self._connected_nodes_for_role(workflow, "reference_image")
        return sorted(
            reachable,
            key=lambda node_id: int(
                workflow[node_id].get("_meta", {}).get("selma_index", 0)
            ),
        )

    def _select_reference_slots(
        self, workflow: dict[str, Any], *, reference_count: int
    ) -> list[str]:
        """Drop the reference slots this request does not fill.

        The template declares three chainable slots because the turnaround
        wants up to three (source plus two accepted neighbours), yet a single
        edit may legitimately carry one. Because the slots are *chained* rather
        than blended, an untouched slot would keep its template placeholder
        filename in the prompt: queue validation fails at best, and at worst
        the edit silently conditions on whatever image already sits under that
        name. So the unused branch is removed and the ``ReferenceLatent`` chain
        is re-wired over the slots that remain.
        """
        if reference_count <= 0:
            raise ProviderError(
                "FLUX.2 edit requires at least one reference image."
            )
        slots = self._connected_reference_nodes(workflow)
        if len(slots) < reference_count:
            raise ProviderError(
                "ComfyUI workflow does not contain enough connected SELMA "
                "reference nodes."
            )
        used, dropped = slots[:reference_count], slots[reference_count:]
        for load_id in dropped:
            for node_id in self._reference_slot_nodes(workflow, load_id):
                workflow.pop(node_id, None)
        self._rewire_reference_chain(workflow, load_ids=used)
        return used

    # ------------------------------------------------------------------
    # Reference slot surgery
    # ------------------------------------------------------------------
    @staticmethod
    def _role_of(node: dict[str, Any]) -> str:
        return str(node.get("_meta", {}).get("selma_role", ""))

    def _consumers(self, workflow: dict[str, Any], node_id: str) -> list[str]:
        return [
            other_id
            for other_id, node in workflow.items()
            if any(
                isinstance(value, list)
                and len(value) == 2
                and str(value[0]) == node_id
                for value in node.get("inputs", {}).values()
            )
        ]

    def _reference_slot_nodes(
        self, workflow: dict[str, Any], load_id: str
    ) -> list[str]:
        """Return one slot's nodes: load, scale, encode, chained bindings."""
        nodes = [load_id]
        current = [load_id]
        for role in ("reference_scale", "reference_latent", "reference_binding"):
            visited: list[str] = []
            for node_id in current:
                for consumer in self._consumers(workflow, node_id):
                    if (
                        self._role_of(workflow[consumer]) == role
                        and consumer not in nodes
                        and consumer not in visited
                    ):
                        visited.append(consumer)
            nodes.extend(visited)
            current = visited
            if not current:
                break
        return nodes

    def _chain_root(self, workflow: dict[str, Any], node_id: str) -> str:
        """Return the prompt role a conditioning chain ultimately starts from."""
        seen: set[str] = set()
        current: str | None = node_id
        while current is not None and current not in seen:
            seen.add(current)
            node = workflow.get(current)
            if node is None:
                return ""
            role = self._role_of(node)
            if role in {"positive_prompt", "negative_prompt"}:
                return role
            conditioning = node.get("inputs", {}).get("conditioning")
            current = (
                str(conditioning[0])
                if isinstance(conditioning, list) and len(conditioning) == 2
                else None
            )
        return ""

    def _positive_binding(
        self, workflow: dict[str, Any], load_id: str
    ) -> str | None:
        for node_id in self._reference_slot_nodes(workflow, load_id):
            node = workflow.get(node_id)
            if node is None or self._role_of(node) != "reference_binding":
                continue
            if self._chain_root(workflow, node_id) == "positive_prompt":
                return node_id
        return None

    def _rewire_reference_chain(
        self, workflow: dict[str, Any], *, load_ids: list[str]
    ) -> None:
        """Chain the surviving slots in order and point the guider at the tail."""
        chain: list[str] = []
        for load_id in load_ids:
            binding = self._positive_binding(workflow, load_id)
            if binding is None:
                raise ProviderError(
                    "FLUX.2 workflow has no positive ReferenceLatent node for "
                    f"reference slot '{load_id}'."
                )
            chain.append(binding)
        positive = self._node_for_role(workflow, "positive_prompt", "CLIPTextEncode")
        guider = self._node_for_role(workflow, "guider", "CFGGuider")
        if positive is None or guider is None:
            raise ProviderError(
                "FLUX.2 workflow is missing its prompt or guider node."
            )
        previous = [positive[0], 0]
        for binding_id in chain:
            workflow[binding_id]["inputs"]["conditioning"] = list(previous)
            previous = [binding_id, 0]
        guider[1]["inputs"]["positive"] = list(previous)

    def _inject_reference_weights(
        self,
        workflow: dict[str, Any],
        *,
        request: KeyframeGenerationRequest,
        reference_count: int,
    ) -> None:
        """Reference latents carry no per-image weight in this dialect.

        Weights are still validated so a caller cannot believe a blend was
        applied when the graph ignores it.
        """
        del workflow
        raw_weights = request.visual_constraints.get("identity_reference_weights")
        if raw_weights is None:
            return
        if not isinstance(raw_weights, (list, tuple)):
            raise ProviderError("identity_reference_weights must be a list.")
        if len(raw_weights) != reference_count:
            raise ProviderError(
                "identity_reference_weights must match the selected reference count."
            )
        if any(not 0.0 <= float(weight) <= 2.0 for weight in raw_weights):
            raise ProviderError("Identity reference weights must be between 0 and 2.")

    def _select_character_lora(
        self,
        workflow: dict[str, Any],
        request: KeyframeGenerationRequest,
    ) -> tuple[dict[str, Any] | None, list[Any]]:
        del request
        unet = self._node_for_role(workflow, "diffusion_model", "UNETLoader")
        if unet is None:
            raise ProviderError("FLUX.2 workflow has no diffusion-model node.")
        return None, [unet[0], 0]

    def _select_identity_conditioning(
        self,
        workflow: dict[str, Any],
        *,
        reference_count: int,
        base_model_source: list[Any],
    ) -> None:
        """Identity is bound by ``ReferenceLatent``, not by an adapter chain."""
        del workflow, reference_count, base_model_source

    def _select_pose_conditioning(
        self,
        workflow: dict[str, Any],
        request: KeyframeGenerationRequest,
        *,
        use_pose: bool,
        controlnet_type: str = "openpose",
    ) -> None:
        del workflow, controlnet_type
        if use_pose:
            raise ProviderError(
                "FLUX.2 edit does not use pose templates; clear pose_storage_key."
            )
        if request.visual_constraints.get("pose_storage_key"):
            raise ProviderError(
                "FLUX.2 edit does not use pose templates; clear pose_storage_key."
            )

    def _select_latent_source(
        self,
        workflow: dict[str, Any],
        *,
        request: KeyframeGenerationRequest,
        use_reference: bool,
    ) -> None:
        """The sampler always starts from the target canvas.

        Picture 1 arrives through the conditioning chain, so there is no
        reference-latent/denoise pair to switch between here.
        """
        del request, use_reference
        sample = self._node_for_role(workflow, "sample", "SamplerCustomAdvanced")
        if sample is None:
            raise ProviderError("FLUX.2 workflow has no SamplerCustomAdvanced node.")
        latent = self._node_for_role(
            workflow, "empty_latent", "EmptyFlux2LatentImage"
        )
        if latent is None:
            raise ProviderError("FLUX.2 workflow has no empty-latent node.")
        sample[1]["inputs"]["latent_image"] = [latent[0], 0]


__all__ = ["ComfyUIFlux2EditProvider"]
