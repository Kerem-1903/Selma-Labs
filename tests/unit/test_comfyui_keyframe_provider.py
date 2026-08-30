import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from core.domain.exceptions import ProviderError
from core.domain.value_objects.keyframe_generation_request import KeyframeGenerationRequest
from infrastructure.providers.keyframe.comfyui_keyframe_provider import ComfyUIKeyframeProvider
import json

@pytest.fixture
def dummy_workflow(tmp_path):
    workflow_path = tmp_path / "workflow.json"
    workflow_data = {
        "1": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": ""}
        }
    }
    with open(workflow_path, "w") as f:
        json.dump(workflow_data, f)
    return str(workflow_path)

@pytest.fixture
def provider(dummy_workflow):
    return ComfyUIKeyframeProvider(api_url="http://localhost:8188", workflow_path=dummy_workflow)

@pytest.fixture
def valid_request():
    return KeyframeGenerationRequest(
        shot_contract_id="shot-1",
        camera_constraints={},
        action_constraints={},
        visual_constraints={"prompt": "A beautiful cinematic shot"},
        width=1024,
        height=1024
    )

def test_init(provider):
    assert provider.name == "comfyui_keyframe"
    assert provider.api_url == "http://localhost:8188"

@pytest.mark.asyncio
async def test_generate_keyframe_success(provider, valid_request):
    with patch("aiohttp.ClientSession.post") as mock_post, \
         patch("aiohttp.ClientSession.get") as mock_get:

        mock_post_response = AsyncMock()
        mock_post_response.status = 200
        mock_post_response.json.return_value = {"prompt_id": "test-prompt-id"}
        mock_post.return_value.__aenter__.return_value = mock_post_response

        mock_get_history_response = AsyncMock()
        mock_get_history_response.status = 200
        mock_get_history_response.json.return_value = {
            "test-prompt-id": {
                "outputs": {
                    "2": {
                        "images": [
                            {"filename": "test.png", "subfolder": "", "type": "output"}
                        ]
                    }
                }
            }
        }

        mock_get_view_response = AsyncMock()
        mock_get_view_response.status = 200
        mock_get_view_response.read.return_value = b"fake-image-bytes"

        mock_get.return_value.__aenter__.side_effect = [mock_get_history_response, mock_get_view_response]

        keyframe = await provider.generate_keyframe(valid_request)

        assert keyframe.image_bytes == b"fake-image-bytes"
        assert keyframe.content_type == "image/png"
        assert keyframe.provider_asset_id == "test.png"
        assert keyframe.width == 1024
        assert keyframe.height == 1024

@pytest.mark.asyncio
async def test_generate_keyframe_missing_prompt_fallbacks_to_generic(provider, valid_request):
    # A5 requests might not have a prompt, should fallback to constructed prompt from constraints
    invalid_request = KeyframeGenerationRequest(
        shot_contract_id="shot-1",
        camera_constraints={"angle": "close up"},
        action_constraints={"primary_action": "running fast"},
        visual_constraints={},
        width=1024,
        height=1024
    )
    with patch("aiohttp.ClientSession.post") as mock_post, \
         patch("aiohttp.ClientSession.get") as mock_get:

        mock_post_response = AsyncMock()
        mock_post_response.status = 200
        mock_post_response.json.return_value = {"prompt_id": "test-prompt-id"}
        mock_post.return_value.__aenter__.return_value = mock_post_response

        mock_get_history_response = AsyncMock()
        mock_get_history_response.status = 200
        mock_get_history_response.json.return_value = {
            "test-prompt-id": {
                "outputs": {
                    "2": {
                        "images": [
                            {"filename": "test.png", "subfolder": "", "type": "output"}
                        ]
                    }
                }
            }
        }

        mock_get_view_response = AsyncMock()
        mock_get_view_response.status = 200
        mock_get_view_response.read.return_value = b"fake-image-bytes"

        mock_get.return_value.__aenter__.side_effect = [mock_get_history_response, mock_get_view_response]

        keyframe = await provider.generate_keyframe(invalid_request)

        assert keyframe.image_bytes == b"fake-image-bytes"

        # Verify the fallback prompt was injected
        call_args = mock_post.call_args[1]["json"]["prompt"]
        assert call_args["1"]["inputs"]["text"] == "running fast, close up"

@pytest.mark.asyncio
async def test_generate_keyframe_queue_fails(provider, valid_request):
    with patch("aiohttp.ClientSession.post") as mock_post:
        mock_post_response = AsyncMock()
        mock_post_response.status = 500
        mock_post_response.text.return_value = "Internal Server Error"
        mock_post.return_value.__aenter__.return_value = mock_post_response

        with pytest.raises(ProviderError, match="ComfyUI queue failed"):
            await provider.generate_keyframe(valid_request)

@pytest.mark.asyncio
async def test_generate_keyframe_no_image_output(provider, valid_request):
    with patch("aiohttp.ClientSession.post") as mock_post, \
         patch("aiohttp.ClientSession.get") as mock_get:

        mock_post_response = AsyncMock()
        mock_post_response.status = 200
        mock_post_response.json.return_value = {"prompt_id": "test-prompt-id"}
        mock_post.return_value.__aenter__.return_value = mock_post_response

        mock_get_history_response = AsyncMock()
        mock_get_history_response.status = 200
        mock_get_history_response.json.return_value = {
            "test-prompt-id": {
                "outputs": {}
            }
        }

        mock_get.return_value.__aenter__.return_value = mock_get_history_response

        with pytest.raises(ProviderError, match="No image output found"):
            await provider.generate_keyframe(valid_request)
