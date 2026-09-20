"""Checksummed, revision-CAS JSON authority for the pre-GPU Wan queue."""

from __future__ import annotations

import asyncio
import json
import os
import re
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast
from weakref import WeakValueDictionary

from core.domain.entities.wan_render_job import WanRenderJob, WanRenderJobStatus
from core.domain.exceptions import StorageError
from core.domain.ports.storage_port import StoragePort
from core.domain.ports.wan_checkpoint_store_port import (
    CheckpointWriteResult,
    HeartbeatResult,
    WanCheckpointStorePort,
)
from core.domain.ports.wan_job_repository_port import WanJobRepositoryPort
from core.domain.services.wan_checkpoint_codec import (
    job_checksum,
    migrate_v1_envelope,
    verify_envelope,
)


class LocalJsonWanJobRepository(WanJobRepositoryPort, WanCheckpointStorePort):
    """Mounted-volume checkpoint authority with an optional mirror.

    The queue methods are retained for compatibility; all state mutations use
    the same lock and revision compare-and-swap as the checkpoint port.
    """

    SCHEMA_VERSION = 2
    _SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
    _locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()

    def __init__(self, root_directory: str | Path, *, checkpoint_storage: StoragePort | None = None,
                 checkpoint_prefix: str = "wan-worker/checkpoints", provider_persistent_volume: bool = False) -> None:
        if not str(root_directory).strip():
            raise ValueError("A provider persistent-volume root is required for the Wan queue.")
        if checkpoint_storage is None and not provider_persistent_volume:
            raise ValueError("Wan queue requires checkpoint_storage or an explicitly declared provider persistent volume.")
        self._root = Path(root_directory).resolve()
        self._storage = checkpoint_storage
        self._prefix = checkpoint_prefix.strip("/")
        lock_key = str(self._root).casefold()
        lock = self._locks.get(lock_key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[lock_key] = lock
        self._lock = lock
        self._coordinator_lock_path = self._root / ".coordinator.lock"
        self._authority_guard_path = self._root / ".wan-authority.guard"

    async def add(self, job: WanRenderJob) -> None:
        self._validate_id(job.job_id)
        async with self._lock:
            with self._authority_guard():
                if await asyncio.to_thread(self._path_for(job.job_id).exists):
                    raise ValueError(f"Wan job '{job.job_id}' already exists.")
                await self._write_unlocked(job, expected_revision=-1)

    async def save(self, job: WanRenderJob, *, expected_revision: int | None = None) -> None:
        self._validate_id(job.job_id)
        async with self._lock:
            with self._authority_guard():
                await self._load_unlocked(job.job_id)
                expected = job.revision - 1 if expected_revision is None else expected_revision
                await self._write_unlocked(job, expected_revision=expected)

    async def get(self, job_id: str) -> WanRenderJob:
        self._validate_id(job_id)
        async with self._lock:
            return await self._load_unlocked(job_id)

    async def list(self, prefix: str | None = None):
        async with self._lock:
            if prefix is not None:
                return tuple(self._storage_key(path.stem) for path in await asyncio.to_thread(lambda: sorted(self._root.glob("*.json"))) if prefix in self._storage_key(path.stem))
            return await self._list_jobs_unlocked()

    async def claim_next(self, slot_id: str, lease_seconds: float) -> WanRenderJob | None:
        if not slot_id.strip() or lease_seconds <= 0:
            raise ValueError("A slot id and positive claim lease are required.")
        async with self._lock:
            with self._authority_guard():
                now = datetime.now(timezone.utc)
                jobs = list(await self._list_jobs_unlocked())
                candidates: list[WanRenderJob] = []
                for job in jobs:
                    if job.status in {WanRenderJobStatus.RUNNING, WanRenderJobStatus.VERIFYING} and job.lease_expires_at and job.lease_expires_at <= now:
                        job = job.recover_expired_claim()
                        await self._write_unlocked(job, expected_revision=job.revision - 1)
                    if job.status in {WanRenderJobStatus.PENDING, WanRenderJobStatus.RETRY_REQUIRED}:
                        candidates.append(job)
                if not candidates:
                    return None
                selected = min(candidates, key=lambda item: (item.priority, item.created_at, item.job_id))
                claimed = selected.claim(slot_id, now + timedelta(seconds=lease_seconds), worker_id=slot_id)
                await self._write_unlocked(claimed, expected_revision=selected.revision)
                return claimed

    async def commit_fenced(self, job_id: str, lease_id: str, attempt_id: str, fencing_token: int, expected_revision: int, operation):
        self._validate_id(job_id)
        async with self._lock:
            with self._authority_guard():
                current = await self._load_unlocked(job_id)
                current.assert_fence(lease_id, attempt_id, fencing_token)
                if current.revision != expected_revision:
                    raise ValueError("Wan stale writer revision conflict.")
                completed = await operation(current)
                if completed.revision != expected_revision + 1:
                    raise ValueError("Fenced operation must advance revision exactly once.")
                await self._write_unlocked(completed, expected_revision=expected_revision)
                return completed

    async def heartbeat(self, checkpoint_key: str, lease_id: str, attempt_id: str, fencing_token: int, expected_revision: int, requested_lease_extension: float):
        job_id = Path(checkpoint_key).stem
        self._validate_id(job_id)
        if requested_lease_extension <= 0:
            raise ValueError("Heartbeat extension must be positive.")
        async with self._lock:
            with self._authority_guard():
                try:
                    current = await self._load_unlocked(job_id)
                    current.assert_fence(lease_id, attempt_id, fencing_token)
                    if current.revision != expected_revision:
                        return HeartbeatResult(False, current.revision, fencing_token=fencing_token, conflict="STALE_REVISION")
                    updated = current.heartbeat(lease_id, attempt_id, fencing_token, datetime.now(timezone.utc) + timedelta(seconds=requested_lease_extension))
                    await self._write_unlocked(updated, expected_revision=expected_revision)
                    return HeartbeatResult(True, updated.revision, updated.lease_expires_at, updated.heartbeat_at, updated.fencing_token)
                except ValueError as exc:
                    return HeartbeatResult(False, expected_revision, fencing_token=fencing_token, conflict=str(exc))

    async def put_if_revision(self, checkpoint_key: str, expected_revision: int, envelope: dict) -> CheckpointWriteResult:
        job_id = Path(checkpoint_key).stem
        self._validate_id(job_id)
        async with self._lock:
            with self._authority_guard():
                try:
                    current = await self._load_unlocked(job_id)
                    current_revision = current.revision
                except ValueError:
                    current_revision = -1
                requested_revision = int(envelope.get("revision", -1))
                if current_revision != expected_revision:
                    return CheckpointWriteResult(False, current_revision, conflict="STALE_REVISION")
                if requested_revision != expected_revision + 1:
                    return CheckpointWriteResult(False, current_revision, conflict="INVALID_REVISION")
                job = WanRenderJob.from_dict(envelope["job"])
                await self._write_unlocked(job, expected_revision=expected_revision)
                committed = self._envelope(job, committed=True)
                return CheckpointWriteResult(True, job.revision, committed["checksum"])

    async def acquire_coordinator_lock(self, owner_id: str, ttl: float) -> bool:
        if not owner_id.strip() or ttl <= 0:
            raise ValueError("Coordinator owner and TTL are required.")
        async with self._lock:
            with self._coordinator_guard():
                now = datetime.now(timezone.utc)
                self._root.mkdir(parents=True, exist_ok=True)
                payload = json.dumps(
                    {"owner_id": owner_id, "expires_at": (now + timedelta(seconds=ttl)).isoformat()},
                    sort_keys=True,
                ).encode("utf-8")
                try:
                    self._exclusive_write(self._coordinator_lock_path, payload)
                    return True
                except FileExistsError:
                    try:
                        current = json.loads(self._coordinator_lock_path.read_text(encoding="utf-8"))
                        expires_at = datetime.fromisoformat(str(current["expires_at"]))
                        if str(current["owner_id"]) == owner_id:
                            self._write_coordinator_lock(owner_id, now + timedelta(seconds=ttl))
                            return True
                        if expires_at > now:
                            return False
                        self._coordinator_lock_path.unlink(missing_ok=True)
                        self._exclusive_write(self._coordinator_lock_path, payload)
                        return True
                    except FileExistsError:
                        return False
                    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
                        return False

    async def renew_coordinator_lock(self, owner_id: str, ttl: float) -> bool:
        if ttl <= 0:
            raise ValueError("Coordinator lock TTL must be positive.")
        async with self._lock:
            with self._coordinator_guard():
                try:
                    current = json.loads(self._coordinator_lock_path.read_text(encoding="utf-8"))
                    if str(current["owner_id"]) != owner_id or datetime.fromisoformat(str(current["expires_at"])) <= datetime.now(timezone.utc):
                        return False
                except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
                    return False
                self._write_coordinator_lock(owner_id, datetime.now(timezone.utc) + timedelta(seconds=ttl))
                return True

    async def release_coordinator_lock(self, owner_id: str) -> None:
        async with self._lock:
            with self._coordinator_guard():
                try:
                    current = json.loads(self._coordinator_lock_path.read_text(encoding="utf-8"))
                    if str(current["owner_id"]) == owner_id:
                        self._coordinator_lock_path.unlink(missing_ok=True)
                except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
                    return

    @contextmanager
    def _authority_guard(self):
        """Serialize checkpoint CAS operations across repository processes."""
        self._root.mkdir(parents=True, exist_ok=True)
        with self._authority_guard_path.open("a+b") as handle:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                if os.name == "nt":
                    import msvcrt

                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    @contextmanager
    def _coordinator_guard(self):
        """Serialize lock-record operations across repository processes."""
        self._root.mkdir(parents=True, exist_ok=True)
        guard_path = self._root / ".coordinator.lock.guard"
        with guard_path.open("a+b") as handle:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                if os.name == "nt":
                    import msvcrt

                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _write_coordinator_lock(self, owner_id: str, expires_at: datetime) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"owner_id": owner_id, "expires_at": expires_at.isoformat()}, sort_keys=True).encode("utf-8")
        self._atomic_write_bytes(self._coordinator_lock_path, payload)

    async def load(self, checkpoint_key: str) -> bytes:
        job_id = Path(checkpoint_key).stem
        self._validate_id(job_id)
        async with self._lock:
            envelope = self._envelope(await self._load_unlocked(job_id), committed=True)
            return self._canonical_envelope_bytes(envelope)

    async def _list_jobs_unlocked(self) -> tuple[WanRenderJob, ...]:
        if self._storage is not None and await self._storage.exists(self._index_storage_key()):
            raw = await self._storage.load(self._index_storage_key())
            index = json.loads(raw.decode("utf-8"))
            for job_id in index.get("job_ids", []):
                self._validate_id(job_id)
                if not await asyncio.to_thread(self._path_for(job_id).is_file):
                    raw_checkpoint = await self._storage.load(self._storage_key(job_id))
                    await asyncio.to_thread(self._atomic_write_bytes, self._path_for(job_id), raw_checkpoint)
        paths = await asyncio.to_thread(lambda: sorted(self._root.glob("*.json")))
        jobs = [await self._load_unlocked(path.stem) for path in paths]
        return tuple(sorted(jobs, key=lambda item: (item.priority, item.created_at, item.job_id)))

    async def _load_unlocked(self, job_id: str) -> WanRenderJob:
        path = self._path_for(job_id)
        try:
            try:
                envelope = await asyncio.to_thread(self._read_envelope, path)
            except FileNotFoundError:
                if self._storage is None:
                    raise
                envelope = json.loads((await self._storage.load(self._storage_key(job_id))).decode("utf-8"))
            if envelope.get("schema_version") == 1:
                envelope = migrate_v1_envelope(envelope)
                await self._persist_envelope_unlocked(job_id, envelope)
            verify_envelope(envelope)
            job = WanRenderJob.from_dict(envelope["job"])
            if job.job_id != job_id:
                raise ValueError("Wan checkpoint id does not match its filename.")
            return job
        except (FileNotFoundError, KeyError, TypeError, ValueError, StorageError, json.JSONDecodeError) as exc:
            raise ValueError(f"Wan job checkpoint '{job_id}' could not be read.") from exc

    async def _write_unlocked(self, job: WanRenderJob, *, expected_revision: int) -> None:
        if expected_revision >= 0:
            try:
                current = await self._load_unlocked(job.job_id)
            except ValueError:
                return await self._raise_conflict()
            if current.revision != expected_revision:
                raise ValueError("Wan stale writer revision conflict.")
            if job.revision != expected_revision + 1:
                raise ValueError("Wan checkpoint revision must increase exactly once.")
        elif job.revision != 0:
            raise ValueError("New Wan checkpoints must start at revision zero.")
        envelope = self._envelope(job, committed=True)
        await self._persist_envelope_unlocked(job.job_id, envelope)

    async def _raise_conflict(self):
        raise ValueError("Wan stale writer revision conflict.")

    async def _persist_envelope_unlocked(self, job_id: str, envelope: dict) -> None:
        payload = self._canonical_envelope_bytes(envelope)
        await asyncio.to_thread(self._atomic_write_bytes, self._path_for(job_id), payload)
        if self._storage is not None:
            await self._storage.save(self._storage_key(job_id), payload, "application/json")
            ids = sorted(path.stem for path in self._root.glob("*.json"))
            index = {"schema_version": self.SCHEMA_VERSION, "job_ids": ids}
            await self._storage.save(self._index_storage_key(), self._canonical_envelope_bytes(index), "application/json")

    def _envelope(self, job: WanRenderJob, *, committed: bool) -> dict:
        payload = job.to_dict()
        return {"schema_version": self.SCHEMA_VERSION, "revision": job.revision, "committed": committed,
                "checksum": job_checksum(payload), "updated_at": payload["updated_at"], "job": payload}

    @staticmethod
    def _canonical_envelope_bytes(payload: dict) -> bytes:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")

    def _storage_key(self, job_id: str) -> str:
        return f"{self._prefix}/{job_id}.json"

    def _index_storage_key(self) -> str:
        return f"{self._prefix}/index.json"

    def _path_for(self, job_id: str) -> Path:
        return self._root / f"{job_id}.json"

    @staticmethod
    def _read_envelope(path: Path) -> dict:
        parsed = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(parsed, dict):
            raise TypeError("Wan checkpoint must contain an object.")
        return parsed

    @staticmethod
    def _exclusive_write(path: Path, payload: bytes) -> None:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                descriptor = -1
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
        finally:
            if descriptor >= 0:
                os.close(descriptor)

    @staticmethod
    def _atomic_write_bytes(path: Path, payload: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
        try:
            with temporary.open("wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            if os.name != "nt":
                descriptor = os.open(path.parent, cast(Any, os).O_DIRECTORY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
        finally:
            temporary.unlink(missing_ok=True)

    @classmethod
    def _validate_id(cls, job_id: str) -> None:
        if not isinstance(job_id, str) or not cls._SAFE_ID.fullmatch(job_id):
            raise ValueError("Wan job_id must be a portable identifier.")

    @classmethod
    def _validate_checkpoint_key(cls, checkpoint_key: str) -> str:
        job_id = Path(checkpoint_key).stem
        cls._validate_id(job_id)
        return job_id
