"""Attempt-scoped manifest used for idempotent Wan artifact commits."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class WanAttemptManifest:
    job_id: str
    attempt_id: str
    lease_id: str
    worker_id: str
    slot_id: str
    fencing_token: int
    render_storage_key: str
    manifest_storage_key: str
    byte_size: int | None = None
    sha256: str | None = None
    fingerprint: str | None = None

    def __post_init__(self) -> None:
        if not all(str(value).strip() for value in (
            self.job_id, self.attempt_id, self.lease_id, self.worker_id,
            self.slot_id, self.render_storage_key, self.manifest_storage_key,
        )):
            raise ValueError("Wan attempt manifest identity is required.")
        if self.fencing_token < 1:
            raise ValueError("Wan attempt manifest fencing_token must be positive.")
        if self.byte_size is not None and self.byte_size < 0:
            raise ValueError("Wan attempt manifest byte_size cannot be negative.")
        if self.sha256 is not None and len(self.sha256) != 64:
            raise ValueError("Wan attempt manifest sha256 must be a SHA-256 digest.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "attempt_id": self.attempt_id,
            "lease_id": self.lease_id,
            "worker_id": self.worker_id,
            "slot_id": self.slot_id,
            "fencing_token": self.fencing_token,
            "render_storage_key": self.render_storage_key,
            "manifest_storage_key": self.manifest_storage_key,
            "byte_size": self.byte_size,
            "sha256": self.sha256,
            "fingerprint": self.fingerprint,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> WanAttemptManifest:
        return cls(
            job_id=str(data["job_id"]),
            attempt_id=str(data["attempt_id"]),
            lease_id=str(data["lease_id"]),
            worker_id=str(data["worker_id"]),
            slot_id=str(data["slot_id"]),
            fencing_token=int(data["fencing_token"]),
            render_storage_key=str(data["render_storage_key"]),
            manifest_storage_key=str(data["manifest_storage_key"]),
            byte_size=int(data["byte_size"]) if data.get("byte_size") is not None else None,
            sha256=str(data["sha256"]) if data.get("sha256") is not None else None,
            fingerprint=str(data["fingerprint"]) if data.get("fingerprint") is not None else None,
        )
