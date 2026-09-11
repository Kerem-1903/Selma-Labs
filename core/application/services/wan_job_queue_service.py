from __future__ import annotations

from dataclasses import dataclass

from core.domain.entities.wan_render_job import WanRenderJob, WanRenderJobStatus
from core.domain.ports.wan_job_repository_port import WanJobRepositoryPort


@dataclass(frozen=True)
class WanQueueSnapshot:
    counts: dict[WanRenderJobStatus, int]

    @property
    def claimable(self) -> int:
        return self.counts.get(WanRenderJobStatus.PENDING, 0) + self.counts.get(
            WanRenderJobStatus.RETRY_REQUIRED, 0
        )

    @property
    def active(self) -> int:
        return self.counts.get(WanRenderJobStatus.RUNNING, 0) + self.counts.get(
            WanRenderJobStatus.VERIFYING, 0
        )

    @property
    def drained(self) -> bool:
        return self.claimable == 0 and self.active == 0


class WanJobQueueService:
    def __init__(self, repository: WanJobRepositoryPort, *, lease_seconds: float = 3600.0) -> None:
        if lease_seconds <= 0:
            raise ValueError("Wan queue lease_seconds must be positive.")
        self._repository = repository
        self._lease_seconds = lease_seconds

    @property
    def lease_seconds(self) -> float:
        return self._lease_seconds

    @property
    def repository(self) -> WanJobRepositoryPort:
        return self._repository

    async def enqueue(self, jobs: tuple[WanRenderJob, ...] | list[WanRenderJob]) -> int:
        """Add only new jobs; durable jobs, especially COMPLETED ones, are preserved."""
        added = 0
        for job in jobs:
            try:
                await self._repository.get(job.job_id)
            except ValueError:
                await self._repository.add(job)
                added += 1
        return added

    async def claim(self, slot_id: str) -> WanRenderJob | None:
        # Very short leases are useful for direct recovery tests but leave no
        # time for a real provider round-trip plus durable checkpoint fsync.
        return await self._repository.claim_next(slot_id, max(self._lease_seconds, 1.0))

    async def get(self, job_id: str) -> WanRenderJob:
        return await self._repository.get(job_id)

    async def acquire_coordinator_lock(self, owner_id: str, ttl: float) -> bool:
        method = getattr(self._repository, "acquire_coordinator_lock", None)
        if method is None:
            raise ValueError("Wan repository does not provide coordinator ownership locking.")
        return await method(owner_id, ttl)

    async def renew_coordinator_lock(self, owner_id: str, ttl: float) -> bool:
        method = getattr(self._repository, "renew_coordinator_lock", None)
        if method is None:
            return False
        return await method(owner_id, ttl)

    async def release_coordinator_lock(self, owner_id: str) -> None:
        method = getattr(self._repository, "release_coordinator_lock", None)
        if method is not None:
            await method(owner_id)

    async def save(self, job: WanRenderJob, *, expected_revision: int | None = None) -> None:
        await self._repository.save(job, expected_revision=expected_revision)

    async def heartbeat(self, job: WanRenderJob, requested_lease_extension: float, *, expected_revision: int | None = None):
        if not job.lease_id or not job.attempt_id:
            raise ValueError("Wan heartbeat requires an active lease and attempt.")
        return await self._repository.heartbeat(
            f"{job.job_id}.json",
            job.lease_id,
            job.attempt_id,
            job.fencing_token,
            job.revision if expected_revision is None else expected_revision,
            max(requested_lease_extension, 1.0),
        )

    async def snapshot(self) -> WanQueueSnapshot:
        counts = {status: 0 for status in WanRenderJobStatus}
        for job in await self._repository.list():
            counts[job.status] += 1
        return WanQueueSnapshot(counts)

    async def jobs(self) -> tuple[WanRenderJob, ...]:
        return await self._repository.list()

