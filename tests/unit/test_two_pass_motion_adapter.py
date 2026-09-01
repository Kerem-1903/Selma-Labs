from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.domain.entities.candidate.keyframe_candidate import CandidateStatus
from core.domain.entities.character_state import CharacterState
from core.domain.entities.shot_animation import ShotPlan
from core.domain.exceptions import MotionGenerationError
from core.domain.ports.storage_port import StoragePort
from core.domain.value_objects.render_config import RenderConfig
from core.domain.value_objects.storage_reference import StorageReference
from infrastructure.providers.motion.comfyui_motion_adapter import ComfyUIMotionAdapter


class MemoryStorage(StoragePort):
    def __init__(self):
        self.data = {}

    async def save(self, key, data, content_type):
        self.data[key] = bytes(data)
        return StorageReference(key, key, len(data))

    async def load(self, key):
        return self.data[key]

    async def exists(self, key):
        return key in self.data

    def upload_file(self, file_stream, destination_path, content_type):
        raise NotImplementedError

    def download_file(self, source_path, local_destination):
        raise NotImplementedError

    def delete_file(self, file_path):
        raise NotImplementedError


class FakeClient:
    def __init__(self):
        self.prompt = None
        self.queue_calls = 0

    async def upload_image(self, image_bytes, storage_key):
        assert image_bytes == b"png"
        return "selma/approved.png"

    async def queue_prompt_and_wait(self, prompt, client_id=None, progress_callback=None):
        self.prompt = prompt
        self.queue_calls += 1
        if progress_callback:
            progress_callback(0.5)
            progress_callback(1.0)
        return {
            "prompt_id": "prompt-1",
            "outputs": {
                "6": {
                    "gifs": [
                        {"filename": "akira.mp4", "subfolder": "selma", "type": "output"}
                    ]
                }
            },
        }

    async def download_output(self, file_info):
        return b"\x00\x00\x00\x18ftypisom0000"


class CommittedCandidate:
    status = CandidateStatus.COMMITTED

    def __init__(self, storage_key):
        self.storage_key = storage_key


class FakeCandidateEvaluation:
    async def get_approved_candidate_for_shot(self, shot_id):
        assert shot_id == "pilot-shot-001"
        return CommittedCandidate("storyboards/pilot-shot-001/frame.png")


def _workflow(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "1": {"class_type": "LoadImage", "inputs": {"image": "old.png"}},
                "2": {
                    "class_type": "CLIPTextEncode",
                    "inputs": {"text": "positive"},
                    "_meta": {"title": "Positive Prompt"},
                },
                "3": {
                    "class_type": "CLIPTextEncode",
                    "inputs": {"text": "negative"},
                    "_meta": {"title": "Negative Prompt"},
                },
                "4": {
                    "class_type": "KSampler",
                    "inputs": {
                        "seed": 1,
                        "steps": 1,
                        "cfg": 1,
                        "sampler_name": "old",
                        "denoise": 1,
                        "latent_image": ["1", 0],
                        "positive": ["2", 0],
                        "negative": ["3", 0],
                    },
                },
                "5": {"class_type": "VAEDecode", "inputs": {"samples": ["4", 0]}},
                "6": {"class_type": "VHS_VideoCombine", "inputs": {"images": ["5", 0], "frame_rate": 8}},
            }
        ),
        encoding="utf-8",
    )


def _plan(*, approved=True):
    plan = ShotPlan(
        id="pilot-shot-001",
        script_id="pilot",
        scene_plan_id="pilot-scene-001",
        prompt="akira_girl turns",
        negative_prompt="identity drift",
        duration_seconds=1,
        character_state=CharacterState("akira", "akira-default", [], []),
    )
    return plan.approve_keyframe("storyboards/pilot-shot-001/frame.png") if approved else plan


@pytest.mark.asyncio
async def test_adapter_builds_chained_two_pass_graph_and_caches_result(tmp_path):
    workflow_path = tmp_path / "workflow.json"
    _workflow(workflow_path)
    storage = MemoryStorage()
    await storage.save("storyboards/pilot-shot-001/frame.png", b"png", "image/png")
    client = FakeClient()
    adapter = ComfyUIMotionAdapter(
        "http://127.0.0.1:8188",
        workflow_path=workflow_path,
        storage=storage,
        client=client,
        render_config=RenderConfig(512, 512, 8, 1903, "euler", 0.12, 0.06),
        candidate_evaluation_service=FakeCandidateEvaluation(),
    )

    clip = await adapter.generate_motion_clip(_plan())
    cached = await adapter.generate_motion_clip(_plan())

    assert clip.cached is False
    assert cached.cached is True
    assert clip.video_path == cached.video_path
    assert client.queue_calls == 1
    assert client.prompt["4"]["inputs"]["denoise"] == 0.12
    assert client.prompt["selma_motion_pass_2"]["inputs"]["denoise"] == 0.06
    assert client.prompt["selma_motion_pass_2"]["inputs"]["latent_image"] == ["4", 0]
    assert client.prompt["5"]["inputs"]["samples"] == ["selma_motion_pass_2", 0]


@pytest.mark.asyncio
async def test_adapter_refuses_unapproved_plan_before_comfyui(tmp_path):
    workflow_path = tmp_path / "workflow.json"
    _workflow(workflow_path)
    adapter = ComfyUIMotionAdapter(
        "127.0.0.1:8188",
        workflow_path=workflow_path,
        storage=MemoryStorage(),
        client=FakeClient(),
        candidate_evaluation_service=FakeCandidateEvaluation(),
    )

    with pytest.raises(MotionGenerationError, match="human-review"):
        await adapter.generate_motion_clip(_plan(approved=False))


@pytest.mark.asyncio
async def test_adapter_fails_closed_without_persisted_approval_verifier(tmp_path):
    workflow_path = tmp_path / "workflow.json"
    _workflow(workflow_path)
    storage = MemoryStorage()
    await storage.save("storyboards/pilot-shot-001/frame.png", b"png", "image/png")
    adapter = ComfyUIMotionAdapter(
        "127.0.0.1:8188",
        workflow_path=workflow_path,
        storage=storage,
        client=FakeClient(),
    )

    with pytest.raises(MotionGenerationError, match="committed-candidate verifier"):
        await adapter.generate_motion_clip(_plan())
