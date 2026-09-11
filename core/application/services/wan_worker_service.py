"""Dynamic multi-slot unattended Wan worker coordinator."""

from __future__ import annotations

import asyncio
from pathlib import Path

from core.application.services.wan_attempt_commit_service import WanAttemptCommitService
from core.application.services.wan_budget_guard import WanBudgetGuard
from core.application.services.wan_job_queue_service import WanJobQueueService
from core.application.services.wan_output_verification_service import (
    WanOutputVerificationService,
)
from core.domain.entities.wan_render_job import (
    WanRenderJob,
    WanRenderJobStatus,
    WanTechnicalError,
)
from core.domain.ports.storage_port import StoragePort
from core.domain.ports.wan_compute_lifecycle_port import WanComputeLifecyclePort
from core.domain.ports.wan_worker_provider_port import (
    WanWorkerProviderPort,
    WanWorkerResult,
)


class WanWorkerService:
    def __init__(
        self,
        queue: WanJobQueueService,
        provider: WanWorkerProviderPort,
        verifier: WanOutputVerificationService,
        output_storage: StoragePort,
        lifecycle: WanComputeLifecyclePort,
        *,
        work_directory: str | Path,
        hard_runtime_seconds: float = 3600.0,
        budget: WanBudgetGuard | None = None,
        attempt_commits: WanAttemptCommitService,
    ) -> None:
        if hard_runtime_seconds <= 0:
            raise ValueError("Wan hard runtime must be positive.")
        if attempt_commits is None:
            raise ValueError("Wan worker requires the fenced attempt commit service.")
        self._queue = queue
        self._provider = provider
        self._verifier = verifier
        self._storage = output_storage
        self._lifecycle = lifecycle
        self._work_directory = Path(work_directory)
        self._hard_runtime_seconds = hard_runtime_seconds
        self._budget = budget or WanBudgetGuard()
        self._attempt_commits = attempt_commits
        self._coordinator_owner = f"wan-worker-{id(self)}"

    async def run(self, *, slot_count: int = 2) -> tuple[WanRenderJob, ...]:
        if slot_count < 1:
            raise ValueError("Wan worker requires at least one GPU slot.")
        self._work_directory.mkdir(parents=True, exist_ok=True)
        if not await self._queue.acquire_coordinator_lock(self._coordinator_owner, max(self._queue.lease_seconds, 30.0)):
            raise RuntimeError("Wan coordinator ownership could not be acquired.")
        try:
            renew_task = asyncio.create_task(self._renew_coordinator_lock())
            async def run_slots() -> None:
                await asyncio.gather(
                    *(self._run_slot(f"GPU-{index}") for index in range(slot_count))
                )

            slot_group = asyncio.create_task(run_slots())
            try:
                done, _ = await asyncio.wait(
                    {slot_group, renew_task}, return_when=asyncio.FIRST_COMPLETED
                )
                if renew_task in done:
                    renew_task.result()
                    raise RuntimeError("Wan coordinator ownership was lost.")
                slot_group.result()
            finally:
                for task in (slot_group, renew_task):
                    if not task.done():
                        task.cancel()
                await asyncio.gather(slot_group, renew_task, return_exceptions=True)
        finally:
            await self._queue.release_coordinator_lock(self._coordinator_owner)
        snapshot = await self._queue.snapshot()
        if snapshot.drained and self._lifecycle.provider_auto_stop_enabled:
            await self._lifecycle.stop_own_instance()
        return await self._queue.jobs()

    async def _renew_coordinator_lock(self) -> None:
        interval = max(0.05, min(self._queue.lease_seconds, 5.0))
        while True:
            await asyncio.sleep(interval)
            if not await self._queue.renew_coordinator_lock(
                self._coordinator_owner, max(self._queue.lease_seconds, 30.0)
            ):
                raise RuntimeError("Wan coordinator ownership was lost.")

    async def _run_slot(self, slot_id: str) -> None:
        while await self._budget.reserve():
            job = await self._queue.claim(slot_id)
            if job is None:
                return
            await self._execute(job)

    async def _execute(self, job: WanRenderJob) -> None:
        try:
            result, active_job = await self._render_with_heartbeat(job)
            if result is None or active_job is None:
                return
        except (TimeoutError, asyncio.TimeoutError):
            await self._technical_failure(await self._queue.get(job.job_id), WanTechnicalError.TIMEOUT)
            return
        except Exception:  # noqa: BLE001 - provider-specific failures become typed job state
            current = await self._queue.get(job.job_id)
            if current.status in {WanRenderJobStatus.RUNNING, WanRenderJobStatus.VERIFYING}:
                await self._technical_failure(current, WanTechnicalError.BROKEN_MP4)
            return

        if result.technical_error is not None:
            await self._technical_failure(active_job, result.technical_error)
            return
        if result.quality_error is not None:
            reviewed = active_job.require_review(result.quality_error)
            await self._queue.save(reviewed, expected_revision=active_job.revision)
            return
        if result.local_output_path is None:
            await self._technical_failure(active_job, WanTechnicalError.BROKEN_MP4)
            return

        verifying = active_job.verifying()
        await self._queue.save(verifying, expected_revision=active_job.revision)
        refreshed_verifying = await self._refresh_lease(verifying)
        if refreshed_verifying is None:
            return
        verifying = refreshed_verifying
        verification = await self._verifier.verify(
            verifying, result.local_output_path, inspection=result.inspection
        )
        if not verification.accepted:
            await self._technical_failure(
                verifying, verification.error or WanTechnicalError.BROKEN_MP4
            )
            return

        try:
            manifest = await self._attempt_commits.upload_attempt(
                verifying, result.local_output_path
            )
            await self._attempt_commits.conditional_commit(
                verifying, manifest, verifying.revision
            )
        except Exception:  # noqa: BLE001 - persistence adapters have different error types
            current = await self._queue.get(verifying.job_id)
            if current.status in {WanRenderJobStatus.RUNNING, WanRenderJobStatus.VERIFYING}:
                await self._technical_failure(current, WanTechnicalError.BROKEN_MP4)

    async def _render_with_heartbeat(
        self, job: WanRenderJob
    ) -> tuple[WanWorkerResult | None, WanRenderJob | None]:
        render_task = asyncio.create_task(
            self._provider.render(job, self._work_directory / job.job_id)
        )
        heartbeat_task = asyncio.create_task(self._heartbeat_until_done(job, render_task))
        try:
            done, _ = await asyncio.wait(
                {render_task, heartbeat_task},
                timeout=self._hard_runtime_seconds,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if not done:
                raise TimeoutError("Wan render exceeded its hard runtime.")
            if heartbeat_task in done:
                active_job = heartbeat_task.result()
                if active_job is None:
                    render_task.cancel()
                    await asyncio.gather(render_task, return_exceptions=True)
                    return None, None
                return await render_task, active_job
            result = render_task.result()
            if heartbeat_task.done():
                active_job = heartbeat_task.result()
            else:
                heartbeat_task.cancel()
                await asyncio.gather(heartbeat_task, return_exceptions=True)
                active_job = await self._refresh_lease(await self._queue.get(job.job_id))
            if active_job is None:
                return None, None
            return result, active_job
        finally:
            if not render_task.done():
                render_task.cancel()
            if not heartbeat_task.done():
                heartbeat_task.cancel()
            await asyncio.gather(render_task, heartbeat_task, return_exceptions=True)

    async def _heartbeat_until_done(
        self, job: WanRenderJob, render_task: asyncio.Task[WanWorkerResult]
    ) -> WanRenderJob | None:
        current = job
        interval = max(0.005, min(self._queue.lease_seconds / 3, 0.25))
        while not render_task.done():
            await asyncio.sleep(interval)
            if render_task.done():
                break
            current = await self._refresh_lease(current)
            if current is None:
                return None
        return current

    async def _refresh_lease(self, job: WanRenderJob) -> WanRenderJob | None:
        try:
            heartbeat = await self._queue.heartbeat(job, self._queue.lease_seconds)
        except (ValueError, OSError):
            return None
        if not heartbeat.accepted or heartbeat.lease_expires_at is None:
            return None
        refreshed = await self._queue.get(job.job_id)
        if refreshed.revision != heartbeat.revision:
            return None
        return refreshed

    async def _technical_failure(self, job: WanRenderJob, error: WanTechnicalError) -> None:
        if job.attempt_count < job.max_attempts:
            await self._queue.save(job.retry(error), expected_revision=job.revision)
            return
        if job.allow_step_fallback:
            await self._queue.save(job.use_fallback(), expected_revision=job.revision)
            return
        await self._queue.save(job.fail(error), expected_revision=job.revision)
