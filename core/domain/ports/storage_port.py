"""
StoragePort — the contract every binary-asset storage backend must satisfy.

Named in Architecture v1 (Section 3) and the MVP repository layout, first
implemented here in Sprint 2 because this is the first module with binary
output to persist. LocalFsStorage (this sprint) and a future MinIO/S3
adapter are interchangeable through this same interface — no service that
depends on StoragePort needs to change when that swap happens.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from core.domain.value_objects.storage_reference import StorageReference


class StoragePort(ABC):
    """Persists binary assets and returns a reference to locate them later."""

    @abstractmethod
    async def save(self, key: str, data: bytes, content_type: str) -> StorageReference:
        """Persist ``data`` under ``key``.

        Args:
            key: A hierarchical identifier for the asset, e.g.
                "voice/<script_id>-<uuid>.mp3". Implementations decide how
                to map this to their backend (a filesystem path, an S3
                object key, etc).
            data: Raw bytes to store.
            content_type: MIME type of the data, e.g. "audio/mpeg".

        Returns:
            A StorageReference describing where the asset was stored.

        Raises:
            StorageError: The write failed.
        """
        raise NotImplementedError
