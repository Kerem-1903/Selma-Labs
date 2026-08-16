from __future__ import annotations

import pytest
from contextlib import asynccontextmanager

from core.application.orchestration.run_executor import RunExecutor
from core.domain.entities.pipeline_run import PipelineRun, PipelineRunStatus
from core.domain.exceptions import PipelineRunNotFoundError


class InMemoryRunRepository:
    """Repository fake proving executor behavior without disk or database I/O."""

    def __init__(self, run: PipelineRun) -> None:
        self.runs = {run.run_id: run}
        self.saved_states: list[PipelineRunStatus] = []

    async def save(self, run: PipelineRun) -> None:
        self.runs[run.run_id] = run
        self.saved_states.append(run.status)

    async def get_by_id(self, run_id: str) -> PipelineRun:
        try:
            return self.runs[run_id]
        except KeyError as error:
            raise PipelineRunNotFoundError(run_id) from error

    @asynccontextmanager
    async def lock_run(self, run_id: str):
        del run_id
        yield


@pytest.mark.asyncio
async def test_executor_checkpoints_success_and_skips_completed_stage():
    run = PipelineRun.create()
    repository = InMemoryRunRepository(run)
    executor = RunExecutor(repository)
    calls = 0

    async def operation() -> dict[str, str]:
        nonlocal calls
        calls += 1
        return {"highlight_id": "hook-1"}

    first = await executor.execute_stage(run.run_id, "AUDIO_ANALYSIS", operation)
    second = await executor.execute_stage(run.run_id, "AUDIO_ANALYSIS", operation)

    assert first == second == {"highlight_id": "hook-1"}
    assert calls == 1
    assert repository.saved_states == [PipelineRunStatus.RUNNING, PipelineRunStatus.RUNNING]


@pytest.mark.asyncio
async def test_executor_persists_failure_then_allows_retry():
    run = PipelineRun.create(max_retries=1)
    repository = InMemoryRunRepository(run)
    executor = RunExecutor(repository)

    async def failing_operation() -> dict[str, str]:
        raise RuntimeError("temporary vision outage")

    with pytest.raises(RuntimeError, match="temporary vision outage"):
        await executor.execute_stage(run.run_id, "VISION_SEARCH", failing_operation)

    assert run.status is PipelineRunStatus.FAILED
    assert "temporary vision outage" in (run.failure_reason or "")

    result = await executor.execute_stage(
        run.run_id,
        "VISION_SEARCH",
        lambda: {"asset_id": "video-1"},
    )

    assert result == {"asset_id": "video-1"}
    assert run.retry_count == 1
    assert run.status is PipelineRunStatus.RUNNING


@pytest.mark.asyncio
async def test_executor_marks_finished_workflow_completed():
    run = PipelineRun.create()
    repository = InMemoryRunRepository(run)
    executor = RunExecutor(repository)

    await executor.execute_stage(run.run_id, "RENDER", lambda: {"output": "short.mp4"})
    await executor.complete_run(run.run_id)

    assert run.status is PipelineRunStatus.COMPLETED
