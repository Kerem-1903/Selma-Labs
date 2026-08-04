"""
StorageReference — what a StoragePort implementation returns after persisting
data. Carries just enough to locate and describe the stored asset, without
committing the domain layer to any particular storage backend's concepts
(no S3 bucket/key semantics leaking in, no local-filesystem assumptions).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StorageReference:
    key: str
    path: str
    size_bytes: int
