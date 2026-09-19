from __future__ import annotations

import json
from pathlib import Path

import pytest

from config.provider_registry import get_keyframe_generation_provider
from config.settings import Settings
from core.domain.exceptions import ProviderError, StorageError
from core.domain.ports.storage_port import StoragePort
from core.domain.value_objects.keyframe_generation_request import (
    KeyframeGenerationRequest,
)
from core.domain.value_objects.production_infra import ModelLock, ModelLockEntry
from core.domain.value_objects.storage_reference import StorageReference
from infrastructure.providers.keyframe.comfyui_flux2_edit_provider import (
    ComfyUIFlux2EditProvider,
)

ROOT = Path(__file__).parents[2]
WORKFLOW_PATH = ROOT / "assets" / "comfyui_flux2_klein_edit_workflow.json"

DIFFUSION = "flux-2-klein-4b-fp8.safetensors"
TEXT_ENCODER = "qwen_3_4b.safetensors"
VAE = "flux2-vae.safetensors"


class MemoryStorage(StoragePort):
    def __init__(self, assets: dict[str, bytes] | None = None) -> None:
        self.assets = assets or {}

    async def save(self, key: str, data: bytes, content_type: str) -> StorageReference:
        del content_type
        self.assets[key] = data
        return StorageReference(key=key, path=f"memory://{key}", size_bytes=len(data))

    async def load(self, key: str) -> bytes:
        try:
            return self.assets[key]
        except KeyError as error:
            raise StorageError(f"Missing memory asset: {key}") from error

    async def exists(self, key: str) -> bool:
        return key in self.assets

    def upload_file(self, file_stream, destination_path: str, content_type: str) -> str:
        del file_stream, content_type
        return f"memory://{destination_path}"

    def download_file(self, source_path: str, local_destination: str) -> bool:
        del source_path, local_destination
        return False

    def delete_file(self, file_path: str) -> bool:
        return self.assets.pop(file_path, None) is not None


def _lock() -> ModelLock:
    return ModelLock(
        schema_version=1,
        comfyui_root="C:/ComfyUI",
        entries=tuple(
            ModelLockEntry(
                role=role,
                filename=filename,
                relative_path=f"models/{filename}",
                sha256="a" * 64,
                size_bytes=1,
            )
            for role, filename in (
                ("diffusion_model", DIFFUSION),
                ("text_encoder", TEXT_ENCODER),
                ("vae", VAE),
            )
        ),
    )


def _provider() -> ComfyUIFlux2EditProvider:
    return ComfyUIFlux2EditProvider(
        api_url="http://127.0.0.1:8188",
        workflow_path=WORKFLOW_PATH,
        storage=MemoryStorage(),
        model_lock=_lock(),
    )


def _workflow() -> dict:
    return json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))


def _request(**overrides) -> KeyframeGenerationRequest:
    constraints: dict = {
        "image_edit_prompt": (
            "Edit Picture 1. Change only the viewpoint: show a strict left side "
            "profile, nose pointing to image left, with only one eye visible."
        ),
        "view": "PROFILE_LEFT",
    }
    constraints.update(overrides)
    return KeyframeGenerationRequest(
        shot_contract_id="character-reference-kaito-profile_left",
        camera_constraints={"angle": "left profile"},
        action_constraints={"primary_action": "neutral reference pose"},
        visual_constraints=constraints,
        width=768,
        height=1152,
        seed=42,
    )


def test_provider_declares_the_edit_dialect_name():
    assert _provider().name == "comfyui:flux2-edit"


def test_provider_requires_all_three_flux_locked_roles():
    lock = ModelLock(
        schema_version=1,
        comfyui_root="C:/ComfyUI",
        entries=(
            ModelLockEntry(
                role="diffusion_model",
                filename=DIFFUSION,
                relative_path=f"models/{DIFFUSION}",
                sha256="a" * 64,
                size_bytes=1,
            ),
        ),
    )

    with pytest.raises(ValueError, match="text_encoder"):
        ComfyUIFlux2EditProvider(
            api_url="http://127.0.0.1:8188",
            workflow_path=WORKFLOW_PATH,
            storage=MemoryStorage(),
            model_lock=lock,
        )


