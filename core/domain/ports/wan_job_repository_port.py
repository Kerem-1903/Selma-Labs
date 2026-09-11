from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable

from core.domain.entities.wan_render_job import WanRenderJob
from core.domain.ports.wan_checkpoint_store_port import HeartbeatResult


class WanJobRepositoryPort(ABC):
    """Persistent queue boundary with atomic claim and fenced commit operations."""

    @abstractmethod
    async def add(self, job: WanRenderJob) -> None:
        raise NotImplementedError

    @abstractmethod
    async def save(self, job: WanRenderJob, *, expected_revision: int | None = None) -> None:
        raise NotImplementedError

    @abstractmethod
    async def get(self, job_id: str) -> WanRenderJob:
        raise NotImplementedError

    @abstractmethod
    async def list(self) -> tuple[WanRenderJob, ...]:
        raise NotImplementedError

    @abstractmethod
    async def claim_next(self, slot_id: str, lease_seconds: float) -> WanRenderJob | None:
        raise NotImplementedError

    @abstractmethod
    async def heartbeat(
        self,
        checkpoint_key: str,
        lease_id: str,
        attempt_id: str,
        fencing_token: int,
        expected_revision: int,
        requested_lease_extension: float,
    ) -> HeartbeatResult:
        raise NotImplementedError

    @abstractmethod
    async def commit_fenced(
        self,
        job_id: str,
        lease_id: str,
        attempt_id: str,
        fencing_token: int,
        expected_revision: int,
        operation: Callable[[WanRenderJob], Awaitable[WanRenderJob]],
    ) -> WanRenderJob:
        """Run artifact publication and checkpoint completion in one fence section."""
        raise NotImplementedError
