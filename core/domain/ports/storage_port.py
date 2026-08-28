"""
StoragePort — the contract every binary-asset storage backend must satisfy.

Named in Architecture v1 (Section 3) and the MVP repository layout, first
implemented here in Sprint 2 because this is the first module with binary
output to persist. LocalFsStorage (this sprint) and a future MinIO/S3
adapter are interchangeable through this same interface — no service that
depends on StoragePort needs to change when that swap happens.
"""
from __future__ import annotations

import typing
from abc import ABC, abstractmethod
from collections.abc import AsyncIterable

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

    async def save_stream(
        self,
        key: str,
        chunks: AsyncIterable[bytes],
        content_type: str,
    ) -> StorageReference:
        """Persist streamed bytes; non-streaming adapters retain compatibility."""
        data = bytearray()
        async for chunk in chunks:
            data.extend(chunk)
        return await self.save(key, bytes(data), content_type)

    async def load(self, key: str) -> bytes:
        """Return bytes stored under a portable storage key.

        This concrete default preserves compatibility with older adapters
        while making binary retrieval available to reference-asset services.
        """
        raise NotImplementedError

    async def exists(self, key: str) -> bool:
        """Return whether a portable storage key can be resolved."""
        raise NotImplementedError

    @abstractmethod
    def upload_file(self, file_stream: typing.BinaryIO, destination_path: str, content_type: str) -> str:
        """Uploads a file to cloud storage and returns its access URL (or URI)."""
        pass

    @abstractmethod
    def download_file(self, source_path: str, local_destination: str) -> bool:
        """Downloads a file from cloud storage to a local temporary path."""
        pass

    @abstractmethod
    def delete_file(self, file_path: str) -> bool:
        """Deletes a file from cloud storage when no longer needed."""
        pass