def test_locked_models_replace_every_flux_loader():
    workflow = _workflow()
    _provider()._inject_locked_models(workflow)

    assert workflow["unet"]["inputs"]["unet_name"] == DIFFUSION
    assert workflow["clip"]["inputs"]["clip_name"] == TEXT_ENCODER
    assert workflow["clip"]["inputs"]["type"] == "flux2"
    assert workflow["vae"]["inputs"]["vae_name"] == VAE


def test_locked_models_reject_an_sdxl_loader_in_the_graph():
    workflow = _workflow()
    workflow["stowaway"] = {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {"ckpt_name": "animagine-xl-4.0-opt.safetensors"},
    }

    with pytest.raises(ProviderError, match="CheckpointLoaderSimple"):
        _provider()._inject_locked_models(workflow)


def test_edit_instruction_seed_steps_and_canvas_are_injected():
    workflow = _workflow()
    provider = _provider()
    request = _request()

    provider._inject_typed_constraints(workflow, request)

    assert workflow["positive"]["inputs"]["text"] == (
        request.visual_constraints["image_edit_prompt"]
    )
    assert workflow["noise"]["inputs"]["noise_seed"] == 42
    assert workflow["sigmas"]["inputs"]["steps"] == 4
    assert workflow["sigmas"]["inputs"]["width"] == 768
    assert workflow["sigmas"]["inputs"]["height"] == 1152
    assert workflow["latent"]["inputs"]["width"] == 768
    assert workflow["latent"]["inputs"]["height"] == 1152
    assert workflow["guider"]["inputs"]["cfg"] == 1.0


def test_edit_instruction_is_required():
    workflow = _workflow()
    request = KeyframeGenerationRequest(
        shot_contract_id="character-reference-kaito-profile_left",
        camera_constraints={},
        action_constraints={},
        visual_constraints={"view": "PROFILE_LEFT"},
        width=768,
        height=1152,
        seed=1,
    )

    with pytest.raises(ProviderError, match="image_edit_prompt"):
        _provider()._inject_typed_constraints(workflow, request)


def test_negatives_are_omitted_by_default_to_reproduce_the_baseline():
    provider = _provider()

    assert provider._compose_edit_text(
        "Edit Picture 1.", _request(), {"image_edit_prompt": "Edit Picture 1."}
    ) == "Edit Picture 1."

    appended = provider._compose_edit_text(
        "Edit Picture 1.",
        _request(),
        {
            "image_edit_prompt": "Edit Picture 1.",
            "image_edit_negative_mode": "append",
            "image_edit_negative_prompts": ["second person", "second person", "style change"],
        },
    )
    assert appended.startswith("Edit Picture 1. Avoid: second person, style change.")

    with pytest.raises(ProviderError, match="image_edit_negative_mode"):
        provider._compose_edit_text(
            "Edit Picture 1.", _request(), {"image_edit_negative_mode": "shout"}
        )


def test_reference_nodes_are_ordered_by_declared_index():
    workflow = _workflow()
    shuffled = {
        "load_neighbor2": workflow["load_neighbor2"],
        "load_neighbor": workflow["load_neighbor"],
        **{key: value for key, value in workflow.items() if not key.startswith("load_")},
        "load_source": workflow["load_source"],
    }

    assert _provider()._connected_reference_nodes(shuffled) == [
        "load_source",
        "load_neighbor",
        "load_neighbor2",
    ]


def test_seed_slot_tracks_the_flux_noise_node():
    node, key = _provider()._seed_slot(_workflow())

    assert node is not None
    assert node[0] == "noise"
    assert key == "noise_seed"


def test_pose_templates_are_rejected_by_this_dialect():
    with pytest.raises(ProviderError, match="pose templates"):
        _provider()._select_pose_conditioning(
            _workflow(), _request(pose_storage_key="characters/_pose_templates/x.png"),
            use_pose=True,
        )


def test_sampler_always_starts_from_the_target_canvas():
    workflow = _workflow()
    _provider()._select_latent_source(workflow, request=_request(), use_reference=True)

    assert workflow["sample"]["inputs"]["latent_image"] == ["latent", 0]


