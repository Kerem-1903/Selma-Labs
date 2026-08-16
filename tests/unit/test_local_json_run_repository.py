from __future__ import annotations

import pytest

from core.domain.entities.pipeline_run import PipelineRun, PipelineRunStatus
from core.domain.exceptions import PipelineRunNotFoundError, PipelineRunStateError
from infrastructure.repositories.local_json_run_repository import LocalJsonRunRepository


@pytest.mark.asyncio
async def test_save_creates_json_and_get_rehydrates_run(tmp_path):
    repository = LocalJsonRunRepository(tmp_path / ".selma_runs")
    run = PipelineRun.create()
    run.begin_stage("AUDIO_INTELLIGENCE")
    run.mark_stage_completed("AUDIO_INTELLIGENCE", {"highlight_id": "hook-1"})

    await repository.save(run)
    restored = await repository.get_by_id(run.run_id)

    assert (tmp_path / ".selma_runs" / f"{run.run_id}.json").exists()
    assert restored.status is PipelineRunStatus.RUNNING
    assert restored.get_stage_artifact("AUDIO_INTELLIGENCE") == {"highlight_id": "hook-1"}


@pytest.mark.asyncio
async def test_missing_run_raises_typed_not_found_error(tmp_path):
    repository = LocalJsonRunRepository(tmp_path)

    with pytest.raises(PipelineRunNotFoundError):
        await repository.get_by_id("c1a6312c-0e2d-4b0a-a8d8-8f95f6d78d25")


@pytest.mark.asyncio
async def test_lock_run_serializes_another_writer(tmp_path):
    repository = LocalJsonRunRepository(tmp_path, lock_timeout_seconds=0.05)
    run = PipelineRun.create()

    async with repository.lock_run(run.run_id):
        with pytest.raises(PipelineRunStateError, match="Timed out waiting for the lock"):
            async with LocalJsonRunRepository(
                tmp_path,
                lock_timeout_seconds=0.01,
            ).lock_run(run.run_id):
                pass


@pytest.mark.asyncio
async def test_released_lock_is_immediately_available_to_next_stage(tmp_path):
    run = PipelineRun.create()
    first = LocalJsonRunRepository(tmp_path, lock_timeout_seconds=0.2)
    second = LocalJsonRunRepository(tmp_path, lock_timeout_seconds=0.2)

    async with first.lock_run(run.run_id):
        pass

    async with second.lock_run(run.run_id):
        pass
