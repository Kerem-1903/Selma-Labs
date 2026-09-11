"""Local Wan artifact store for pre-GPU contract tests."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import uuid
from contextlib import contextmanager
from pathlib import Path

from core.domain.ports.wan_artifact_store_port import (
    ArtifactHead,
    ArtifactPutResult,
    PromoteResult,
    WanArtifactStorePort,
)


class LocalWanArtifactStore(WanArtifactStorePort):
    """Filesystem implementation with immutable attempt and fenced final keys."""

    _safe_key = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,511}$")

    def __init__(self, root_directory: str | Path) -> None:
        self._root = Path(root_directory).resolve()
        self._lock = asyncio.Lock()
        self._filesystem_guard_path = self._root / ".wan-artifact.guard"

    async def register_fencing_token(self, job_id: str, fencing_token: int) -> None:
        self._validate(job_id)
        if fencing_token < 1:
            raise ValueError("Fencing token must be positive.")
        async with self._lock:
            with self._filesystem_guard():
                path = self._watermark_path(job_id)
                current = 0
                if path.is_file():
                    try:
                        current = int(json.loads(path.read_text(encoding="utf-8"))["fencing_token"])
                    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                        raise ValueError("Fencing watermark is corrupt.") from exc
                if fencing_token < current:
                    raise ValueError("Stale fencing token.")
                await asyncio.to_thread(
                    self._atomic_write_text,
                    path,
                    json.dumps({"fencing_token": fencing_token}, sort_keys=True),
                )

    async def put_if_absent_or_same(
        self, key: str, data: bytes, sha256: str, byte_size: int
    ) -> ArtifactPutResult:
        self._validate(key)
        if byte_size != len(data) or hashlib.sha256(data).hexdigest() != sha256:
            return ArtifactPutResult(False, conflict="ARTIFACT_DIGEST_MISMATCH")
        async with self._lock:
            with self._filesystem_guard():
                path = self._path(key)
                if path.is_file():
                    existing = path.read_bytes()
                    if len(existing) == byte_size and hashlib.sha256(existing).hexdigest() == sha256:
                        return ArtifactPutResult(True, reused=True)
                    return ArtifactPutResult(False, conflict="ARTIFACT_KEY_CONFLICT")
                await asyncio.to_thread(self._atomic_write, path, data)
                return ArtifactPutResult(True)

    async def head(self, key: str) -> ArtifactHead:
        self._validate(key)
        async with self._lock:
            with self._filesystem_guard():
                path = self._path(key)
                if not path.is_file():
                    return ArtifactHead(False)
                data = path.read_bytes()
                return ArtifactHead(True, hashlib.sha256(data).hexdigest(), len(data), {})

    async def promote_if_fenced(
        self, source_key: str, final_key: str, fingerprint: str, fencing_token: int
    ) -> PromoteResult:
        self._validate(source_key)
        self._validate(final_key)
        if fencing_token < 1 or not fingerprint.strip():
            return PromoteResult(False, conflict="INVALID_FENCE")
        async with self._lock:
            with self._filesystem_guard():
                source_parts = source_key.split("/")
                if len(source_parts) < 3:
                    return PromoteResult(False, conflict="INVALID_ATTEMPT_KEY")
                watermark = self._watermark_path(source_parts[2])
                try:
                    current_token = int(
                        json.loads(watermark.read_text(encoding="utf-8"))["fencing_token"]
                    )
                except FileNotFoundError:
                    return PromoteResult(False, conflict="FENCING_WATERMARK_MISSING")
                except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
                    return PromoteResult(False, conflict="FENCING_WATERMARK_MISSING")
                if fencing_token < current_token:
                    return PromoteResult(False, conflict="STALE_FENCING_TOKEN")

                source = self._path(source_key)
                if not source.is_file():
                    return PromoteResult(False, conflict="SOURCE_MISSING")
                final = self._path(final_key)
                metadata = self._metadata_path(final_key)

                if final.is_file() and not metadata.is_file():
                    final_data = final.read_bytes()
                    if hashlib.sha256(final_data).hexdigest() != fingerprint:
                        return PromoteResult(False, conflict="FINAL_FINGERPRINT_MISMATCH")
                    await asyncio.to_thread(
                        self._atomic_write_text,
                        metadata,
                        json.dumps(
                            {
                                "fingerprint": fingerprint,
                                "fencing_token": fencing_token,
                                "source_key": source_key,
                            },
                            sort_keys=True,
                        ),
                    )
                    return PromoteResult(True, reused=True)

                if metadata.is_file() and not final.is_file():
                    try:
                        current = json.loads(metadata.read_text(encoding="utf-8"))
                        recorded_source_key = str(current["source_key"])
                        recorded_token = int(current["fencing_token"])
                        recorded_fingerprint = str(current["fingerprint"])
                        source_data = self._path(recorded_source_key).read_bytes()
                    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
                        return PromoteResult(False, conflict="FINAL_METADATA_CORRUPT")
                    if recorded_token != fencing_token:
                        return PromoteResult(False, conflict="STALE_FENCING_TOKEN")
                    if (
                        recorded_fingerprint != fingerprint
                        or hashlib.sha256(source_data).hexdigest() != recorded_fingerprint
                    ):
                        return PromoteResult(False, conflict="FINAL_FINGERPRINT_MISMATCH")
                    await asyncio.to_thread(self._atomic_write, final, source_data)
                    return PromoteResult(True, reused=True)

                if final.is_file() and metadata.is_file():
                    try:
                        current = json.loads(metadata.read_text(encoding="utf-8"))
                        recorded_token = int(current["fencing_token"])
                        recorded_fingerprint = str(current["fingerprint"])
                    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
                        return PromoteResult(False, conflict="FINAL_METADATA_CORRUPT")
                    final_data = final.read_bytes()
                    if (
                        recorded_fingerprint == fingerprint
                        and recorded_token <= fencing_token
                        and hashlib.sha256(final_data).hexdigest() == recorded_fingerprint
                    ):
                        return PromoteResult(True, reused=True)
                    if recorded_token > fencing_token:
                        return PromoteResult(False, conflict="STALE_FENCING_TOKEN")
                    return PromoteResult(False, conflict="FINAL_KEY_CONFLICT")

                data = source.read_bytes()
                if hashlib.sha256(data).hexdigest() != fingerprint:
                    return PromoteResult(False, conflict="SOURCE_FINGERPRINT_MISMATCH")
                await asyncio.to_thread(self._atomic_write, final, data)
                await asyncio.to_thread(
                    self._atomic_write_text,
                    metadata,
                    json.dumps(
                        {
                            "fingerprint": fingerprint,
                            "fencing_token": fencing_token,
                            "source_key": source_key,
                        },
                        sort_keys=True,
                    ),
                )
                return PromoteResult(True)

    @contextmanager
    def _filesystem_guard(self):
        """Serialize artifact mutations across store instances/processes."""
        self._root.mkdir(parents=True, exist_ok=True)
        with self._filesystem_guard_path.open("a+b") as handle:
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

    def _path(self, key: str) -> Path:
        relative = Path(*key.split("/"))
        path = (self._root / relative).resolve()
        try:
            path.relative_to(self._root)
        except ValueError as exc:
            raise ValueError("Wan artifact key escapes its root.") from exc
        return path

    def _metadata_path(self, key: str) -> Path:
        path = self._path(key)
        return path.with_name(f".{path.name}.promote.json")

    def _watermark_path(self, job_id: str) -> Path:
        return self._root / "wan" / "fencing" / f"{job_id}.json"

    @classmethod
    def _validate(cls, key: str) -> None:
        if not cls._safe_key.fullmatch(key) or ".." in key.split("/"):
            raise ValueError("Wan artifact key must be a portable relative key.")

    @staticmethod
    def _atomic_write(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
        try:
            with temporary.open("wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _atomic_write_text(path: Path, data: str) -> None:
        LocalWanArtifactStore._atomic_write(path, data.encode("utf-8"))
