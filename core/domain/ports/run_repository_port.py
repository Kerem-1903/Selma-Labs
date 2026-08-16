"""Persistence boundary for durable pipeline-run aggregates."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncContextManager

from core.domain.entities.pipeline_run import PipelineRun


class RunRepositoryPort(ABC):
    """Stores and retrieves the aggregate that makes stage recovery possible."""

    @abstractmethod
    async def save(self, run: PipelineRun) -> None:
        """Persist the current aggregate state atomically when possible."""
        raise NotImplementedError

    @abstractmethod
    async def get_by_id(self, run_id: str) -> PipelineRun:
        """Load an existing run or raise ``PipelineRunNotFoundError``."""
        raise NotImplementedError

    @abstractmethod
    def lock_run(self, run_id: str) -> AsyncContextManager[None]:
        """Acquire an exclusive lease for decisions and writes on one run."""
        raise NotImplementedError
