"""Hash-bound asset approval and readiness contracts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from core.domain.exceptions import PreProductionValidationError

_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
_ASSET_STATES = frozenset({
    "PLANNED", "GENERATED", "QC_PASSED", "REVIEW_REQUIRED", "APPROVED",
    "READY", "MISSING", "STALE", "REJECTED", "BLOCKED",
})


def _hash(value: object, field: str) -> str:
    text = str(value).strip().lower()
    if not _SHA256.fullmatch(text):
        raise PreProductionValidationError(f"{field} must be a SHA-256 digest.")
    return text


@dataclass(frozen=True)
class AssetApprovalReceipt:
    """Approval evidence for one exact asset and manifest byte version."""

    schema_version: int
    asset_id: str
    asset_hash: str
    manifest_hash: str
    approved_by: str
    approved_at: datetime
    approval_type: str = "human"
    status: str = "APPROVED"

    def __post_init__(self) -> None:
        if self.schema_version != 1 or not self.asset_id.strip():
            raise PreProductionValidationError("Approval receipt identity is incomplete.")
        object.__setattr__(self, "asset_hash", _hash(self.asset_hash, "asset_hash"))
        object.__setattr__(self, "manifest_hash", _hash(self.manifest_hash, "manifest_hash"))
        if not self.approved_by.strip() or self.approval_type != "human":
            raise PreProductionValidationError("Only named human approvals are valid.")
        if self.status not in {"APPROVED", "STALE", "REJECTED"}:
            raise PreProductionValidationError("Unknown approval receipt status.")

    def matches(self, *, asset_hash: str, manifest_hash: str) -> bool:
        return (
            self.status == "APPROVED"
            and self.asset_hash == str(asset_hash).strip().lower()
            and self.manifest_hash == str(manifest_hash).strip().lower()
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "asset_id": self.asset_id,
            "asset_hash": self.asset_hash,
            "manifest_hash": self.manifest_hash,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at.isoformat(),
            "approval_type": self.approval_type,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AssetApprovalReceipt":
        return cls(
            schema_version=int(data.get("schema_version", 0)),
            asset_id=str(data.get("asset_id", "")),
            asset_hash=str(data.get("asset_hash", "")),
            manifest_hash=str(data.get("manifest_hash", "")),
            approved_by=str(data.get("approved_by", "")),
            approved_at=datetime.fromisoformat(str(data.get("approved_at", ""))),
            approval_type=str(data.get("approval_type", "")),
            status=str(data.get("status", "")),
        )


def derive_asset_state(
    *,
    exists: bool,
    generated: bool,
    qc_passed: bool,
    receipt: AssetApprovalReceipt | None,
    asset_hash: str = "",
    manifest_hash: str = "",
) -> str:
    """Derive state; stored booleans never grant READY by themselves."""
    if not exists:
        return "MISSING"
    if receipt is not None and receipt.status == "REJECTED":
        return "REJECTED"
    if receipt is not None and not receipt.matches(asset_hash=asset_hash, manifest_hash=manifest_hash):
        return "STALE"
    if receipt is not None and receipt.status == "APPROVED" and qc_passed:
        return "READY"
    if qc_passed:
        return "REVIEW_REQUIRED"
    if generated:
        return "GENERATED"
    return "PLANNED"


def validate_asset_state(value: str) -> str:
    if value not in _ASSET_STATES:
        raise PreProductionValidationError(f"Unknown asset state: {value}")
    return value
