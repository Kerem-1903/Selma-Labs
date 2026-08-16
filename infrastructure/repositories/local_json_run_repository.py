"""Local JSON implementation of the durable pipeline-run repository port."""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from filelock import FileLock, Timeout

from core.domain.entities.pipeline_run import PipelineRun
from core.domain.exceptions import PipelineRunNotFoundError, PipelineRunStateError
from core.domain.ports.run_repository_port import RunRepositoryPort


class LocalJsonRunRepository(RunRepositoryPort):
    """Persist ``PipelineRun`` aggregates as atomically replaced JSON files.

    This adapter is intentionally suitable for a single local worker. A
    production multi-worker deployment should replace it with a database or
    workflow-store adapter that offers optimistic locking and leases; callers
    remain unchanged because they depend only on ``RunRepositoryPort``.
    """

    def __init__(
        self,
        base_directory: str | Path = ".selma_runs",
        *,
        lock_timeout_seconds: float = 300.0,
    ) -> None:
        if lock_timeout_seconds <= 0:
            raise ValueError("lock_timeout_seconds must be greater than zero.")
        self._base_directory = Path(base_directory)
        self._lock_timeout_seconds = lock_timeout_seconds
        self._held_run_ids: ContextVar[frozenset[str]] = ContextVar(
            "local_json_run_repository_held_run_ids",
            default=frozenset(),
        )

    async def save(self, run: PipelineRun) -> None:
        """Atomically save the aggregate without blocking the event loop."""
        async with self.lock_run(run.run_id):
            await asyncio.to_thread(self._write_run, run.to_dict())

    @asynccontextmanager
    async def lock_run(self, run_id: str) -> AsyncIterator[None]:
        """Hold an inter-process lock for a run's decisions and disk writes.

        ``RunExecutor`` keeps this lock for the whole stage transition, while
        ``save`` acquires it when used independently. The context variable
        makes that nested acquisition re-entrant within the same task.
        """
        self._validate_run_id(run_id)
        held_run_ids = self._held_run_ids.get()
        if run_id in held_run_ids:
            yield
            return

        self._base_directory.mkdir(parents=True, exist_ok=True)
        # acquire/release run in executor-pool workers via asyncio.to_thread;
        # FileLock's default thread-local state can therefore leak a lock when
        # those calls land on different threads. Shared state keeps ownership
        # attached to this lock object rather than one worker thread.
        lock = FileLock(str(self._lock_path_for(run_id)), thread_local=False)
        try:
            await asyncio.to_thread(lock.acquire, timeout=self._lock_timeout_seconds)
        except Timeout as error:
            raise PipelineRunStateError(
                f"Timed out waiting for the lock on pipeline run '{run_id}'."
            ) from error

        token = self._held_run_ids.set(held_run_ids | {run_id})
        try:
            yield
        finally:
            self._held_run_ids.reset(token)
            await asyncio.to_thread(lock.release)

    async def get_by_id(self, run_id: str) -> PipelineRun:
        """Read and rehydrate a persisted run, or raise a typed not-found error."""
        self._validate_run_id(run_id)
        try:
            data = await asyncio.to_thread(self._read_run, run_id)
        except FileNotFoundError as error:
            raise PipelineRunNotFoundError(
                f"Pipeline run '{run_id}' was not found."
            ) from error
        except (json.JSONDecodeError, OSError, UnicodeError) as error:
            raise PipelineRunStateError(
                f"Persisted pipeline run '{run_id}' could not be read."
            ) from error
        try:
            run = PipelineRun.from_dict(data)
        except (KeyError, TypeError, ValueError) as error:
            raise PipelineRunStateError(
                f"Persisted pipeline run '{run_id}' is invalid."
            ) from error
        if run.run_id != run_id:
            raise PipelineRunStateError(
                f"Persisted run ID does not match requested run '{run_id}'."
            )
        return run

    def _write_run(self, data: dict[str, Any]) -> None:
        run_id = str(data["run_id"])
        self._validate_run_id(run_id)
        self._base_directory.mkdir(parents=True, exist_ok=True)
        target_path = self._path_for(run_id)
        temporary_path = self._base_directory / f".{run_id}.{uuid.uuid4().hex}.tmp"
        serialized = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
        with temporary_path.open("w", encoding="utf-8") as temporary_file:
            temporary_file.write(serialized)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        # os.replace is atomic on one filesystem, so an interruption never
        # leaves a partially-written JSON file at the canonical run path.
        os.replace(temporary_path, target_path)

    def _read_run(self, run_id: str) -> dict[str, Any]:
        raw = self._path_for(run_id).read_text(encoding="utf-8")
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("Pipeline run JSON must contain an object.")
        return parsed

    def _path_for(self, run_id: str) -> Path:
        return self._base_directory / f"{run_id}.json"

    def _lock_path_for(self, run_id: str) -> Path:
        return self._base_directory / f"{run_id}.lock"

    @staticmethod
    def _validate_run_id(run_id: str) -> None:
        try:
            uuid.UUID(run_id)
        except (ValueError, TypeError, AttributeError) as error:
            raise ValueError("run_id must be a valid UUID.") from error
