"""Durable authority for Wan job state and optimistic CAS writes."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CheckpointWriteResult:
    accepted: bool
    revision: int
    checksum: str | None = None
    conflict: str | None = None


@dataclass(frozen=True)
class HeartbeatResult:
    accepted: bool
    revision: int
    lease_expires_at: Any = None
    heartbeat_at: Any = None
    fencing_token: int = 0
    conflict: str | None = None


class WanCheckpointStorePort(ABC):
    @abstractmethod
    async def load(self, checkpoint_key: str) -> bytes:
        raise NotImplementedError

    @abstractmethod
    async def list(self, prefix: str) -> tuple[str, ...]:
        raise NotImplementedError

    @abstractmethod
    async def put_if_revision(
        self, checkpoint_key: str, expected_revision: int, envelope: dict[str, Any]
    ) -> CheckpointWriteResult:
        raise NotImplementedError

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
    async def acquire_coordinator_lock(self, owner_id: str, ttl: float) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def renew_coordinator_lock(self, owner_id: str, ttl: float) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def release_coordinator_lock(self, owner_id: str) -> None:
        raise NotImplementedError
