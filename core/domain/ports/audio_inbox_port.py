"""Port for a durable, licensed local audio work queue."""
from __future__ import annotations

from abc import ABC, abstractmethod

from core.domain.value_objects.audio_inbox_job import AudioInboxJob


class AudioInboxPort(ABC):
    """Claims audio work and records its terminal outcome."""

    @abstractmethod
    async def claim_next(self) -> AudioInboxJob | None:
        """Claim the next recoverable local audio item, if one exists."""
        raise NotImplementedError

    @abstractmethod
    async def mark_completed(self, job: AudioInboxJob) -> None:
        """Record a successful factory run and archive its source."""
        raise NotImplementedError

    @abstractmethod
    async def renew_lease(self, job: AudioInboxJob) -> None:
        """Extend ownership while a long-running factory job is active."""
        raise NotImplementedError

    @abstractmethod
    async def mark_failed(self, job: AudioInboxJob, reason: str) -> None:
        """Record a retryable failure or move an exhausted source aside."""
        raise NotImplementedError
