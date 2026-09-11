from __future__ import annotations

import pytest

from core.application.services.asset_approval_service import AssetApprovalService
from core.domain.exceptions import PreProductionValidationError
from core.domain.value_objects.asset_approval import derive_asset_state


_DIGEST = "a" * 64


def _receipt(payload: dict[str, object] | None = None):
    manifest = payload or {"asset_id": "pack", "version": 1}
    return AssetApprovalService.receipt(
        asset_id="pack",
        asset_hash=AssetApprovalService.asset_set_digest([_DIGEST]),
        manifest_payload=manifest,
        approved_by="art-director",
    )


def test_shared_receipt_matches_exact_asset_set_and_manifest():
    manifest = {"asset_id": "pack", "version": 1}
    receipt = _receipt(manifest)

    assert AssetApprovalService.verify_asset_set(
        receipt.to_dict(),
        asset_id="pack",
        asset_hashes=[_DIGEST],
        manifest_payload=manifest,
    )
    assert not AssetApprovalService.verify_asset_set(
        receipt.to_dict(),
        asset_id="pack",
        asset_hashes=["b" * 64],
        manifest_payload=manifest,
    )


def test_manifest_change_derives_stale_not_ready():
    receipt = _receipt({"asset_id": "pack", "version": 1})

    assert derive_asset_state(
        exists=True,
        generated=True,
        qc_passed=True,
        receipt=receipt,
        asset_hash=AssetApprovalService.asset_set_digest([_DIGEST]),
        manifest_hash=AssetApprovalService.manifest_digest({"asset_id": "pack", "version": 2}),
    ) == "STALE"


def test_missing_or_unapproved_assets_never_become_ready():
    assert derive_asset_state(
        exists=False,
        generated=True,
        qc_passed=True,
        receipt=None,
    ) == "MISSING"
    assert derive_asset_state(
        exists=True,
        generated=True,
        qc_passed=True,
        receipt=None,
    ) == "REVIEW_REQUIRED"


def test_asset_set_digest_rejects_missing_content_hashes():
    with pytest.raises(PreProductionValidationError):
        AssetApprovalService.asset_set_digest([""])
