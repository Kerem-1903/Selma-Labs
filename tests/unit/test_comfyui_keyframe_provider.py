from __future__ import annotations

import base64
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from config.provider_registry import get_keyframe_generation_provider
from config.settings import Settings
from core.domain.exceptions import ProviderError, StorageError
from core.domain.ports.storage_port import StoragePort
from core.domain.value_objects.keyframe_generation_request import (
    KeyframeGenerationRequest,
)
from core.domain.value_objects.storage_reference import StorageReference
from infrastructure.providers.keyframe.comfyui_keyframe_provider import (
    ComfyUIKeyframeProvider,
)
from infrastructure.providers.keyframe.fake_keyframe_generation_provider import (
    FakeKeyframeGenerationProvider,
)

PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
WORKFLOW_PATH = Path(__file__).parents[2] / "assets" / "comfyui_keyframe_workflow.json"


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


class FakeResponse:
    def __init__(
        self,
        *,
        status: int = 200,
        payload: dict[str, Any] | None = None,
        body: bytes = b"",
        content_type: str = "application/json",
    ) -> None:
        self.status = status
        self._payload = payload or {}
        self._body = body
        self.headers = {"Content-Type": content_type}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        del exc_type, exc, traceback

    async def json(self) -> dict[str, Any]:
        return self._payload

    async def text(self) -> str:
        return self._body.decode("utf-8", errors="replace")

    async def read(self) -> bytes:
        return self._body


class FakeSession:
    def __init__(self) -> None:
        self.uploaded_forms: list[Any] = []
        self.queued_workflow: dict[str, Any] | None = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        del exc_type, exc, traceback

    def post(self, url: str, *, data=None, json=None):
        if url.endswith("/upload/image"):
            self.uploaded_forms.append(data)
            return FakeResponse(
                status=200,
                payload={"name": "reference.png", "subfolder": "selma", "type": "input"},
            )
        if url.endswith("/prompt"):
            self.queued_workflow = json["prompt"]
            return FakeResponse(status=200, payload={"prompt_id": "prompt-1"})
        raise AssertionError(f"Unexpected POST URL: {url}")

    def get(self, url: str, *, params=None):
        if "/history/" in url:
            return FakeResponse(
                payload={
                    "prompt-1": {
                        "status": {"status_str": "success"},
                        "outputs": {
                            "9": {
                                "images": [
                                    {"filename": "keyframe.png", "subfolder": "", "type": "output"}
                                ]
                            }
                        },
                    }
                }
            )
        if url.endswith("/view"):
            assert params == {
                "filename": "keyframe.png",
                "subfolder": "",
                "type": "output",
            }
            return FakeResponse(body=PNG_BYTES, content_type="image/png")
        raise AssertionError(f"Unexpected GET URL: {url}")


def _request(*, with_reference: bool = True) -> KeyframeGenerationRequest:
    references = (
        [
            {
                "view": "FACE_CLOSEUP",
                "asset_id": "asset-face",
                "storage_key": "characters/akira/face.png",
            },
            {
                "view": "FRONT",
                "asset_id": "asset-front",
                "storage_key": "characters/akira/front.png",
            },
        ]
        if with_reference
        else []
    )
    return KeyframeGenerationRequest(
        shot_contract_id="shot-1",
        camera_constraints={"angle": "close-up", "lens": "50mm", "movement": "static"},
        action_constraints={"primary_action": "draw katana", "secondary_actions": []},
        visual_constraints={
            "prompt": "locked Akira visual identity",
            "lighting": "low-key",
            "environment_style": "neon street",
            "weather": "rain",
        },
        character_conditioning=(
            {
                "character_id": "akira",
                "identity_constraints": {"hair": "black", "eye_color": "brown"},
                "style_profile": {"base_style": "anime"},
                "continuity_state": {
                    "active_outfit_id": "battle-jacket",
                    "injuries": ["shoulder wound"],
                    "held_objects": ["katana"],
                    "emotion": "determined",
                    "location": "neon street",
                },
                "references": references,
            },
        ),
        reference_asset_ids=("asset-face", "asset-front") if with_reference else (),
        reference_storage_keys=(
            "characters/akira/face.png",
            "characters/akira/front.png",
        )
        if with_reference
        else (),
        negative_prompts=("identity drift", "extra fingers"),
        width=1280,
        height=720,
        seed=1903,
    )


