"""File-locked, restart-safe queue for licensed local MP3 and WAV files."""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from filelock import FileLock

from core.domain.exceptions import PipelineRunStateError
from core.domain.ports.audio_inbox_port import AudioInboxPort
from core.domain.value_objects.audio_inbox_job import AudioInboxJob


class LocalAudioInbox(AudioInboxPort):
    """Consumes licensed audio files from a folder with durable worker leases."""

    _SUPPORTED_SUFFIXES = {".mp3", ".wav"}

    def __init__(
        self,
        directory: str | Path = "input_audio",
        *,
        max_attempts: int = 3,
        lease_seconds: int = 3_600,
    ) -> None:
        if max_attempts <= 0:
            raise ValueError("max_attempts must be greater than zero.")
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be greater than zero.")
        self._directory = Path(directory)
        self._processing_directory = self._directory / "processing"
        self._completed_directory = self._directory / "completed"
        self._failed_directory = self._directory / "failed"
        self._state_path = self._directory / ".selma_audio_inbox.json"
        self._lock_path = self._directory / ".selma_audio_inbox.lock"
        self._max_attempts = max_attempts
        self._lease_seconds = lease_seconds
        self._worker_id = str(uuid.uuid4())

    async def claim_next(self) -> AudioInboxJob | None:
        """Atomically claim a new file or resume an expired durable lease."""
        return await asyncio.to_thread(self._claim_next_sync)

    async def mark_completed(self, job: AudioInboxJob) -> None:
        """Archive a successfully rendered source without blocking the loop."""
        await asyncio.to_thread(self._mark_completed_sync, job)

    async def renew_lease(self, job: AudioInboxJob) -> None:
        """Extend this worker's durable lease without blocking the event loop."""
        await asyncio.to_thread(self._renew_lease_sync, job)

    async def mark_failed(self, job: AudioInboxJob, reason: str) -> None:
        """Release a job for retry, or quarantine it after its retry budget."""
        await asyncio.to_thread(self._mark_failed_sync, job, reason)

    def _claim_next_sync(self) -> AudioInboxJob | None:
        self._ensure_directories()
        with FileLock(str(self._lock_path)):
            state = self._read_state()
            now = self._now()
            for record in self._records(state):
                if self._is_claimable(record, now):
                    record["status"] = "processing"
                    record["lease_owner"] = self._worker_id
                    record["lease_expires_at"] = self._lease_expiry(now)
                    self._write_state(state)
                    return self._job_from_record(record)

            source = self._next_unclaimed_source()
            if source is None:
                return None
            job_id = str(uuid.uuid4())
            processing_path = self._processing_directory / f"{job_id}{source.suffix.lower()}"
            os.replace(source, processing_path)
            record = {
                "job_id": job_id,
                "run_id": str(uuid.uuid4()),
                "source_uri": str(processing_path.resolve()),
                "attempts": 0,
                "status": "processing",
                "lease_owner": self._worker_id,
                "lease_expires_at": self._lease_expiry(now),
                "failure_reason": None,
            }
            state["jobs"].append(record)
            self._write_state(state)
            return self._job_from_record(record)

    def _mark_completed_sync(self, job: AudioInboxJob) -> None:
        self._ensure_directories()
        with FileLock(str(self._lock_path)):
            state = self._read_state()
            record = self._record_for_job(state, job)
            self._require_owned_lease(record, job)
            source_path = Path(record["source_uri"])
            completed_path = self._completed_directory / source_path.name
            if source_path.exists():
                os.replace(source_path, completed_path)
            record["source_uri"] = str(completed_path.resolve())
            record["status"] = "completed"
            record["lease_owner"] = None
            record["lease_expires_at"] = None
            self._write_state(state)

    def _renew_lease_sync(self, job: AudioInboxJob) -> None:
        self._ensure_directories()
        with FileLock(str(self._lock_path)):
            state = self._read_state()
            record = self._record_for_job(state, job)
            self._require_owned_lease(record, job)
            record["lease_expires_at"] = self._lease_expiry(self._now())
            self._write_state(state)

    def _mark_failed_sync(self, job: AudioInboxJob, reason: str) -> None:
        self._ensure_directories()
        normalized_reason = reason.strip() or "Unknown factory failure."
        with FileLock(str(self._lock_path)):
            state = self._read_state()
            record = self._record_for_job(state, job)
            self._require_owned_lease(record, job)
            record["attempts"] = int(record["attempts"]) + 1
            record["failure_reason"] = normalized_reason
            record["lease_owner"] = None
            record["lease_expires_at"] = None
            if int(record["attempts"]) >= self._max_attempts:
                source_path = Path(record["source_uri"])
                failed_path = self._failed_directory / source_path.name
                if source_path.exists():
                    os.replace(source_path, failed_path)
                record["source_uri"] = str(failed_path.resolve())
                record["status"] = "failed"
            else:
                record["status"] = "queued"
            self._write_state(state)

    def _ensure_directories(self) -> None:
        for directory in (
            self._directory,
            self._processing_directory,
            self._completed_directory,
            self._failed_directory,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def _read_state(self) -> dict[str, list[dict[str, Any]]]:
        if not self._state_path.exists():
            return {"jobs": []}
        try:
            state = json.loads(self._state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise PipelineRunStateError("Audio inbox state could not be read.") from error
        if not isinstance(state, dict) or not isinstance(state.get("jobs"), list):
            raise PipelineRunStateError("Audio inbox state is invalid.")
        return state

    def _write_state(self, state: dict[str, list[dict[str, Any]]]) -> None:
        temporary_path = self._directory / f".{uuid.uuid4().hex}.tmp"
        try:
            with temporary_path.open("w", encoding="utf-8") as temporary_file:
                json.dump(state, temporary_file, ensure_ascii=False, indent=2, sort_keys=True)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.replace(temporary_path, self._state_path)
        finally:
            if temporary_path.exists():
                temporary_path.unlink(missing_ok=True)

    def _next_unclaimed_source(self) -> Path | None:
        sources = sorted(
            (
                path
                for path in self._directory.iterdir()
                if path.is_file() and path.suffix.lower() in self._SUPPORTED_SUFFIXES
            ),
            key=lambda path: (path.stat().st_mtime, path.name.lower()),
        )
        return sources[0] if sources else None

    def _records(self, state: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
        return sorted(state["jobs"], key=lambda record: str(record["job_id"]))

    def _is_claimable(self, record: dict[str, Any], now: datetime) -> bool:
        if record.get("status") == "queued":
            return Path(str(record["source_uri"])).is_file()
        if record.get("status") != "processing":
            return False
        lease_expiry = record.get("lease_expires_at")
        return not lease_expiry or datetime.fromisoformat(str(lease_expiry)) <= now

    def _record_for_job(
        self,
        state: dict[str, list[dict[str, Any]]],
        job: AudioInboxJob,
    ) -> dict[str, Any]:
        for record in state["jobs"]:
            if record.get("job_id") == job.job_id and record.get("run_id") == job.run_id:
                return record
        raise PipelineRunStateError(f"Audio inbox job '{job.job_id}' was not found.")

    def _require_owned_lease(self, record: dict[str, Any], job: AudioInboxJob) -> None:
        if record.get("lease_owner") != self._worker_id:
            raise PipelineRunStateError(
                f"Audio inbox job '{job.job_id}' is not leased by this worker."
            )

    @staticmethod
    def _job_from_record(record: dict[str, Any]) -> AudioInboxJob:
        return AudioInboxJob(
            job_id=str(record["job_id"]),
            run_id=str(record["run_id"]),
            source_uri=str(record["source_uri"]),
            attempts=int(record["attempts"]),
        )

    def _lease_expiry(self, now: datetime) -> str:
        return (now + timedelta(seconds=self._lease_seconds)).isoformat()

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)
