"""Independent creative and technical style-lock contracts.

A style approval is a creative decision. A production style lock is a
technical execution snapshot. They intentionally have separate lifecycles so
model/workflow changes do not invalidate the creative decision.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any

from core.domain.exceptions import PreProductionValidationError

DISCOVERY = "DISCOVERY"
PRODUCTION = "PRODUCTION"
STYLE_APPROVED = "APPROVED"
LOCK_PENDING_SMOKE = "PENDING_SMOKE_TEST"
LOCK_COMPATIBLE = "PRODUCTION_COMPATIBLE"


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PreProductionValidationError(f"{field_name} must not be empty.")
    return value.strip()


def _digest(value: object, field_name: str) -> str:
    text = _text(value, field_name).casefold()
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise PreProductionValidationError(f"{field_name} must be a SHA-256 digest.")
    return text


def _key(value: object, field_name: str) -> str:
    text = _text(value, field_name).replace("\\", "/")
    path = PurePosixPath(text)
    if path.is_absolute() or ":" in text or ".." in path.parts:
        raise PreProductionValidationError(
            f"{field_name} must be a portable relative path."
        )
    return path.as_posix()


def canonical_style_payload(style: Mapping[str, Any]) -> dict[str, Any]:
    """Return only style-owned data for the creative style hash.

    Character registry, story, and unrelated series settings are deliberately
    excluded so adding a character cannot stale existing style approvals.
    """
    fields = (
        "style_id",
        "style_version",
        "reference_asset",
        "reference_sha256",
        "width",
        "height",
        "rendering_rules",
        "composition_rules",
        "identity_policy",
    )
    payload: dict[str, Any] = {}
    for field_name in fields:
        value = style.get(field_name)
        if isinstance(value, tuple):
            value = list(value)
        payload[field_name] = value
    return payload


def canonical_style_hash(style: Mapping[str, Any]) -> str:
    payload = canonical_style_payload(style)
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def canonical_json_hash(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class StyleApprovalReceipt:
    schema_version: int
    artifact_mode: str
    series_id: str
    style_id: str
    style_version: int
    reference_sha256: str
    style_bible_sha256: str
    approval_status: str
    approval_criteria: tuple[str, ...]
    approved_by: str
    approved_at: datetime
    receipt_storage_key: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != 1 or self.artifact_mode != DISCOVERY:
            raise PreProductionValidationError(
                "Style approval receipts must be version 1 DISCOVERY artifacts."
            )
        if self.style_version < 1:
            raise PreProductionValidationError("Style version must be positive.")
        object.__setattr__(self, "series_id", _text(self.series_id, "series_id"))
        object.__setattr__(self, "style_id", _text(self.style_id, "style_id"))
        object.__setattr__(self, "reference_sha256", _digest(self.reference_sha256, "reference_sha256"))
        object.__setattr__(self, "style_bible_sha256", _digest(self.style_bible_sha256, "style_bible_sha256"))
        if self.approval_status != STYLE_APPROVED:
            raise PreProductionValidationError("Style approval receipt is not approved.")
        if not self.approval_criteria:
            raise PreProductionValidationError("Style approval requires criteria.")
        object.__setattr__(self, "approved_by", _text(self.approved_by, "approved_by"))
        if self.receipt_storage_key:
            object.__setattr__(self, "receipt_storage_key", _key(self.receipt_storage_key, "receipt_storage_key"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "artifact_mode": self.artifact_mode,
            "artifact_type": "STYLE_APPROVAL_RECEIPT",
            "production_eligible": False,
            "series_id": self.series_id,
            "style_id": self.style_id,
            "style_version": self.style_version,
            "reference_sha256": self.reference_sha256,
            "style_bible_sha256": self.style_bible_sha256,
            "approval_status": self.approval_status,
            "approval_criteria": list(self.approval_criteria),
            "approved_by": self.approved_by,
            "approved_at": self.approved_at.isoformat(),
            "receipt_storage_key": self.receipt_storage_key,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> StyleApprovalReceipt:
        return cls(
            schema_version=int(data.get("schema_version", 0)),
            artifact_mode=str(data.get("artifact_mode", "")),
            series_id=str(data.get("series_id", "")),
            style_id=str(data.get("style_id", "")),
            style_version=int(data.get("style_version", 0)),
            reference_sha256=str(data.get("reference_sha256", "")),
            style_bible_sha256=str(data.get("style_bible_sha256", "")),
            approval_status=str(data.get("approval_status", "")),
            approval_criteria=tuple(str(item) for item in data.get("approval_criteria", ())),
            approved_by=str(data.get("approved_by", "")),
            approved_at=datetime.fromisoformat(str(data.get("approved_at", ""))),
            receipt_storage_key=str(data.get("receipt_storage_key", "")),
        )


@dataclass(frozen=True)
class ProductionStyleLock:
    schema_version: int
    artifact_mode: str
    series_id: str
    style_id: str
    style_version: int
    style_approval_receipt_sha256: str
    model_lock_sha256: str
    model_hashes: Mapping[str, str]
    workflow_id: str
    workflow_sha256: str
    component_hashes: Mapping[str, str]
    width: int
    height: int
    sampler: str
    steps: int
    cfg: float
    denoise: float
    lock_version: int
    compatibility_status: str
    production_eligible: bool
    smoke_test_receipt_sha256: str = ""
    lock_storage_key: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != 1 or self.artifact_mode != PRODUCTION:
            raise PreProductionValidationError(
                "Production style locks must be version 1 PRODUCTION artifacts."
            )
        if self.style_version < 1 or self.lock_version < 1:
            raise PreProductionValidationError("Style and lock versions must be positive.")
        object.__setattr__(self, "series_id", _text(self.series_id, "series_id"))
        object.__setattr__(self, "style_id", _text(self.style_id, "style_id"))
        for field_name in (
            "style_approval_receipt_sha256",
            "model_lock_sha256",
            "workflow_sha256",
        ):
            object.__setattr__(self, field_name, _digest(getattr(self, field_name), field_name))
        if self.smoke_test_receipt_sha256:
            object.__setattr__(self, "smoke_test_receipt_sha256", _digest(self.smoke_test_receipt_sha256, "smoke_test_receipt_sha256"))
        if self.width <= 0 or self.height <= 0 or self.steps <= 0:
            raise PreProductionValidationError("Production dimensions and steps must be positive.")
        if self.denoise < 0 or self.denoise > 1 or self.cfg < 0:
            raise PreProductionValidationError("Invalid production sampler parameters.")
        if self.compatibility_status == LOCK_COMPATIBLE and not self.production_eligible:
            raise PreProductionValidationError("Compatible production locks must be eligible.")
        if self.production_eligible and (
            self.compatibility_status != LOCK_COMPATIBLE or not self.smoke_test_receipt_sha256
        ):
            raise PreProductionValidationError(
                "Production eligibility requires a compatible lock and smoke evidence."
            )
        if self.lock_storage_key:
            object.__setattr__(self, "lock_storage_key", _key(self.lock_storage_key, "lock_storage_key"))

    @property
    def digest(self) -> str:
        payload = self.to_dict()
        payload.pop("lock_storage_key", None)
        return canonical_json_hash(payload)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "artifact_mode": self.artifact_mode,
            "artifact_type": "PRODUCTION_STYLE_LOCK",
            "production_eligible": self.production_eligible,
            "series_id": self.series_id,
            "style_id": self.style_id,
            "style_version": self.style_version,
            "style_approval_receipt_sha256": self.style_approval_receipt_sha256,
            "model_lock_sha256": self.model_lock_sha256,
            "model_hashes": dict(self.model_hashes),
            "workflow_id": self.workflow_id,
            "workflow_sha256": self.workflow_sha256,
            "component_hashes": dict(self.component_hashes),
            "width": self.width,
            "height": self.height,
            "sampler": self.sampler,
            "steps": self.steps,
            "cfg": self.cfg,
            "denoise": self.denoise,
            "lock_version": self.lock_version,
            "compatibility_status": self.compatibility_status,
            "smoke_test_receipt_sha256": self.smoke_test_receipt_sha256,
            "lock_storage_key": self.lock_storage_key,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ProductionStyleLock:
        models = data.get("model_hashes", {})
        components = data.get("component_hashes", {})
        return cls(
            schema_version=int(data.get("schema_version", 0)),
            artifact_mode=str(data.get("artifact_mode", "")),
            series_id=str(data.get("series_id", "")),
            style_id=str(data.get("style_id", "")),
            style_version=int(data.get("style_version", 0)),
            style_approval_receipt_sha256=str(data.get("style_approval_receipt_sha256", "")),
            model_lock_sha256=str(data.get("model_lock_sha256", "")),
            model_hashes={str(k): str(v) for k, v in models.items()} if isinstance(models, Mapping) else {},
            workflow_id=str(data.get("workflow_id", "")),
            workflow_sha256=str(data.get("workflow_sha256", "")),
            component_hashes={str(k): str(v) for k, v in components.items()} if isinstance(components, Mapping) else {},
            width=int(data.get("width", 0)),
            height=int(data.get("height", 0)),
            sampler=str(data.get("sampler", "")),
            steps=int(data.get("steps", 0)),
            cfg=float(data.get("cfg", 0)),
            denoise=float(data.get("denoise", 0)),
            lock_version=int(data.get("lock_version", 0)),
            compatibility_status=str(data.get("compatibility_status", "")),
            production_eligible=bool(data.get("production_eligible", False)),
            smoke_test_receipt_sha256=str(data.get("smoke_test_receipt_sha256", "")),
            lock_storage_key=str(data.get("lock_storage_key", "")),
        )


@dataclass(frozen=True)
class StyleLockSnapshot:
    """Compact request-level snapshot; full lock data remains in the manifest."""

    series_id: str
    style_id: str
    style_version: int
    style_approval_receipt_sha256: str
    production_lock_digest: str
    reference_sha256: str
    style_bible_sha256: str
    source: str = "ACTIVE_SERIES"
    reference_asset: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "series_id", _text(self.series_id, "series_id"))
        object.__setattr__(self, "style_id", _text(self.style_id, "style_id"))
        for field_name in (
            "style_approval_receipt_sha256",
            "production_lock_digest",
            "reference_sha256",
            "style_bible_sha256",
        ):
            object.__setattr__(self, field_name, _digest(getattr(self, field_name), field_name))
        if self.style_version < 1:
            raise PreProductionValidationError("Style version must be positive.")
        if self.source != "ACTIVE_SERIES":
            raise PreProductionValidationError("Production snapshots must come from ACTIVE_SERIES.")
        if self.reference_asset:
            object.__setattr__(self, "reference_asset", _key(self.reference_asset, "reference_asset"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "series_id": self.series_id,
            "style_id": self.style_id,
            "style_version": self.style_version,
            "style_approval_receipt_sha256": self.style_approval_receipt_sha256,
            "production_lock_digest": self.production_lock_digest,
            "reference_sha256": self.reference_sha256,
            "style_bible_sha256": self.style_bible_sha256,
            "source": self.source,
            "reference_asset": self.reference_asset,
        }