def test_positive_prompt_keeps_explicit_selma_visual_contract():
    prompt = ComfyUIKeyframeProvider._build_positive_prompt(_request())

    assert "locked Akira visual identity" in prompt
    assert "draw katana" in prompt


def test_positive_prompt_flattens_identity_and_composition_contracts():
    request = replace(
        _request(),
        visual_constraints={
            **_request().visual_constraints,
            "composition_contract": "face occupies 55-70% of frame",
            "identity_contract": {
                "hair": "long black hair",
                "immutable_marks": ("one red streak", "amber eyes"),
            },
        },
    )

    prompt = ComfyUIKeyframeProvider._build_positive_prompt(request)

    assert "face occupies 55-70% of frame" in prompt
    assert "locked hair: (long black hair:1.25)" in prompt
    assert "locked immutable_marks: (one red streak:1.25)" in prompt
    assert "locked immutable_marks: (amber eyes:1.25)" in prompt


@pytest.mark.asyncio
async def test_provider_uploads_selected_reference_and_injects_typed_contract():
    storage = MemoryStorage(
        {
            "characters/akira/face.png": PNG_BYTES,
            "characters/akira/front.png": PNG_BYTES,
        }
    )
    session = FakeSession()
    provider = ComfyUIKeyframeProvider(
        api_url="http://127.0.0.1:8188",
        workflow_path=WORKFLOW_PATH,
        storage=storage,
        session_factory=lambda **kwargs: session,
    )

    generated = await provider.generate_keyframe(_request())

    assert len(session.uploaded_forms) == 1
    workflow = session.queued_workflow
    assert workflow is not None
    assert workflow["10"]["inputs"]["image"] == "selma/reference.png"
    assert workflow["3"]["inputs"]["latent_image"] == ["13", 0]
    assert workflow["3"]["inputs"]["model"] == ["20", 0]
    assert workflow["18"]["inputs"]["model"] == ["4", 0]
    assert workflow["20"]["inputs"]["model"] == ["18", 0]
    assert workflow["20"]["inputs"]["ipadapter"] == ["18", 1]
    assert workflow["3"]["inputs"]["seed"] == 1903
    assert workflow["4"]["inputs"]["ckpt_name"] == "sd_xl_base_1.0.safetensors"
    assert workflow["12"]["inputs"]["width"] == 1280
    assert workflow["12"]["inputs"]["height"] == 720
    assert "draw katana" in workflow["6"]["inputs"]["text"]
    assert "battle-jacket" in workflow["6"]["inputs"]["text"]
    assert "identity drift" in workflow["7"]["inputs"]["text"]
    assert generated.image_bytes == PNG_BYTES
    assert generated.width == 1
    assert generated.height == 1
    assert generated.metadata["reference_asset_ids"] == ["asset-face"]


@pytest.mark.asyncio
async def test_provider_uses_empty_latent_when_shot_has_no_character_reference():
    session = FakeSession()
    provider = ComfyUIKeyframeProvider(
        api_url="http://127.0.0.1:8188",
        workflow_path=WORKFLOW_PATH,
        storage=MemoryStorage(),
        session_factory=lambda **kwargs: session,
    )

    await provider.generate_keyframe(_request(with_reference=False))

    assert session.uploaded_forms == []
    assert session.queued_workflow["3"]["inputs"]["latent_image"] == ["5", 0]
    assert session.queued_workflow["3"]["inputs"]["model"] == ["4", 0]
    assert session.queued_workflow["3"]["inputs"]["positive"] == ["6", 0]
    assert session.queued_workflow["3"]["inputs"]["negative"] == ["7", 0]
    assert session.queued_workflow["5"]["inputs"]["width"] == 1280
    assert session.queued_workflow["5"]["inputs"]["height"] == 720
    assert "13" in session.queued_workflow


