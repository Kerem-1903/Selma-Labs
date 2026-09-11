"""Artifact authority for immutable attempt uploads and fenced promotion."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ArtifactHead:
    exists: bool
    sha256: str | None = None
    byte_size: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ArtifactPutResult:
    accepted: bool
    reused: bool = False
    conflict: str | None = None


@dataclass(frozen=True)
class PromoteResult:
    accepted: bool
    reused: bool = False
    conflict: str | None = None


class WanArtifactStorePort(ABC):
    @abstractmethod
    async def put_if_absent_or_same(
        self, key: str, data: bytes, sha256: str, byte_size: int
    ) -> ArtifactPutResult:
        raise NotImplementedError

    @abstractmethod
    async def head(self, key: str) -> ArtifactHead:
        raise NotImplementedError

    @abstractmethod
    async def promote_if_fenced(
        self, source_key: str, final_key: str, fingerprint: str, fencing_token: int
    ) -> PromoteResult:
        raise NotImplementedError

    async def register_fencing_token(self, job_id: str, fencing_token: int) -> None:
        """Persist the newest token before a worker can expose a final artifact."""
        raise NotImplementedError
