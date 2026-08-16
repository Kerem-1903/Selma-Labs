"""Atomic local JSON persistence for channel performance history."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from collections.abc import AsyncIterator

from filelock import FileLock, Timeout

from core.domain.exceptions import PerformanceDataError
from core.domain.ports.youtube_performance_repository_port import (
    YoutubePerformanceRepositoryPort,
)
from core.domain.value_objects.youtube_performance import YoutubePerformanceRecord


class LocalJsonYoutubePerformanceRepository(YoutubePerformanceRepositoryPort):
    schema_version = 1

    def __init__(
        self,
        path: str | Path,
        *,
        lock_timeout_seconds: float = 30.0,
    ) -> None:
        if lock_timeout_seconds <= 0:
            raise ValueError("lock_timeout_seconds must be greater than zero.")
        self._path = Path(path).resolve()
        self._lock = asyncio.Lock()
        self._lock_timeout_seconds = lock_timeout_seconds

    async def list_records(self) -> tuple[YoutubePerformanceRecord, ...]:
        async with self._store_lock():
            return await asyncio.to_thread(self._read)

    async def save(self, record: YoutubePerformanceRecord) -> None:
        async with self._store_lock():
            records = [
                item for item in await asyncio.to_thread(self._read)
                if item.video_id != record.video_id
            ]
            records.append(record)
            records.sort(key=lambda item: item.published_at)
            await asyncio.to_thread(self._write, tuple(records))

    @asynccontextmanager
    async def _store_lock(self) -> AsyncIterator[None]:
        async with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            lock = FileLock(f"{self._path}.lock", thread_local=False)
            try:
                await asyncio.to_thread(
                    lock.acquire,
                    timeout=self._lock_timeout_seconds,
                )
            except Timeout as error:
                raise PerformanceDataError(
                    f"Timed out waiting for YouTube performance store '{self._path}'."
                ) from error
            try:
                yield
            finally:
                await asyncio.to_thread(lock.release)

    def _read(self) -> tuple[YoutubePerformanceRecord, ...]:
        if not self._path.is_file():
            return ()
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                records_data = data
            elif isinstance(data, dict):
                if int(data.get("schema_version", -1)) != self.schema_version:
                    raise PerformanceDataError("Unsupported YouTube performance schema version.")
                records_data = data.get("records")
                if not isinstance(records_data, list):
                    raise PerformanceDataError("YouTube performance records must be a list.")
                expected = str(data.get("checksum") or "")
                actual = self._checksum(records_data)
                if not expected or expected != actual:
                    raise PerformanceDataError("YouTube performance checksum mismatch.")
            else:
                raise PerformanceDataError("YouTube performance store has an invalid root value.")
            return tuple(
                YoutubePerformanceRecord.from_dict(dict(item))
                for item in records_data
            )
        except PerformanceDataError:
            raise
        except (json.JSONDecodeError, OSError, UnicodeError, TypeError, ValueError, KeyError) as error:
            raise PerformanceDataError(
                f"YouTube performance store '{self._path}' is corrupt or invalid."
            ) from error

    def _write(self, records: tuple[YoutubePerformanceRecord, ...]) -> None:
        records_data = [item.to_dict() for item in records]
        envelope = {
            "schema_version": self.schema_version,
            "checksum": self._checksum(records_data),
            "records": records_data,
        }
        serialized = json.dumps(envelope, indent=2, ensure_ascii=False, sort_keys=True)
        temporary = self._path.parent / f".{self._path.name}.{uuid.uuid4().hex}.tmp"
        try:
            with temporary.open("w", encoding="utf-8") as handle:
                handle.write(serialized)
                handle.flush()
                os.fsync(handle.fileno())
            if self._path.is_file():
                shutil.copyfile(self._path, self._path.with_suffix(self._path.suffix + ".bak"))
            os.replace(temporary, self._path)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _checksum(records: list[dict[str, object]]) -> str:
        canonical = json.dumps(
            records,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
