"""Durable contracts for the pre-animation three-pose character library."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any

from core.domain.exceptions import PreProductionValidationError

POSE_PACK_POSE_IDS = (
    "FRONT_NEUTRAL",
    "PROFILE_LEFT",
    "BACK_FULL_BODY",
)
POSE_PACK_HUMAN_CHECKS = (
    "identity_consistent",
    "outfit_consistent",
    "all_three_poses_present",
    "style_consistent",
    "anatomy_and_artifacts_pass",
)
_PACK_STATUSES = {"IN_PROGRESS", "PENDING_HUMAN_REVIEW", "BLOCKED"}


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PreProductionValidationError(f"{field_name} must not be empty.")
    return value.strip()


def _key(value: object, field_name: str) -> str:
    text = _text(value, field_name).replace("\\", "/")
    path = PurePosixPath(text)
    if path.is_absolute() or ".." in path.parts or ":" in text:
        raise PreProductionValidationError(
            f"{field_name} must be a portable relative storage key."
        )
    return text


def _hash(value: object, field_name: str) -> str:
    digest = _text(value, field_name).casefold()
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise PreProductionValidationError(f"{field_name} must be a SHA-256 digest.")
    return digest


@dataclass(frozen=True)
class CharacterPoseEvidence:
    pose_id: str
    storage_key: str
    content_hash: str
    pose_template_storage_key: str
    pose_template_hash: str
    seed: int
    width: int
    height: int
    reference_storage_keys: tuple[str, ...]
    reference_hashes: tuple[str, ...]
    style_reference_hash: str
    prompt_hash: str
    workflow_hash: str
    model_hashes: Mapping[str, str]
    qc_report: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.pose_id not in POSE_PACK_POSE_IDS:
            raise PreProductionValidationError(f"Unknown pose-pack pose: {self.pose_id}")
        object.__setattr__(self, "storage_key", _key(self.storage_key, "storage_key"))
        object.__setattr__(
            self,
            "pose_template_storage_key",
            _key(self.pose_template_storage_key, "pose_template_storage_key"),
        )
        object.__setattr__(self, "content_hash", _hash(self.content_hash, "content_hash"))
        object.__setattr__(
            self, "pose_template_hash", _hash(self.pose_template_hash, "pose_template_hash")
        )
        object.__setattr__(self, "style_reference_hash", _hash(self.style_reference_hash, "style_reference_hash"))
        if self.seed < 0 or self.width <= 0 or self.height <= 0:
            raise PreProductionValidationError("Pose evidence dimensions and seed must be positive.")
        if len(self.reference_storage_keys) != len(self.reference_hashes):
            raise PreProductionValidationError("Pose references and hashes must stay aligned.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "pose_id": self.pose_id,
            "storage_key": self.storage_key,
            "content_hash": self.content_hash,
            "pose_template_storage_key": self.pose_template_storage_key,
            "pose_template_hash": self.pose_template_hash,
            "seed": self.seed,
            "width": self.width,
            "height": self.height,
            "reference_storage_keys": list(self.reference_storage_keys),
            "reference_hashes": list(self.reference_hashes),
            "style_reference_hash": self.style_reference_hash,
            "prompt_hash": self.prompt_hash,
            "workflow_hash": self.workflow_hash,
            "model_hashes": dict(self.model_hashes),
            "qc_report": dict(self.qc_report),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CharacterPoseEvidence:
        raw_models = data.get("model_hashes", {})
        raw_qc = data.get("qc_report", {})
        return cls(
            pose_id=str(data.get("pose_id", "")),
            storage_key=str(data.get("storage_key", "")),
            content_hash=str(data.get("content_hash", "")),
            pose_template_storage_key=str(data.get("pose_template_storage_key", "")),
            pose_template_hash=str(data.get("pose_template_hash", "")),
            seed=int(data.get("seed", -1)),
            width=int(data.get("width", 0)),
            height=int(data.get("height", 0)),
            reference_storage_keys=tuple(str(item) for item in data.get("reference_storage_keys", ())),
            reference_hashes=tuple(str(item) for item in data.get("reference_hashes", ())),
            style_reference_hash=str(data.get("style_reference_hash", "")),
            prompt_hash=str(data.get("prompt_hash", "")),
            workflow_hash=str(data.get("workflow_hash", "")),
            model_hashes={str(key): str(value) for key, value in raw_models.items()} if isinstance(raw_models, Mapping) else {},
            qc_report=dict(raw_qc) if isinstance(raw_qc, Mapping) else {},
        )


@dataclass(frozen=True)
class CharacterPosePackManifest:
    schema_version: int
    character_id: str
    character_version: int
    brief_hash: str
    style_id: str
    style_reference_storage_key: str
    style_reference_hash: str
    poses: tuple[CharacterPoseEvidence, ...]
    status: str
    contact_sheet_storage_key: str = ""
    contact_sheet_content_hash: str = ""
    manifest_storage_key: str = ""
    quarantined: tuple[Mapping[str, Any], ...] = ()
    artifact_mode: str = "DISCOVERY"
    production_eligible: bool = False
    style_lock_snapshot: Mapping[str, Any] = field(default_factory=dict)
    # A generated/reviewable manifest is not production-ready until a separate
    # approval receipt has been verified by the loading boundary.
    # Compatibility fields are retained for old manifests, but consumers must
    # verify the shared receipt before exposing any pose as READY.
    human_approved: bool = False
    approval_receipt: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.schema_version != 1 or self.status not in _PACK_STATUSES:
            raise PreProductionValidationError("Invalid character pose-pack manifest state.")
        if self.artifact_mode not in {"DISCOVERY", "PRODUCTION"}:
            raise PreProductionValidationError("Pose-pack artifact mode must be DISCOVERY or PRODUCTION.")
        if self.artifact_mode == "DISCOVERY" and self.production_eligible:
            raise PreProductionValidationError("Discovery pose-packs cannot be production eligible.")
        if self.artifact_mode == "PRODUCTION" and (
            not self.production_eligible or not self.style_lock_snapshot
        ):
            raise PreProductionValidationError(
                "Production pose-packs require an eligible style-lock snapshot."
            )
        object.__setattr__(self, "character_id", _text(self.character_id, "character_id"))
        object.__setattr__(self, "style_id", _text(self.style_id, "style_id"))
        object.__setattr__(self, "brief_hash", _hash(self.brief_hash, "brief_hash"))
        object.__setattr__(self, "style_reference_storage_key", _key(self.style_reference_storage_key, "style_reference_storage_key"))
        object.__setattr__(self, "style_reference_hash", _hash(self.style_reference_hash, "style_reference_hash"))
        if self.character_version < 1:
            raise PreProductionValidationError("Character version must be positive.")
        pose_ids = {pose.pose_id for pose in self.poses}
        if len(pose_ids) != len(self.poses):
            raise PreProductionValidationError("Pose-pack pose ids must be unique.")
        if self.status == "PENDING_HUMAN_REVIEW" and pose_ids != set(POSE_PACK_POSE_IDS):
            raise PreProductionValidationError("A reviewable pose pack requires all three poses.")
        if self.status == "PENDING_HUMAN_REVIEW":
            if not self.contact_sheet_storage_key or not self.contact_sheet_content_hash:
                raise PreProductionValidationError("A reviewable pose pack requires a contact sheet.")
            object.__setattr__(self, "contact_sheet_storage_key", _key(self.contact_sheet_storage_key, "contact_sheet_storage_key"))
            object.__setattr__(self, "contact_sheet_content_hash", _hash(self.contact_sheet_content_hash, "contact_sheet_content_hash"))
        if self.manifest_storage_key:
            object.__setattr__(self, "manifest_storage_key", _key(self.manifest_storage_key, "manifest_storage_key"))

    @property
    def complete(self) -> bool:
        return {pose.pose_id for pose in self.poses} == set(POSE_PACK_POSE_IDS)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "character_id": self.character_id,
            "character_version": self.character_version,
            "brief_hash": self.brief_hash,
            "style_id": self.style_id,
            "style_reference_storage_key": self.style_reference_storage_key,
            "style_reference_hash": self.style_reference_hash,
            "status": self.status,
            "complete": self.complete,
            "next_gate": "HUMAN_POSE_PACK_APPROVAL" if self.status == "PENDING_HUMAN_REVIEW" else "POSE_REGENERATION",
            "poses": [pose.to_dict() for pose in self.poses],
            "contact_sheet_storage_key": self.contact_sheet_storage_key,
            "contact_sheet_content_hash": self.contact_sheet_content_hash,
            "manifest_storage_key": self.manifest_storage_key,
            "quarantined": [dict(item) for item in self.quarantined],
            "artifact_mode": self.artifact_mode,
            "production_eligible": self.production_eligible,
            "style_lock_snapshot": dict(self.style_lock_snapshot),
            "human_approved": self.human_approved and bool(self.approval_receipt),
            "approval_receipt": dict(self.approval_receipt) if self.approval_receipt else None,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CharacterPosePackManifest:
        raw_snapshot = data.get("style_lock_snapshot", {})
        raw_receipt = data.get("approval_receipt")
        return cls(
            schema_version=int(data.get("schema_version", 0)),
            character_id=str(data.get("character_id", "")),
            character_version=int(data.get("character_version", 0)),
            brief_hash=str(data.get("brief_hash", "")),
            style_id=str(data.get("style_id", "")),
            style_reference_storage_key=str(data.get("style_reference_storage_key", "")),
            style_reference_hash=str(data.get("style_reference_hash", "")),
            poses=tuple(CharacterPoseEvidence.from_dict(item) for item in data.get("poses", ()) if isinstance(item, Mapping)),
            status=str(data.get("status", "")),
            contact_sheet_storage_key=str(data.get("contact_sheet_storage_key", "")),
            contact_sheet_content_hash=str(data.get("contact_sheet_content_hash", "")),
            manifest_storage_key=str(data.get("manifest_storage_key", "")),
            quarantined=tuple(dict(item) for item in data.get("quarantined", ()) if isinstance(item, Mapping)),
            artifact_mode=str(data.get("artifact_mode", "DISCOVERY")),
            production_eligible=bool(data.get("production_eligible", False)),
            style_lock_snapshot=(
                dict(raw_snapshot) if isinstance(raw_snapshot, Mapping) else {}
            ),
            human_approved=bool(data.get("human_approved", False)),
            approval_receipt=(
                dict(raw_receipt) if isinstance(raw_receipt, Mapping) else None
            ),
        )


@dataclass(frozen=True)
class CharacterPosePackApproval:
    schema_version: int
    character_id: str
    character_version: int
    brief_hash: str
    style_id: str
    manifest_storage_key: str
    manifest_content_hash: str
    contact_sheet_content_hash: str
    pose_hashes: Mapping[str, str]
    approved_by: str
    approved_at: datetime
    confirmed_checks: tuple[str, ...]
    asset_approval_receipt: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.schema_version != 1 or set(self.pose_hashes) != set(POSE_PACK_POSE_IDS):
            raise PreProductionValidationError("Pose-pack approval requires all three pose hashes.")
        object.__setattr__(self, "character_id", _text(self.character_id, "character_id"))
        object.__setattr__(self, "style_id", _text(self.style_id, "style_id"))
        object.__setattr__(self, "approved_by", _text(self.approved_by, "approved_by"))
        object.__setattr__(self, "manifest_storage_key", _key(self.manifest_storage_key, "manifest_storage_key"))
        _hash(self.brief_hash, "brief_hash")
        _hash(self.manifest_content_hash, "manifest_content_hash")
        _hash(self.contact_sheet_content_hash, "contact_sheet_content_hash")
        for pose_id, digest in self.pose_hashes.items():
            _hash(digest, f"{pose_id}_hash")
        if set(self.confirmed_checks) != set(POSE_PACK_HUMAN_CHECKS):
            raise PreProductionValidationError("Pose-pack approval requires every human check.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "character_id": self.character_id,
            "character_version": self.character_version,
            "brief_hash": self.brief_hash,
            "style_id": self.style_id,
            "manifest_storage_key": self.manifest_storage_key,
            "manifest_content_hash": self.manifest_content_hash,
            "contact_sheet_content_hash": self.contact_sheet_content_hash,
            "pose_hashes": dict(self.pose_hashes),
            "approved_by": self.approved_by,
            "approved_at": self.approved_at.isoformat(),
            "human_approved": True,
            "confirmed_checks": list(self.confirmed_checks),
            "next_gate": "ANIMATION_PRODUCTION",
            "asset_approval_receipt": dict(self.asset_approval_receipt) if self.asset_approval_receipt else None,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CharacterPosePackApproval:
        raw_hashes = data.get("pose_hashes", {})
        raw_receipt = data.get("asset_approval_receipt")
        return cls(
            schema_version=int(data.get("schema_version", 0)),
            character_id=str(data.get("character_id", "")),
            character_version=int(data.get("character_version", 0)),
            brief_hash=str(data.get("brief_hash", "")),
            style_id=str(data.get("style_id", "")),
            manifest_storage_key=str(data.get("manifest_storage_key", "")),
            manifest_content_hash=str(data.get("manifest_content_hash", "")),
            contact_sheet_content_hash=str(data.get("contact_sheet_content_hash", "")),
            pose_hashes={str(key): str(value) for key, value in raw_hashes.items()} if isinstance(raw_hashes, Mapping) else {},
            approved_by=str(data.get("approved_by", "")),
            approved_at=datetime.fromisoformat(str(data.get("approved_at", ""))),
            confirmed_checks=tuple(str(item) for item in data.get("confirmed_checks", ())),
            asset_approval_receipt=(
                dict(raw_receipt) if isinstance(raw_receipt, Mapping) else None
            ),
        )
