"""Shared hash-bound approval operations for generated asset packs."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from core.domain.exceptions import PreProductionValidationError
from core.domain.value_objects.asset_approval import AssetApprovalReceipt, derive_asset_state

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class AssetApprovalService:
    """One owner for receipt evidence and derived asset readiness."""

    @staticmethod
    def digest(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def _evidence_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
        """Remove approval wrappers so a receipt remains stable after approval."""
        def clean(value: Any) -> Any:
            if isinstance(value, Mapping):
                return {
                    str(key): clean(item)
                    for key, item in value.items()
                    if key not in {
                        "approval_receipt",
                        "asset_approval_receipt",
                        "human_approved",
                        "approval",
                    }
                }
            if isinstance(value, list):
                return [clean(item) for item in value]
            return value

        result = clean(payload)
        if not isinstance(result, dict):  # defensive; Mapping input should always produce a dict
            raise TypeError("Approval evidence must be a JSON object.")
        return result

    @classmethod
    def manifest_digest(cls, payload: Mapping[str, Any]) -> str:
        canonical = json.dumps(
            cls._evidence_payload(payload),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return cls.digest(canonical)

    @classmethod
    def asset_set_digest(cls, asset_hashes: Sequence[str]) -> str:
        """Digest a complete, ordered-independent set of SHA-256 asset hashes."""
        values = tuple(sorted(str(item).strip().lower() for item in asset_hashes))
        if not values or any(not _SHA256.fullmatch(value) for value in values):
            raise PreProductionValidationError(
                "Every approved asset must provide a SHA-256 content hash."
            )
        return cls.digest("|".join(values).encode("utf-8"))

    @classmethod
    def receipt(
        cls,
        *,
        asset_id: str,
        asset_hash: str,
        manifest_hash: str | None = None,
        manifest_bytes: bytes | None = None,
        manifest_payload: Mapping[str, Any] | None = None,
        approved_by: str,
    ) -> AssetApprovalReceipt:
        if manifest_hash is None:
            if manifest_payload is not None:
                manifest_hash = cls.manifest_digest(manifest_payload)
            else:
                manifest_hash = cls.digest(manifest_bytes or b"")
        return AssetApprovalReceipt(
            schema_version=1,
            asset_id=asset_id,
            asset_hash=asset_hash,
            manifest_hash=manifest_hash,
            approved_by=approved_by,
            approved_at=datetime.now(timezone.utc),
        )

    @classmethod
    def verify(
        cls,
        receipt: AssetApprovalReceipt,
        *,
        asset_hash: str,
        manifest_hash: str | None = None,
        manifest_bytes: bytes | None = None,
        manifest_payload: Mapping[str, Any] | None = None,
    ) -> bool:
        if manifest_hash is None:
            manifest_hash = (
                cls.manifest_digest(manifest_payload)
                if manifest_payload is not None
                else cls.digest(manifest_bytes or b"")
            )
        return receipt.matches(asset_hash=asset_hash, manifest_hash=manifest_hash)

    @classmethod
    def verify_asset_set(
        cls,
        receipt_payload: Mapping[str, Any] | None,
        *,
        asset_id: str,
        asset_hashes: Sequence[str],
        manifest_payload: Mapping[str, Any],
    ) -> bool:
        if not isinstance(receipt_payload, Mapping):
            return False
        try:
            receipt = AssetApprovalReceipt.from_dict(receipt_payload)
            asset_hash = cls.asset_set_digest(asset_hashes)
        except (KeyError, TypeError, ValueError, OverflowError, PreProductionValidationError):
            return False
        return (
            receipt.asset_id == asset_id
            and cls.verify(
                receipt,
                asset_hash=asset_hash,
                manifest_payload=manifest_payload,
            )
        )

    @classmethod
    def state(
        cls,
        *,
        exists: bool,
        generated: bool,
        qc_passed: bool,
        receipt: AssetApprovalReceipt | None,
        asset_hash: str = "",
        manifest_bytes: bytes = b"",
        manifest_payload: Mapping[str, Any] | None = None,
    ) -> str:
        manifest_hash = (
            cls.manifest_digest(manifest_payload)
            if manifest_payload is not None
            else cls.digest(manifest_bytes) if manifest_bytes else ""
        )
        return derive_asset_state(
            exists=exists,
            generated=generated,
            qc_passed=qc_passed,
            receipt=receipt,
            asset_hash=asset_hash,
            manifest_hash=manifest_hash,
        )

    @staticmethod
    def receipt_payload(receipt: AssetApprovalReceipt) -> Mapping[str, Any]:
        return receipt.to_dict()
