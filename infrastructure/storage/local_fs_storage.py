"""
LocalFsStorage — StoragePort adapter that writes to the local filesystem.

MVP-appropriate storage backend per the MVP plan: one machine, one creator,
no need for MinIO/S3 yet. StoragePort stays abstract so swapping this for a
real S3-compatible adapter later is a config + one new class change, not a
rewrite of any service that depends on StoragePort.
"""
from __future__ import annotations

import typing

import asyncio
import hashlib
import os
import re
import uuid
from collections.abc import AsyncIterable
from pathlib import Path, PurePosixPath

from core.domain.exceptions import StorageError
from core.domain.ports.storage_port import StoragePort
from core.domain.value_objects.storage_reference import StorageReference


class LocalFsStorage(StoragePort):
    """Persists assets under a root directory on the local filesystem."""

    _WINDOWS_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
    _WINDOWS_RESERVED = {
        "CON", "PRN", "AUX", "NUL",
        *(f"COM{index}" for index in range(1, 10)),
        *(f"LPT{index}" for index in range(1, 10)),
    }
    _MAX_COMPONENT_LENGTH = 120

    def __init__(self, root_dir: str) -> None:
        self._root_dir = Path(root_dir).resolve()

    async def save(self, key: str, data: bytes, content_type: str) -> StorageReference:
        # content_type is accepted for interface compatibility with future
        # backends (e.g. S3 needs it for the object's Content-Type header)
        # but is unused here — the local filesystem has no such concept.
        del content_type

        destination = self._destination_for(key)
        try:
            await asyncio.to_thread(self._write_bytes, destination, data)
        except OSError as exc:
            raise StorageError(f"Failed to write asset to '{destination}': {exc}") from exc

        return StorageReference(
            key=key,
            path=str(destination.resolve()),
            size_bytes=len(data),
        )

    async def save_stream(
        self,
        key: str,
        chunks: AsyncIterable[bytes],
        content_type: str,
    ) -> StorageReference:
        del content_type
        destination = self._destination_for(key)
        temporary = destination.parent / f".{destination.name}.{uuid.uuid4().hex}.tmp"
        handle = None
        size_bytes = 0
        try:
            await asyncio.to_thread(destination.parent.mkdir, parents=True, exist_ok=True)
            handle = await asyncio.to_thread(temporary.open, "wb")
            async for chunk in chunks:
                if not chunk:
                    continue
                await asyncio.to_thread(handle.write, chunk)
                size_bytes += len(chunk)
            await asyncio.to_thread(handle.flush)
            await asyncio.to_thread(os.fsync, handle.fileno())
            await asyncio.to_thread(handle.close)
            handle = None
            await asyncio.to_thread(os.replace, temporary, destination)
        except OSError as exc:
            raise StorageError(f"Failed to stream asset to '{destination}': {exc}") from exc
        finally:
            if handle is not None:
                await asyncio.to_thread(handle.close)
            if temporary.exists():
                await asyncio.to_thread(temporary.unlink, missing_ok=True)

        return StorageReference(
            key=key,
            path=str(destination),
            size_bytes=size_bytes,
        )

    async def load(self, key: str) -> bytes:
        source = self._destination_for(key)
        try:
            return await asyncio.to_thread(source.read_bytes)
        except OSError as exc:
            raise StorageError(f"Failed to read asset for key '{key}': {exc}") from exc

    async def exists(self, key: str) -> bool:
        source = self._destination_for(key)
        return await asyncio.to_thread(source.is_file)

    def _destination_for(self, key: str) -> Path:
        relative_path = self._portable_relative_path(key)
        destination = (self._root_dir / relative_path).resolve()
        try:
            destination.relative_to(self._root_dir)
        except ValueError as error:
            raise StorageError("Storage key must remain inside the configured root.") from error
        return destination

    @classmethod
    def _portable_relative_path(cls, key: str) -> Path:
        """Return a deterministic Windows-safe path without weakening containment.

        Object-store keys may legally contain characters such as ``:`` while
        Windows filenames may not. The public storage key remains unchanged;
        only the local materialized path is normalized. A short digest is
        added whenever normalization occurs so two different keys cannot
        collapse onto the same local file.
        """
        normalized_key = (key or "").replace("\\", "/")
        path = PurePosixPath(normalized_key)
        if (
            not normalized_key.strip()
            or path.is_absolute()
            or re.match(r"^[A-Za-z]:", normalized_key)
            or any(part in {"", ".", ".."} for part in path.parts)
        ):
            raise StorageError(
                "Storage key must remain inside the configured root and use a "
                "non-empty relative path."
            )

        changed = False
        safe_parts: list[str] = []
        for part in path.parts:
            safe = cls._WINDOWS_INVALID.sub("_", part).rstrip(" .")
            if not safe:
                safe = "_"
            stem = safe.split(".", 1)[0].upper()
            if stem in cls._WINDOWS_RESERVED:
                safe = f"_{safe}"
            if len(safe) > cls._MAX_COMPONENT_LENGTH:
                suffix = Path(safe).suffix[:20]
                digest = hashlib.sha256(part.encode("utf-8")).hexdigest()[:10]
                budget = cls._MAX_COMPONENT_LENGTH - len(suffix) - len(digest) - 1
                safe = f"{safe[:max(1, budget)]}-{digest}{suffix}"
            changed = changed or safe != part
            safe_parts.append(safe)

        if changed:
            digest = hashlib.sha256(normalized_key.encode("utf-8")).hexdigest()[:10]
            filename = safe_parts[-1]
            suffix = Path(filename).suffix
            stem = filename[: -len(suffix)] if suffix else filename
            budget = cls._MAX_COMPONENT_LENGTH - len(suffix) - len(digest) - 1
            safe_parts[-1] = f"{stem[:max(1, budget)]}-{digest}{suffix}"
        return Path(*safe_parts)

    @staticmethod
    def _write_bytes(destination: Path, data: bytes) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)

    def upload_file(self, file_stream: typing.BinaryIO, destination_path: str, content_type: str = "video/mp4") -> str:
        destination = self._destination_for(destination_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("wb") as handle:
            while True:
                chunk = file_stream.read(5 * 1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
        return str(destination.resolve())

    def download_file(self, source_path: str, local_destination: str) -> bool:
        import shutil
        source = Path(source_path)
        if not source.is_absolute():
            source = self._destination_for(source_path)
        if not source.exists():
            return False
        Path(local_destination).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, local_destination)
        return True

    def delete_file(self, file_path: str) -> bool:
        target = Path(file_path)
        if not target.is_absolute():
            target = self._destination_for(file_path)
        if target.exists():
            target.unlink()
            return True
        return False
