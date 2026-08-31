from __future__ import annotations

import pytest

from core.domain.exceptions import ProviderError
from core.domain.value_objects.image_to_video_request import ImageToVideoRequest
from infrastructure.providers.video.comfyui_image_to_video_provider import (
    ComfyUIImageToVideoProvider,
)


def _request() -> ImageToVideoRequest:
    return ImageToVideoRequest(
        shot_contract_id="shot-1",
        storyboard_id="board-1",
        storyboard_frame_id="frame-1",
        source_image_storage_key="storyboards/shot-1/frame.png",
        target_duration_seconds=4,
        motion_prompt="Akira turns toward camera",
        camera_motion="slow push-in",
        width=1280,
        height=720,
        fps=24,
        seed=1903,
    )


def test_request_is_injected_into_connected_workflow_fields():
    workflow = {
        "1": {"class_type": "LoadImage", "inputs": {"image": "old.png"}},
        "2": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "old positive"},
            "_meta": {"title": "Positive Prompt"},
        },
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "keep negative"},
            "_meta": {"title": "Negative Prompt"},
        },
        "4": {
            "class_type": "KSampler",
            "inputs": {"seed": 1, "latent_image": ["5", 0]},
        },
        "5": {"class_type": "ImageToVideo", "inputs": {"num_frames": 16}},
        "6": {"class_type": "VideoCombine", "inputs": {"frame_rate": 8}},
    }

    ComfyUIImageToVideoProvider._inject_request(
        workflow, _request(), "selma/input.png"
    )

    assert workflow["1"]["inputs"]["image"] == "selma/input.png"
    assert "Akira turns" in workflow["2"]["inputs"]["text"]
    assert workflow["3"]["inputs"]["text"] == "keep negative"
    assert workflow["4"]["inputs"]["seed"] == 1903
    assert workflow["5"]["inputs"]["num_frames"] == 96
    assert workflow["6"]["inputs"]["frame_rate"] == 24


def test_workflow_requires_source_image_node():
    with pytest.raises(ProviderError, match="LoadImage"):
        ComfyUIImageToVideoProvider._inject_request(
            {"2": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}}},
            _request(),
            "input.png",
        )


def test_video_output_is_read_from_comfyui_history():
    output = ComfyUIImageToVideoProvider._find_video_output(
        {
            "outputs": {
                "9": {
                    "gifs": [
                        {"filename": "clip.mp4", "subfolder": "selma", "type": "output"}
                    ]
                }
            }
        }
    )
    assert output["filename"] == "clip.mp4"


def test_request_rejects_machine_specific_source_path():
    with pytest.raises(ValueError, match="portable relative"):
        ImageToVideoRequest(
            shot_contract_id="shot-1",
            storyboard_id="board-1",
            storyboard_frame_id="frame-1",
            source_image_storage_key="C:/users/akira.png",
            target_duration_seconds=4,
            motion_prompt="walk",
        )