@pytest.mark.asyncio
async def test_provider_uploads_pose_asset_and_enables_controlnet_conditioning():
    storage = MemoryStorage(
        {
            "characters/akira/face.png": PNG_BYTES,
            "characters/akira/front.png": PNG_BYTES,
            "characters/akira/poses/sprint.png": PNG_BYTES,
        }
    )
    session = FakeSession()
    provider = ComfyUIKeyframeProvider(
        api_url="http://127.0.0.1:8188",
        workflow_path=WORKFLOW_PATH,
        storage=storage,
        session_factory=lambda **kwargs: session,
    )
    request = replace(
        _request(),
        visual_constraints={
            **_request().visual_constraints,
            "pose_storage_key": "characters/akira/poses/sprint.png",
            "identity_strength": 0.65,
            "pose_strength": 0.85,
        },
    )

    generated = await provider.generate_keyframe(request)

    assert len(session.uploaded_forms) == 2
    assert session.queued_workflow["23"]["inputs"]["image"] == "selma/reference.png"
    assert session.queued_workflow["3"]["inputs"]["positive"] == ["22", 0]
    assert session.queued_workflow["3"]["inputs"]["negative"] == ["22", 1]
    assert session.queued_workflow["20"]["inputs"]["weight"] == 0.65
    assert session.queued_workflow["22"]["inputs"]["strength"] == 0.85
    assert generated.metadata["pose_storage_key"] == (
        "characters/akira/poses/sprint.png"
    )


@pytest.mark.asyncio
async def test_provider_identity_only_mode_reduces_composition_transfer():
    session = FakeSession()
    provider = ComfyUIKeyframeProvider(
        api_url="http://127.0.0.1:8188",
        workflow_path=WORKFLOW_PATH,
        storage=MemoryStorage(
            {
                "characters/akira/face.png": PNG_BYTES,
                "characters/akira/front.png": PNG_BYTES,
            }
        ),
        session_factory=lambda **kwargs: session,
    )
    request = replace(
        _request(),
        visual_constraints={
            **_request().visual_constraints,
            "identity_mode": "identity_only",
        },
    )

    await provider.generate_keyframe(request)

    adapter = session.queued_workflow["20"]["inputs"]
    assert adapter["weight_type"] == "weak input"
    assert adapter["combine_embeds"] == "average"
    assert adapter["end_at"] == 0.65
    assert adapter["embeds_scaling"] == "K+V w/ C penalty"


@pytest.mark.asyncio
async def test_provider_rejects_invalid_identity_timing():
    provider = ComfyUIKeyframeProvider(
        api_url="http://127.0.0.1:8188",
        workflow_path=WORKFLOW_PATH,
        storage=MemoryStorage(
            {
                "characters/akira/face.png": PNG_BYTES,
                "characters/akira/front.png": PNG_BYTES,
            }
        ),
        session_factory=lambda **kwargs: FakeSession(),
    )
    request = replace(
        _request(),
        visual_constraints={
            **_request().visual_constraints,
            "identity_start_at": 0.9,
            "identity_end_at": 0.2,
        },
    )

    with pytest.raises(ProviderError, match="start_at"):
        await provider.generate_keyframe(request)


@pytest.mark.asyncio
async def test_provider_injects_model_specific_sampler_settings():
    session = FakeSession()
    provider = ComfyUIKeyframeProvider(
        api_url="http://127.0.0.1:8188",
        workflow_path=WORKFLOW_PATH,
        storage=MemoryStorage(
            {
                "characters/akira/face.png": PNG_BYTES,
                "characters/akira/front.png": PNG_BYTES,
            }
        ),
        session_factory=lambda **kwargs: session,
    )
    request = replace(
        _request(),
        visual_constraints={
            **_request().visual_constraints,
            "sampling_steps": 28,
            "guidance_scale": 5.0,
            "sampler_name": "euler_ancestral",
            "scheduler": "normal",
        },
    )

    await provider.generate_keyframe(request)

    sampler = session.queued_workflow["3"]["inputs"]
    assert sampler["steps"] == 28
    assert sampler["cfg"] == 5.0
    assert sampler["sampler_name"] == "euler_ancestral"
    assert sampler["scheduler"] == "normal"


