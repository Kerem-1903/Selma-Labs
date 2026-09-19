"""Audit existing character view packs for deterministic consistency evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from core.domain.value_objects.character_creation_brief import CharacterCreationBrief
from core.domain.value_objects.character_design import CharacterReferenceDraftPack
from core.domain.value_objects.character_identity_contract import CharacterIdentityContract
from core.domain.value_objects.character_view_consistency_qc import (
    HUMAN_REQUIRED_CONSISTENCY_CHECKS,
)

_EXPECTED_VIEWS = (
    "FACE_CLOSEUP",
    "FRONT",
    "PROFILE_LEFT",
    "PROFILE_RIGHT",
    "THREE_QUARTER_LEFT",
    "THREE_QUARTER_RIGHT",
    "BACK",
)


class CharacterViewConsistencyReportService:
    """Audit evidence/provenance; never infer visual similarity from pixels.

    Visual identity decisions are accepted only through an explicit human review
    receipt. The report therefore separates deterministic evidence failures from
    human ACCEPT/REJECT decisions.
    """

    _REVIEW_DECISIONS = {"ACCEPT", "REJECT"}

    def build(
        self,
        *,
        pack_path: str | Path,
        brief_path: str | Path,
        manifest_path: str | Path | None = None,
        human_review_path: str | Path | None = None,
    ) -> dict[str, Any]:
        pack_file = Path(pack_path)
        raw_pack = self._load_object(pack_file, "view-pack")
        brief = CharacterCreationBrief.from_dict(
            self._load_object(Path(brief_path), "character brief")
        )
        pack = CharacterReferenceDraftPack.from_dict(raw_pack)
        contract = CharacterIdentityContract.from_brief(brief)
        manifest_file = Path(manifest_path) if manifest_path else pack_file.parent / "manifest.json"
        manifest = self._load_object(manifest_file, "production manifest") if manifest_file.is_file() else None
        manifest_assets = self._manifest_assets(manifest)
        human_review = self._load_human_review(
            human_review_path,
            character_id=brief.character_id,
            character_version=pack.character_version,
        )
        drafts_by_view = {draft.view: draft for draft in pack.drafts}
        missing_views = [view for view in _EXPECTED_VIEWS if view not in drafts_by_view]
        unexpected_views = sorted(set(drafts_by_view) - set(_EXPECTED_VIEWS))
        storage_root = self._storage_root(pack_file, pack)
        view_reports = [
            self._audit_view(
                draft=drafts_by_view[view],
                storage_root=storage_root,
                manifest_assets=manifest_assets,
                contract_hash=contract.content_hash,
                human_review=(human_review or {}).get("views", {}).get(view),
            )
            for view in _EXPECTED_VIEWS
            if view in drafts_by_view
        ]
        automatic_checks = {
            "pack_complete": not missing_views and not unexpected_views and pack.status in {
                "PENDING_HUMAN_REVIEW",
                "APPROVED",
                "READY",
            },
            "identity_contract_available": bool(contract.content_hash),
            "all_view_assets_hash_locked": all(item["automatic_checks"]["asset_hash_matches"] for item in view_reports),
            "all_reference_chains_hash_locked": all(item["automatic_checks"]["reference_chain_hashes_match"] for item in view_reports),
            "manifest_provenance_available": bool(manifest_assets) and all(item["automatic_checks"]["manifest_asset_matches"] for item in view_reports),
            "consistency_contract_bound_in_pack": all(item["automatic_checks"]["consistency_contract_present"] for item in view_reports) and len(view_reports) == len(_EXPECTED_VIEWS),
            "model_provenance_present": all(item["automatic_checks"]["model_provenance_present"] for item in view_reports),
        }
        blockers = [name for name, passed in automatic_checks.items() if not passed]
        return {
            "schema_version": 1,
            "report_type": "character_view_evidence_provenance_audit",
            "audit_scope": "file_hash_reference_chain_manifest_provenance_only",
            "status": (
                "REJECTED_HUMAN_REVIEW"
                if human_review and human_review.get("decision") == "REJECT"
                else "HUMAN_REVIEW_REQUIRED" if not blockers else "BLOCKED_AUTOMATIC"
            ),
            "character_id": brief.character_id,
            "character_version": pack.character_version,
            "brief_hash": brief.content_hash,
            "identity_contract_hash": contract.content_hash,
            "pack_path": pack_file.as_posix(),
            "manifest_path": manifest_file.as_posix(),
            "pack_status": pack.status,
            "automatic_checks": automatic_checks,
            "automatic_passed": not blockers,
            "automatic_blockers": blockers,
            "missing_views": missing_views,
            "unexpected_views": unexpected_views,
            "human_required_checks": list(HUMAN_REQUIRED_CONSISTENCY_CHECKS),
            "human_review_policy": "Automatic evidence never replaces visual human approval.",
            "human_review": human_review,
            "views": view_reports,
            "summary": {
                "expected_view_count": len(_EXPECTED_VIEWS),
                "present_view_count": len(view_reports),
                "asset_hash_failures": sum(not item["automatic_checks"]["asset_hash_matches"] for item in view_reports),
                "reference_chain_failures": sum(not item["automatic_checks"]["reference_chain_hashes_match"] for item in view_reports),
                "human_review_view_count": len(view_reports),
                "human_rejected_view_count": sum(
                    bool(item.get("human_review") and item["human_review"].get("decision") == "REJECT")
                    for item in view_reports
                ),
            },
        }

    @staticmethod
    def _storage_root(pack_file: Path, pack: CharacterReferenceDraftPack) -> Path:
        marker = Path(pack.canonical_storage_key).parts
        if len(marker) >= 3:
            return pack_file.parent.parents[len(marker) - 2]
        return pack_file.parent

    @staticmethod
    def _audit_view(*, draft: Any, storage_root: Path, manifest_assets: dict[str, dict[str, Any]], contract_hash: str, human_review: dict[str, Any] | None = None) -> dict[str, Any]:
        image_path = storage_root / Path(draft.storage_key)
        if not image_path.is_file():
            image_path = storage_root / "characters" / Path(draft.storage_key).name
        image_exists = image_path.is_file()
        actual_hash = hashlib.sha256(image_path.read_bytes()).hexdigest() if image_exists else ""
        reference_hashes_match = True
        reference_checks: list[dict[str, Any]] = []
        for key, expected_hash in zip(draft.conditioning_source_keys, draft.conditioning_source_hashes):
            reference_path = storage_root / Path(key)
            exists = reference_path.is_file()
            actual_reference_hash = hashlib.sha256(reference_path.read_bytes()).hexdigest() if exists else ""
            matches = exists and actual_reference_hash == expected_hash
            reference_hashes_match = reference_hashes_match and matches
            reference_checks.append({"storage_key": key, "exists": exists, "expected_hash": expected_hash, "actual_hash": actual_reference_hash, "matches": matches})
        manifest_entry = manifest_assets.get(draft.storage_key)
        qc = dict(draft.qc_report or {})
        consistency = qc.get("consistency_qc")
        model_hashes = manifest_entry.get("model_hashes") if manifest_entry else None
        return {
            "view": draft.view,
            "storage_key": draft.storage_key,
            "image_path": image_path.as_posix(),
            "content_hash": draft.content_hash,
            "qc_passed": bool(qc.get("passed")),
            "consistency_qc": consistency if isinstance(consistency, dict) else None,
            "human_review": human_review,
            "reference_checks": reference_checks,
            "automatic_checks": {
                "asset_exists": image_exists,
                "asset_hash_matches": image_exists and actual_hash == draft.content_hash,
                "reference_chain_hashes_match": reference_hashes_match and bool(reference_checks),
                "manifest_asset_matches": bool(manifest_entry and manifest_entry.get("content_hash") == draft.content_hash and manifest_entry.get("storage_key") == draft.storage_key),
                "prompt_hash_present": bool(draft.prompt_hash),
                "workflow_hash_present": bool(draft.workflow_hash),
                "model_provenance_present": isinstance(model_hashes, dict) and bool(model_hashes),
                "identity_contract_bound": bool(isinstance(consistency, dict) and consistency.get("contract_hash") == contract_hash),
                "consistency_contract_present": isinstance(consistency, dict),
            },
            "human_required_checks": list(HUMAN_REQUIRED_CONSISTENCY_CHECKS),
        }

    @classmethod
    def _load_human_review(
        cls,
        path: str | Path | None,
        *,
        character_id: str,
        character_version: int,
    ) -> dict[str, Any] | None:
        if path is None:
            return None
        payload = cls._load_object(Path(path), "human consistency review")
        if payload.get("character_id") != character_id or int(payload.get("character_version", -1)) != character_version:
            raise ValueError("Human consistency review belongs to another character version.")
        decision = str(payload.get("decision", "")).upper()
        if decision not in cls._REVIEW_DECISIONS:
            raise ValueError("Human consistency review decision must be ACCEPT or REJECT.")
        raw_views = payload.get("views")
        if not isinstance(raw_views, dict):
            raise ValueError("Human consistency review must contain a views object.")
        normalized_views: dict[str, dict[str, Any]] = {}
        for view, raw in raw_views.items():
            if not isinstance(raw, dict):
                raise ValueError(f"Human review for {view} must contain an object.")
            view_decision = str(raw.get("decision", decision)).upper()
            if view_decision not in cls._REVIEW_DECISIONS:
                raise ValueError(f"Human review decision for {view} is invalid.")
            reasons = raw.get("reasons", [])
            if not isinstance(reasons, list) or not all(isinstance(item, str) and item.strip() for item in reasons):
                raise ValueError(f"Human review reasons for {view} must be non-empty text items.")
            normalized_views[str(view)] = {
                "decision": view_decision,
                "reasons": [item.strip() for item in reasons],
                "reviewer": str(raw.get("reviewer", payload.get("reviewer", ""))),
                "reviewed_at": str(raw.get("reviewed_at", payload.get("reviewed_at", ""))),
            }
        payload["decision"] = decision
        payload["views"] = normalized_views
        return payload

    @staticmethod
    def _manifest_assets(manifest: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
        if not manifest or not isinstance(manifest.get("assets"), list):
            return {}
        return {str(item.get("storage_key")): item for item in manifest["assets"] if isinstance(item, dict) and item.get("storage_key")}

    @staticmethod
    def _load_object(path: Path, label: str) -> dict[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise FileNotFoundError(f"{label} was not found: {path}") from error
        if not isinstance(payload, dict):
            raise TypeError(f"{label} must contain a JSON object: {path}")
        return payload


__all__ = ["CharacterViewConsistencyReportService"]
