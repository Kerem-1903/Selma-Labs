from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from core.application.services.approved_keyframe_motion_service import (
    ApprovedKeyframeMotionService,
)
from core.domain.entities.shot_storyboard import ShotStoryboard
from core.domain.exceptions import (
    ProviderConnectionError,
    ProviderQuotaExceededError,
    ProviderTimeoutError,
    ShotProductionError,
)
from core.domain.ports.shot_production_attempt_repository_port import (
    ShotProductionAttemptRepositoryPort,
)
from core.domain.value_objects.render_profile import RenderProfile
from core.domain.value_objects.shot_production_attempt import (
    ProductionAttemptStatus,
    ShotProductionAttempt,
)
from core.domain.value_objects.shot_production_result import ShotProductionResult


class ShotProductionService:
    """Produce a gated motion clip with bounded transient retries and cost telemetry."""

    _RETRYABLE = (
        ProviderConnectionError,
        ProviderQuotaExceededError,
        ProviderTimeoutError,
    )

    def __init__(
        self,
        *,
        motion_service: ApprovedKeyframeMotionService,
        attempts: ShotProductionAttemptRepositoryPort,
        max_retries: int = 2,
        initial_backoff_seconds: float = 1.0,
        hourly_gpu_cost_usd: float = 0.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if max_retries < 0 or initial_backoff_seconds < 0 or hourly_gpu_cost_usd < 0:
            raise ValueError("Production retry and cost settings cannot be negative.")
        self._motion_service = motion_service
        self._attempts = attempts
        self._max_retries = max_retries
        self._initial_backoff_seconds = initial_backoff_seconds
        self._hourly_gpu_cost_usd = hourly_gpu_cost_usd
        self._sleep = sleep

    async def produce_shot(
        self,
        *,
        storyboard: ShotStoryboard,
        target_duration_seconds: float,
        motion_prompt: str,
        camera_motion: str = "static",
        profile: RenderProfile = RenderProfile.BALANCED,
        seed: int | None = None,
    ) -> ShotProductionResult:
        settings = profile.settings
        recorded: list[ShotProductionAttempt] = []
        last_error: Exception | None = None
        existing = await self._attempts.list_for_shot(storyboard.shot_contract_id)
        attempt_offset = max((item.attempt_number for item in existing), default=0)
        for local_attempt in range(1, self._max_retries + 2):
            attempt_number = attempt_offset + local_attempt
            started_at = datetime.now(timezone.utc)
            started_clock = time.perf_counter()
            try:
                clip = await self._motion_service.generate(
                    storyboard=storyboard,
                    target_duration_seconds=target_duration_seconds,
                    motion_prompt=motion_prompt,
                    camera_motion=camera_motion,
                    width=settings.width,
                    height=settings.height,
                    fps=settings.fps,
                    seed=seed,
                    sampling_steps=settings.sampling_steps,
                    guidance_scale=settings.guidance_scale,
                    render_profile=profile,
                )
            except self._RETRYABLE as error:
                last_error = error
                attempt = self._make_attempt(
                    storyboard.shot_contract_id,
                    attempt_number,
                    profile,
                    seed,
                    started_at,
                    started_clock,
                    ProductionAttemptStatus.FAILED_RETRYABLE,
                    error,
                )
                await self._attempts.save(attempt)
                recorded.append(attempt)
                if local_attempt <= self._max_retries:
                    await self._sleep(
                        self._initial_backoff_seconds * (2 ** (local_attempt - 1))
                    )
                    continue
                break
            except Exception as error:
                attempt = self._make_attempt(
                    storyboard.shot_contract_id,
                    attempt_number,
                    profile,
                    seed,
                    started_at,
                    started_clock,
                    ProductionAttemptStatus.FAILED_PERMANENT,
                    error,
                )
                await self._attempts.save(attempt)
                raise
            else:
                attempt = self._make_attempt(
                    storyboard.shot_contract_id,
                    attempt_number,
                    profile,
                    seed,
                    started_at,
                    started_clock,
                    ProductionAttemptStatus.SUCCEEDED,
                    None,
                )
                await self._attempts.save(attempt)
                recorded.append(attempt)
                return ShotProductionResult(clip=clip, attempts=tuple(recorded))

        raise ShotProductionError(
            f"Shot '{storyboard.shot_contract_id}' exhausted "
            f"{self._max_retries + 1} production attempts."
        ) from last_error

    def _make_attempt(
        self,
        shot_contract_id: str,
        attempt_number: int,
        profile: RenderProfile,
        seed: int | None,
        started_at: datetime,
        started_clock: float,
        status: ProductionAttemptStatus,
        error: Exception | None,
    ) -> ShotProductionAttempt:
        finished_at = datetime.now(timezone.utc)
        elapsed = max(0.0, time.perf_counter() - started_clock)
        return ShotProductionAttempt(
            shot_contract_id=shot_contract_id,
            attempt_number=attempt_number,
            profile=profile,
            provider=self._motion_service.provider_name,
            seed=seed,
            started_at=started_at,
            finished_at=finished_at,
            elapsed_seconds=round(elapsed, 6),
            estimated_cost_usd=round(
                elapsed / 3600.0 * self._hourly_gpu_cost_usd, 6
            ),
            status=status,
            error_type=None if error is None else type(error).__name__,
            error_message=None if error is None else str(error),
        )
