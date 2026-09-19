"""Saga-style, checkpointed execution of independently retryable stages."""
from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from typing import Any

from core.domain.entities.pipeline_run import PipelineRunStatus
from core.domain.exceptions import PipelineRunStateError
from core.domain.ports.run_repository_port import RunRepositoryPort

StageArtifact = dict[str, Any]
StageOperation = Callable[[], Awaitable[StageArtifact] | StageArtifact]


class RunExecutor:
    """Coordinates durable stages using a repository-backed Saga checkpoint.

    The executor gives each successful stage *logical* idempotency: once its
    artifact is persisted, later executions return that artifact without
    invoking the operation. Operations that call non-idempotent external APIs
    must still use ``run_id``/stage as their provider idempotency key, because
    a process can fail after the external side effect but before ``save``.
    """

    def __init__(self, repository: RunRepositoryPort) -> None:
        """Inject the persistence boundary; no storage technology leaks here."""
        self._repository = repository

    async def execute_stage(
        self,
        run_id: str,
        stage_name: str,
        operation: StageOperation,
    ) -> StageArtifact:
        """Execute a stage once, checkpoint its artifact, or return its cache.

        The pre-operation save records ``RUNNING`` before an external call.
        The post-operation save records the artifact only after success. On
        failure, the aggregate is saved as ``FAILED`` and the original error
        remains visible to the caller's retry scheduler.
        """
        async with self._repository.lock_run(run_id):
            run = await self._repository.get_by_id(run_id)
            if run.has_completed_stage(stage_name):
                return run.get_stage_artifact(stage_name)
            if run.status is PipelineRunStatus.COMPLETED:
                raise PipelineRunStateError(
                    f"Completed run has no artifact for requested stage '{stage_name}'."
                )

            run.begin_stage(stage_name)
            await self._repository.save(run)
            try:
                artifact = operation()
                if inspect.isawaitable(artifact):
                    artifact = await artifact
                if not isinstance(artifact, dict):
                    raise TypeError("A pipeline stage operation must return a dictionary.")

                run.mark_stage_completed(stage_name, artifact)
                await self._repository.save(run)
                return run.get_stage_artifact(stage_name)
            except asyncio.CancelledError:
                run.mark_failed(f"Stage '{stage_name}' was cancelled.")
                await self._repository.save(run)
                raise
            except Exception as error:
                run.mark_failed(f"Stage '{stage_name}' failed: {error}")
                await self._repository.save(run)
                raise

    async def complete_run(self, run_id: str) -> None:
        """Persist terminal success after the orchestrator's final stage.

        Completion remains separate from ``execute_stage`` because the
        executor cannot know which stage is final for every workflow that
        shares it.
        """
        async with self._repository.lock_run(run_id):
            run = await self._repository.get_by_id(run_id)
            if run.status is PipelineRunStatus.COMPLETED:
                return
            run.mark_completed()
            await self._repository.save(run)
