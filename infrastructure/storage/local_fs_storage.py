"""
LocalFsStorage — StoragePort adapter that writes to the local filesystem.

MVP-appropriate storage backend per the MVP plan: one machine, one creator,
no need for MinIO/S3 yet. StoragePort stays abstract so swapping this for a
real S3-compatible adapter later is a config + one new class change, not a
rewrite of any service that depends on StoragePort.
"""
from __future__ import annotations

from pathlib import Path

from core.domain.exceptions import StorageError
from core.domain.ports.storage_port import StoragePort
from core.domain.value_objects.storage_reference import StorageReference


class LocalFsStorage(StoragePort):
    """Persists assets under a root directory on the local filesystem."""

    def __init__(self, root_dir: str) -> None:
        self._root_dir = Path(root_dir)

    async def save(self, key: str, data: bytes, content_type: str) -> StorageReference:
        # content_type is accepted for interface compatibility with future
        # backends (e.g. S3 needs it for the object's Content-Type header)
        # but is unused here — the local filesystem has no such concept.
        del content_type

        destination = self._root_dir / key
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        except OSError as exc:
            raise StorageError(f"Failed to write asset to '{destination}': {exc}") from exc

        return StorageReference(
            key=key,
            path=str(destination.resolve()),
            size_bytes=len(data),
        )
