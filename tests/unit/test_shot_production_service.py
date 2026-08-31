from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from core.application.services.shot_production_service import ShotProductionService
from core.domain.entities.shot_motion_clip import ShotMotionClip
from core.domain.entities.shot_storyboard import ShotStoryboard
from core.domain.exceptions import (
    MotionGenerationError,
    ProviderTimeoutError,
    ShotProductionError,
)
from core.domain.value_objects.render_profile import RenderProfile
from core.domain.value_objects.shot_production_attempt import ProductionAttemptStatus


def _clip(profile: str = "DRAFT") -> ShotMotionClip:
    return ShotMotionClip(
        id="clip-1",
        shot_contract_id="shot-1",
        storyboard_id="board-1",
        storyboard_frame_id="frame-1",
        candidate_id="candidate-1",
        source_image_storage_key="storyboards/shot-1/frame.png",
        storage_key="motion/shot-1/clip.mp4",
        content_type="video/mp4",
        provider="fake:i2v",
        provider_asset_id="provider-clip",
        width=512,
        height=288,
        duration_seconds=1,
        fps=8,
        created_at=datetime.now(timezone.utc),
        render_profile=profile,
    )


class MemoryAttempts:
    def __init__(self):
        self.items = []

    async def save(self, attempt):
        self.items.append(attempt)

    async def list_for_shot(self, shot_contract_id):
        return [item for item in self.items if item.shot_contract_id == shot_contract_id]


class FakeMotionService:
    provider_name = "fake:i2v"

    def __init__(self, effects):
        self.effects = list(effects)
        self.calls = []

    async def generate(self, **kwargs):
        self.calls.append(kwargs)
        effect = self.effects.pop(0)
        if isinstance(effect, Exception):
            raise effect
        return effect


@pytest.mark.asyncio
async def test_profile_settings_reach_motion_service_and_attempt_is_recorded():
    motion = FakeMotionService([_clip()])
    attempts = MemoryAttempts()
    service = ShotProductionService(
        motion_service=motion,
        attempts=attempts,
        hourly_gpu_cost_usd=0.69,
    )

    result = await service.produce_shot(
        storyboard=ShotStoryboard.create("shot-1"),
        target_duration_seconds=1,
        motion_prompt="Akira looks up",
        profile=RenderProfile.DRAFT,
        seed=1903,
    )

    call = motion.calls[0]
    assert call["width"] == RenderProfile.DRAFT.settings.width
    assert call["sampling_steps"] == RenderProfile.DRAFT.settings.sampling_steps
    assert result.clip.id == "clip-1"
    assert result.attempts[0].status == ProductionAttemptStatus.SUCCEEDED
    assert attempts.items == list(result.attempts)


@pytest.mark.asyncio
async def test_only_transient_provider_errors_retry_with_backoff():
    motion = FakeMotionService([ProviderTimeoutError("slow"), _clip()])
    attempts = MemoryAttempts()
    sleep = AsyncMock()
    service = ShotProductionService(
        motion_service=motion,
        attempts=attempts,
        max_retries=2,
        initial_backoff_seconds=0.5,
        sleep=sleep,
    )

    result = await service.produce_shot(
        storyboard=ShotStoryboard.create("shot-1"),
        target_duration_seconds=1,
        motion_prompt="move",
    )

    assert len(result.attempts) == 2
    assert result.attempts[0].status == ProductionAttemptStatus.FAILED_RETRYABLE
    sleep.assert_awaited_once_with(0.5)


@pytest.mark.asyncio
async def test_permanent_domain_error_is_not_retried():
    motion = FakeMotionService([MotionGenerationError("bad input")])
    attempts = MemoryAttempts()
    service = ShotProductionService(
        motion_service=motion,
        attempts=attempts,
        max_retries=3,
        initial_backoff_seconds=0,
    )

    with pytest.raises(MotionGenerationError, match="bad input"):
        await service.produce_shot(
            storyboard=ShotStoryboard.create("shot-1"),
            target_duration_seconds=1,
            motion_prompt="move",
        )
    assert len(motion.calls) == 1
    assert attempts.items[0].status == ProductionAttemptStatus.FAILED_PERMANENT


@pytest.mark.asyncio
async def test_retry_exhaustion_preserves_exception_chain():
    motion = FakeMotionService(
        [ProviderTimeoutError("one"), ProviderTimeoutError("two")]
    )
    service = ShotProductionService(
        motion_service=motion,
        attempts=MemoryAttempts(),
        max_retries=1,
        initial_backoff_seconds=0,
    )

    with pytest.raises(ShotProductionError) as caught:
        await service.produce_shot(
            storyboard=ShotStoryboard.create("shot-1"),
            target_duration_seconds=1,
            motion_prompt="move",
        )
    assert isinstance(caught.value.__cause__, ProviderTimeoutError)
