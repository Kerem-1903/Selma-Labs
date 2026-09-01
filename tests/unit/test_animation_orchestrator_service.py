from __future__ import annotations

import hashlib

import pytest

from core.application.services.animation_orchestrator_service import (
    AnimationOrchestratorService,
)
from core.domain.entities.character_state import CharacterState
from core.domain.entities.shot_animation import ShotMotionClip, ShotPlan
from core.domain.exceptions import MotionGenerationError
from core.domain.ports.lipsync_port import LipSyncPort
from core.domain.ports.motion_generator_port import MotionGeneratorPort
from core.domain.ports.scene_compositor_port import SceneCompositorPort


class FakeMotion(MotionGeneratorPort):
    async def generate_motion_clip(self, shot_plan, progress_callback=None):
        if progress_callback:
            progress_callback(0.5)
            progress_callback(1.0)
        return ShotMotionClip(
            video_path=f"motion/{shot_plan.id}/clip.mp4",
            hash=hashlib.sha256(shot_plan.id.encode()).hexdigest(),
            seed=1903,
            cached=False,
        )


class FakeLipSync(LipSyncPort):
    def __init__(self):
        self.inputs = None

    async def generate_lipsync_clip(self, source, audio, output):
        self.inputs = (source, audio, output)
        return output


class FakeCompositor(SceneCompositorPort):
    def __init__(self):
        self.inputs = None

    async def compose_scene(self, background, character, audio, output):
        self.inputs = (background, character, audio, output)
        return output


def _plan(*, approved: bool) -> ShotPlan:
    plan = ShotPlan(
        id="pilot-shot-001",
        script_id="pilot",
        scene_plan_id="pilot-scene-001",
        prompt="akira_girl speaks",
        duration_seconds=3,
        character_state=CharacterState("akira", "akira-default", [], []),
        dialogue="Wake up.",
    )
    return plan.approve_keyframe("storyboards/pilot-shot-001/frame.png") if approved else plan


@pytest.mark.asyncio
async def test_orchestrator_runs_motion_lipsync_and_composition_in_order():
    lipsync = FakeLipSync()
    compositor = FakeCompositor()
    service = AnimationOrchestratorService(FakeMotion(), lipsync, compositor)
    progress = []

    result = await service.orchestrate_shot(
        _plan(approved=True),
        "backgrounds/hospital.png",
        "audio/pilot-shot-001.wav",
        "final/pilot-shot-001.mp4",
        progress.append,
    )

    assert result == "final/pilot-shot-001.mp4"
    assert lipsync.inputs[0] == "motion/pilot-shot-001/clip.mp4"
    assert compositor.inputs[1].startswith("lipsync/pilot-shot-001/")
    assert progress == sorted(progress)
    assert progress[-1] == 1.0


@pytest.mark.asyncio
async def test_orchestrator_rejects_unapproved_keyframe_before_calling_providers():
    service = AnimationOrchestratorService(FakeMotion(), FakeLipSync(), FakeCompositor())

    with pytest.raises(MotionGenerationError, match="approval gate"):
        await service.orchestrate_shot(
            _plan(approved=False),
            "backgrounds/hospital.png",
            "audio/dialogue.wav",
            "final/shot.mp4",
        )