@pytest.mark.asyncio
async def test_provider_connects_character_lora_before_ipadapter():
    session = FakeSession()
    provider = ComfyUIKeyframeProvider(
        api_url="http://127.0.0.1:8188",
        workflow_path=WORKFLOW_PATH,
        storage=MemoryStorage(
            {
                "characters/akira/face.png": PNG_BYTES,
                "characters/akira/front.png": PNG_BYTES,
            }
        ),
        character_lora_name="selma-akira-v1.safetensors",
        character_lora_trigger_token="selma_akira_v1",
        session_factory=lambda **kwargs: session,
    )

    generated = await provider.generate_keyframe(_request())

    workflow = session.queued_workflow
    assert workflow["24"]["inputs"]["lora_name"] == (
        "selma-akira-v1.safetensors"
    )
    assert workflow["18"]["inputs"]["model"] == ["24", 0]
    assert workflow["6"]["inputs"]["clip"] == ["24", 1]
    assert workflow["7"]["inputs"]["clip"] == ["24", 1]
    assert workflow["3"]["inputs"]["model"] == ["20", 0]
    assert workflow["6"]["inputs"]["text"].startswith("selma_akira_v1, ")
    assert generated.metadata["character_lora"] == {
        "name": "selma-akira-v1.safetensors",
        "trigger_token": "selma_akira_v1",
        "strength_model": 0.8,
        "strength_clip": 0.8,
    }


@pytest.mark.asyncio
async def test_provider_can_use_character_lora_without_ipadapter_reference():
    session = FakeSession()
    provider = ComfyUIKeyframeProvider(
        api_url="http://127.0.0.1:8188",
        workflow_path=WORKFLOW_PATH,
        storage=MemoryStorage(),
        character_lora_name="selma-akira-v1.safetensors",
        character_lora_trigger_token="selma_akira_v1",
        session_factory=lambda **kwargs: session,
    )

    generated = await provider.generate_keyframe(_request(with_reference=False))

    assert session.uploaded_forms == []
    assert session.queued_workflow["3"]["inputs"]["model"] == ["24", 0]
    assert session.queued_workflow["6"]["inputs"]["clip"] == ["24", 1]
    assert generated.metadata["character_lora"]["name"] == (
        "selma-akira-v1.safetensors"
    )


@pytest.mark.asyncio
async def test_provider_rejects_lora_without_trigger_token():
    provider = ComfyUIKeyframeProvider(
        api_url="http://127.0.0.1:8188",
        workflow_path=WORKFLOW_PATH,
        storage=MemoryStorage(),
        character_lora_name="selma-akira-v1.safetensors",
        session_factory=lambda **kwargs: FakeSession(),
    )

    with pytest.raises(ProviderError, match="trigger token"):
        await provider.generate_keyframe(_request(with_reference=False))


def test_registry_requires_shared_storage_for_comfyui():
    settings = Settings(keyframe_generation_provider="comfyui")
    with pytest.raises(ValueError, match="StoragePort"):
        get_keyframe_generation_provider(settings)

    provider = get_keyframe_generation_provider(settings, storage=MemoryStorage())
    assert isinstance(provider, ComfyUIKeyframeProvider)


def test_registry_keeps_offline_fake_as_default():
    provider = get_keyframe_generation_provider(Settings())
    assert isinstance(provider, FakeKeyframeGenerationProvider)


@pytest.mark.asyncio
async def test_provider_rejects_workflow_with_disconnected_reference_node(tmp_path):
    workflow_path = tmp_path / "workflow.json"
    workflow = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
    workflow["3"]["inputs"]["latent_image"] = ["5", 0]
    # Disconnect the reference node for the test
    if "20" in workflow:
        workflow["20"]["inputs"]["image"] = ["5", 0] # Break the connection to node 12 (ImageScale)
    workflow_path.write_text(json.dumps(workflow), encoding="utf-8")
    provider = ComfyUIKeyframeProvider(
        api_url="http://127.0.0.1:8188",
        workflow_path=workflow_path,
        storage=MemoryStorage({"characters/akira/face.png": PNG_BYTES}),
        session_factory=lambda **kwargs: FakeSession(),
    )

    with pytest.raises(ProviderError, match="connected SELMA reference"):
        await provider.generate_keyframe(_request())
