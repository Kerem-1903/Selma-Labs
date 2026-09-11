"""Durable state machine for an unattended Wan render."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from core.domain.value_objects.wan22_animation_package import Wan22AnimationPackage
from core.domain.value_objects.wan22_render_profile import Wan22RenderProfile


def _now() -> datetime:
    return datetime.now(timezone.utc)


class WanRenderJobStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    RETRY_REQUIRED = "RETRY_REQUIRED"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


class WanTechnicalError(str, Enum):
    TIMEOUT = "TIMEOUT"
    BROKEN_MP4 = "BROKEN_MP4"
    FFPROBE_FAILED = "FFPROBE_FAILED"
    WRONG_FPS = "WRONG_FPS"
    WRONG_FRAME_COUNT = "WRONG_FRAME_COUNT"


class WanQualityError(str, Enum):
    LOW_VISUAL_QUALITY = "LOW_VISUAL_QUALITY"
    IDENTITY_DRIFT = "IDENTITY_DRIFT"
    MOTION_ARTIFACT = "MOTION_ARTIFACT"


@dataclass(frozen=True)
class WanRenderJob:
    job_id: str
    package: Wan22AnimationPackage
    profile: Wan22RenderProfile
    status: WanRenderJobStatus = WanRenderJobStatus.PENDING
    priority: int = 100
    attempt_count: int = 0
    max_attempts: int = 3
    claimed_by: str | None = None
    lease_expires_at: datetime | None = None
    technical_error: WanTechnicalError | None = None
    quality_error: WanQualityError | None = None
    output_storage_key: str | None = None
    allow_step_fallback: bool = False
    fallback_profile: Wan22RenderProfile | None = None
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)
    revision: int = 0
    lease_id: str | None = None
    attempt_id: str | None = None
    worker_id: str | None = None
    slot_id: str | None = None
    heartbeat_at: datetime | None = None
    fencing_token: int = 0

    def __post_init__(self) -> None:
        if not self.job_id.strip():
            raise ValueError("Wan job_id is required.")
        if self.priority < 0 or self.max_attempts < 1 or self.attempt_count < 0:
            raise ValueError("Wan job priority/attempt values are invalid.")
        if self.revision < 0 or self.fencing_token < 0:
            raise ValueError("Wan job revision/fencing values are invalid.")
        if (self.package.frame_count, self.package.fps) != (self.profile.frame_count, self.profile.fps):
            raise ValueError("Wan package frame_count/fps must match its render profile.")
        if self.allow_step_fallback:
            if self.fallback_profile is None or self.fallback_profile.steps <= self.profile.steps:
                raise ValueError("An allowed step fallback requires an explicit higher-step profile.")
        elif self.fallback_profile is not None:
            raise ValueError("fallback_profile cannot be set unless allow_step_fallback is true.")
        if self.status == WanRenderJobStatus.COMPLETED and not self.output_storage_key:
            raise ValueError("A completed Wan job requires a persistent output key.")

    @property
    def is_terminal(self) -> bool:
        return self.status in {
            WanRenderJobStatus.COMPLETED,
            WanRenderJobStatus.HUMAN_REVIEW_REQUIRED,
            WanRenderJobStatus.FAILED,
            WanRenderJobStatus.BLOCKED,
        }

    @property
    def planned_postprocess(self) -> str:
        return self.profile.postprocess.value

    def _changed(self, **changes: Any) -> WanRenderJob:
        changes.setdefault("revision", self.revision + 1)
        changes.setdefault("updated_at", _now())
        return replace(self, **changes)

    def claim(
        self,
        slot_id: str,
        lease_expires_at: datetime,
        *,
        worker_id: str | None = None,
        lease_id: str | None = None,
        attempt_id: str | None = None,
        fencing_token: int | None = None,
    ) -> WanRenderJob:
        if self.status not in {WanRenderJobStatus.PENDING, WanRenderJobStatus.RETRY_REQUIRED}:
            raise ValueError(f"Job '{self.job_id}' cannot be claimed from {self.status.value}.")
        if lease_expires_at.tzinfo is None:
            raise ValueError("Wan lease expiry must be timezone-aware.")
        return self._changed(
            status=WanRenderJobStatus.RUNNING,
            claimed_by=slot_id,
            lease_expires_at=lease_expires_at,
            attempt_count=self.attempt_count + 1,
            technical_error=None,
            lease_id=lease_id or uuid.uuid4().hex,
            attempt_id=attempt_id or uuid.uuid4().hex,
            worker_id=worker_id or slot_id,
            slot_id=slot_id,
            heartbeat_at=_now(),
            fencing_token=fencing_token if fencing_token is not None else self.fencing_token + 1,
        )

    def heartbeat(self, lease_id: str, attempt_id: str, fencing_token: int, lease_expires_at: datetime) -> WanRenderJob:
        if self.status not in {WanRenderJobStatus.RUNNING, WanRenderJobStatus.VERIFYING}:
            raise ValueError("Only an active Wan job can heartbeat.")
        self.assert_fence(lease_id, attempt_id, fencing_token)
        return self._changed(lease_expires_at=lease_expires_at, heartbeat_at=_now())

    def assert_fence(self, lease_id: str, attempt_id: str, fencing_token: int) -> None:
        if (lease_id, attempt_id, fencing_token) != (self.lease_id, self.attempt_id, self.fencing_token):
            raise ValueError("Wan stale lease, attempt, or fencing token.")
        if self.lease_expires_at is not None and self.lease_expires_at <= _now():
            raise ValueError("Wan lease has expired.")

    def recover_expired_claim(self) -> WanRenderJob:
        if self.status not in {WanRenderJobStatus.RUNNING, WanRenderJobStatus.VERIFYING}:
            return self
        next_status = (
            WanRenderJobStatus.FAILED
            if self.attempt_count >= self.max_attempts
            else WanRenderJobStatus.RETRY_REQUIRED
        )
        return self._changed(
            status=next_status,
            claimed_by=None,
            lease_expires_at=None,
            technical_error=WanTechnicalError.TIMEOUT,
            lease_id=None,
            attempt_id=None,
            worker_id=None,
            slot_id=None,
            heartbeat_at=None,
        )

    def verifying(self) -> WanRenderJob:
        if self.status != WanRenderJobStatus.RUNNING:
            raise ValueError("Only a running Wan job can be verified.")
        return self._changed(status=WanRenderJobStatus.VERIFYING)

    def retry(self, error: WanTechnicalError) -> WanRenderJob:
        if self.status not in {WanRenderJobStatus.RUNNING, WanRenderJobStatus.VERIFYING}:
            raise ValueError("Only an active Wan job can request a retry.")
        return self._changed(
            status=WanRenderJobStatus.RETRY_REQUIRED,
            claimed_by=None,
            lease_expires_at=None,
            technical_error=error,
            lease_id=None,
            attempt_id=None,
            worker_id=None,
            slot_id=None,
            heartbeat_at=None,
        )

    def fail(self, error: WanTechnicalError) -> WanRenderJob:
        return self._changed(
            status=WanRenderJobStatus.FAILED,
            claimed_by=None,
            lease_expires_at=None,
            technical_error=error,
            lease_id=None,
            attempt_id=None,
            worker_id=None,
            slot_id=None,
            heartbeat_at=None,
        )

    def require_review(self, error: WanQualityError) -> WanRenderJob:
        return self._changed(
            status=WanRenderJobStatus.HUMAN_REVIEW_REQUIRED,
            claimed_by=None,
            lease_expires_at=None,
            quality_error=error,
            lease_id=None,
            attempt_id=None,
            worker_id=None,
            slot_id=None,
            heartbeat_at=None,
        )

    def complete(self, output_storage_key: str) -> WanRenderJob:
        if self.status != WanRenderJobStatus.VERIFYING or not output_storage_key.strip():
            raise ValueError("Only a verified Wan job with a persistent key can complete.")
        return self._changed(
            status=WanRenderJobStatus.COMPLETED,
            claimed_by=None,
            lease_expires_at=None,
            output_storage_key=output_storage_key,
            lease_id=None,
            attempt_id=None,
            worker_id=None,
            slot_id=None,
            heartbeat_at=None,
        )

    def use_fallback(self) -> WanRenderJob:
        if not self.allow_step_fallback or self.fallback_profile is None:
            raise ValueError("This job manifest does not allow a higher-step fallback.")
        if self.status not in {WanRenderJobStatus.RUNNING, WanRenderJobStatus.VERIFYING}:
            raise ValueError("Fallback is only valid after an active attempt.")
        profile = self.fallback_profile
        package = replace(self.package, frame_count=profile.frame_count, fps=profile.fps)
        return self._changed(
            package=package, profile=profile, status=WanRenderJobStatus.RETRY_REQUIRED,
            claimed_by=None, lease_expires_at=None, allow_step_fallback=False,
            fallback_profile=None, lease_id=None, attempt_id=None, worker_id=None,
            slot_id=None, heartbeat_at=None,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id, "package": self.package.to_dict(), "profile": self.profile.to_dict(),
            "status": self.status.value, "priority": self.priority, "attempt_count": self.attempt_count,
            "max_attempts": self.max_attempts, "claimed_by": self.claimed_by,
            "lease_expires_at": self.lease_expires_at.isoformat() if self.lease_expires_at else None,
            "technical_error": self.technical_error.value if self.technical_error else None,
            "quality_error": self.quality_error.value if self.quality_error else None,
            "output_storage_key": self.output_storage_key, "allow_step_fallback": self.allow_step_fallback,
            "fallback_profile": self.fallback_profile.to_dict() if self.fallback_profile else None,
            "created_at": self.created_at.isoformat(), "updated_at": self.updated_at.isoformat(),
            "revision": self.revision, "lease_id": self.lease_id, "attempt_id": self.attempt_id,
            "worker_id": self.worker_id, "slot_id": self.slot_id,
            "heartbeat_at": self.heartbeat_at.isoformat() if self.heartbeat_at else None,
            "fencing_token": self.fencing_token,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> WanRenderJob:
        lease = data.get("lease_expires_at")
        heartbeat = data.get("heartbeat_at")
        fallback = data.get("fallback_profile")
        return cls(
            job_id=str(data["job_id"]), package=Wan22AnimationPackage.from_dict(data["package"]),
            profile=Wan22RenderProfile.from_dict(data["profile"]),
            status=WanRenderJobStatus(str(data.get("status", "PENDING"))), priority=int(data.get("priority", 100)),
            attempt_count=int(data.get("attempt_count", 0)), max_attempts=int(data.get("max_attempts", 3)),
            claimed_by=str(data["claimed_by"]) if data.get("claimed_by") else None,
            lease_expires_at=datetime.fromisoformat(str(lease)) if lease else None,
            technical_error=WanTechnicalError(str(data["technical_error"])) if data.get("technical_error") else None,
            quality_error=WanQualityError(str(data["quality_error"])) if data.get("quality_error") else None,
            output_storage_key=str(data["output_storage_key"]) if data.get("output_storage_key") else None,
            allow_step_fallback=bool(data.get("allow_step_fallback", False)),
            fallback_profile=Wan22RenderProfile.from_dict(fallback) if isinstance(fallback, Mapping) else None,
            created_at=datetime.fromisoformat(str(data["created_at"])), updated_at=datetime.fromisoformat(str(data["updated_at"])),
            revision=int(data.get("revision", 0)), lease_id=str(data["lease_id"]) if data.get("lease_id") else None,
            attempt_id=str(data["attempt_id"]) if data.get("attempt_id") else None,
            worker_id=str(data["worker_id"]) if data.get("worker_id") else None,
            slot_id=str(data["slot_id"]) if data.get("slot_id") else None,
            heartbeat_at=datetime.fromisoformat(str(heartbeat)) if heartbeat else None,
            fencing_token=int(data.get("fencing_token", 0)),
        )