def test_reference_weights_are_validated_but_never_blended():
    provider = _provider()
    provider._inject_reference_weights(
        _workflow(), request=_request(), reference_count=2
    )

    with pytest.raises(ProviderError, match="must match"):
        provider._inject_reference_weights(
            _workflow(),
            request=_request(identity_reference_weights=[1.0]),
            reference_count=2,
        )
    with pytest.raises(ProviderError, match="between 0 and 2"):
        provider._inject_reference_weights(
            _workflow(),
            request=_request(identity_reference_weights=[3.0, 1.0]),
            reference_count=2,
        )


def test_registry_requires_shared_storage_for_the_edit_dialect():
    settings = Settings(
        keyframe_generation_provider="comfyui-flux2-edit",
        comfyui_flux2_model_lock_path=str(ROOT / "models-flux2.lock.json"),
    )

    with pytest.raises(ValueError, match="StoragePort"):
        get_keyframe_generation_provider(settings)

    provider = get_keyframe_generation_provider(settings, storage=MemoryStorage())
    assert isinstance(provider, ComfyUIFlux2EditProvider)
    assert provider.name == "comfyui:flux2-edit"


def test_flux_workflow_template_matches_the_locked_model_names():
    workflow = _workflow()

    assert workflow["unet"]["inputs"]["unet_name"] == DIFFUSION
    assert workflow["clip"]["inputs"]["clip_name"] == TEXT_ENCODER
    assert workflow["vae"]["inputs"]["vae_name"] == VAE
    assert workflow["negative"]["class_type"] == "ConditioningZeroOut"
    assert workflow["guider"]["inputs"]["positive"] == [
        "positive_reference_neighbor2",
        0,
    ]


def _dangling_links(workflow: dict) -> list[tuple[str, str]]:
    dangling = []
    for node_id, node in workflow.items():
        for field, value in node.get("inputs", {}).items():
            if isinstance(value, list) and len(value) == 2 and str(value[0]) not in workflow:
                dangling.append((node_id, field))
    return dangling


def _loaded_images(workflow: dict) -> list[str]:
    return sorted(
        node_id
        for node_id, node in workflow.items()
        if node.get("class_type") == "LoadImage"
    )


def test_a_single_reference_prunes_every_chained_neighbour_slot():
    # FACE_CLOSEUP and FRONT carry exactly one reference; the untouched
    # neighbour slots used to reach the queue with their placeholder names.
    workflow = _workflow()

    used = _provider()._select_reference_slots(workflow, reference_count=1)

    assert used == ["load_source"]
    assert _loaded_images(workflow) == ["load_source"]
    assert workflow["guider"]["inputs"]["positive"] == ["positive_reference", 0]
    assert workflow["positive_reference"]["inputs"]["conditioning"] == [
        "positive",
        0,
    ]
    assert workflow["guider"]["inputs"]["negative"] == ["negative_reference", 0]
    assert _dangling_links(workflow) == []


def test_two_references_keep_a_contiguous_chain():
    # PROFILE_LEFT binds the source plus one accepted neighbour.
    workflow = _workflow()

    used = _provider()._select_reference_slots(workflow, reference_count=2)

    assert used == ["load_source", "load_neighbor"]
    assert _loaded_images(workflow) == ["load_neighbor", "load_source"]
    assert workflow["positive_reference_neighbor"]["inputs"]["conditioning"] == [
        "positive_reference",
        0,
    ]
    assert workflow["guider"]["inputs"]["positive"] == [
        "positive_reference_neighbor",
        0,
    ]
    assert _dangling_links(workflow) == []


def test_all_three_references_keep_the_original_chain():
    # BACK binds the source plus both profiles; this must be a no-op rewire.
    workflow = _workflow()

    used = _provider()._select_reference_slots(workflow, reference_count=3)

    assert used == ["load_source", "load_neighbor", "load_neighbor2"]
    assert _loaded_images(workflow) == [
        "load_neighbor",
        "load_neighbor2",
        "load_source",
    ]
    assert workflow["guider"]["inputs"]["positive"] == [
        "positive_reference_neighbor2",
        0,
    ]
    assert _dangling_links(workflow) == []


def test_the_edit_dialect_refuses_a_reference_free_request():
    with pytest.raises(ProviderError, match="at least one reference"):
        _provider()._select_reference_slots(_workflow(), reference_count=0)


def test_the_edit_dialect_refuses_more_references_than_slots():
    with pytest.raises(ProviderError, match="enough connected SELMA reference"):
        _provider()._select_reference_slots(_workflow(), reference_count=4)
