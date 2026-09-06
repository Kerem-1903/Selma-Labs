"""Value objects for the v1 production-infrastructure delta layer.

Spec source: "Karakter Üretim Motoru v1" sections 3 (thermal), 4 (model lock
+ preflight), 8.1 (PoseContract), 11 (resume / work lock), 12 (watchdog).

These are pure data shapes: no I/O, no ComfyUI calls. Services own behaviour.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# --------------------------------------------------------------------------
# Model lock (spec §4 / §4.2)
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class ModelLockEntry:
    """One locked model file: role, location under the ComfyUI root, identity."""

    role: str  # e.g. "checkpoint", "ip_adapter", "clip_vision", "controlnet_openpose"
    filename: str
    relative_path: str  # relative to the ComfyUI root, posix-style
    sha256: str
    size_bytes: int
    required: bool = True
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "filename": self.filename,
            "relative_path": self.relative_path,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "required": self.required,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModelLockEntry:
        return cls(
            role=data["role"],
            filename=data["filename"],
            relative_path=data["relative_path"],
            sha256=data["sha256"],
            size_bytes=int(data["size_bytes"]),
            required=bool(data.get("required", True)),
            note=data.get("note", ""),
        )


@dataclass(frozen=True)
class ModelLock:
    schema_version: int
    comfyui_root: str
    entries: tuple[ModelLockEntry, ...] = ()

    def entry(self, role: str) -> ModelLockEntry:
        matches = [entry for entry in self.entries if entry.role == role]
        if len(matches) != 1:
            raise ValueError(f"Model lock requires exactly one '{role}' entry.")
        return matches[0]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "comfyui_root": self.comfyui_root,
            "models": [entry.to_dict() for entry in self.entries],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModelLock:
        return cls(
            schema_version=int(data.get("schema_version", 1)),
            comfyui_root=data.get("comfyui_root", ""),
            entries=tuple(ModelLockEntry.from_dict(e) for e in data.get("models", [])),
        )


# --------------------------------------------------------------------------
# Preflight (spec §4.2)
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class PreflightCheck:
    name: str
    passed: bool
    detail: str = ""
    warning: bool = False  # warnings never fail the report
    duration_sec: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "detail": self.detail,
            "warning": self.warning,
            "duration_sec": round(self.duration_sec, 3),
        }


@dataclass(frozen=True)
class PreflightReport:
    checks: tuple[PreflightCheck, ...] = ()

    @property
    def ok(self) -> bool:
        """True when every required (non-warning) check passed."""
        return all(c.passed or c.warning for c in self.checks)

    @property
    def failures(self) -> tuple[PreflightCheck, ...]:
        return tuple(c for c in self.checks if not c.passed and not c.warning)

    @property
    def warnings(self) -> tuple[PreflightCheck, ...]:
        return tuple(c for c in self.checks if not c.passed and c.warning)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "checks": [c.to_dict() for c in self.checks],
            "failures": [c.name for c in self.failures],
            "warnings": [c.name for c in self.warnings],
        }


BLOCKED_PREFLIGHT = "BLOCKED_PREFLIGHT"


# --------------------------------------------------------------------------
# Thermal policy (spec §3)
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class ThermalPolicy:
    minimum_inter_job_delay_sec: int = 10
    thermal_threshold_celsius: float = 75.0
    thermal_poll_interval_sec: int = 5
    thermal_max_wait_sec: int = 300

    def __post_init__(self) -> None:
        if self.minimum_inter_job_delay_sec < 0:
            raise ValueError("minimum_inter_job_delay_sec must be >= 0")
        if self.thermal_poll_interval_sec <= 0:
            raise ValueError("thermal_poll_interval_sec must be > 0")
        if self.thermal_max_wait_sec < 0:
            raise ValueError("thermal_max_wait_sec must be >= 0")

    def to_dict(self) -> dict[str, Any]:
        return {
            "minimum_inter_job_delay_sec": self.minimum_inter_job_delay_sec,
            "thermal_threshold_celsius": self.thermal_threshold_celsius,
            "thermal_poll_interval_sec": self.thermal_poll_interval_sec,
            "thermal_max_wait_sec": self.thermal_max_wait_sec,
        }


PAUSED_THERMAL = "PAUSED_THERMAL"


@dataclass(frozen=True)
class ThermalDecision:
    waited_sec: float = 0.0
    paused: bool = False  # True -> PAUSED_THERMAL (max wait exhausted while hot)
    temperature_celsius: float | None = None
    temperature_supported: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "waited_sec": round(self.waited_sec, 2),
            "paused": self.paused,
            "status": PAUSED_THERMAL if self.paused else "OK",
            "temperature_celsius": self.temperature_celsius,
            "temperature_supported": self.temperature_supported,
        }


# --------------------------------------------------------------------------
# Watchdog (spec §12)
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class WatchdogPolicy:
    no_progress_timeout_sec: float = 120.0
    absolute_job_timeout_sec: float = 600.0
    api_request_timeout_sec: float = 30.0
    retry_limit: int = 3

    def __post_init__(self) -> None:
        if self.no_progress_timeout_sec <= 0:
            raise ValueError("no_progress_timeout_sec must be > 0")
        if self.absolute_job_timeout_sec < self.no_progress_timeout_sec:
            raise ValueError("absolute_job_timeout_sec must be >= no_progress_timeout_sec")
        if self.api_request_timeout_sec <= 0:
            raise ValueError("api_request_timeout_sec must be > 0")
        if self.retry_limit < 0:
            raise ValueError("retry_limit must be >= 0")

    def to_dict(self) -> dict[str, Any]:
        return {
            "no_progress_timeout_sec": self.no_progress_timeout_sec,
            "absolute_job_timeout_sec": self.absolute_job_timeout_sec,
            "api_request_timeout_sec": self.api_request_timeout_sec,
            "retry_limit": self.retry_limit,
        }


@dataclass(frozen=True)
class WatchdogOutcome:
    ok: bool
    attempts: int
    reason: str = ""
    interrupted: bool = False
    prompt_id: str = ""
    detail: dict[str, Any] = field(default_factory=dict)
