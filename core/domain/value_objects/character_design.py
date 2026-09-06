"""Artifacts and approval evidence for canonical character design selection."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from core.domain.exceptions import PreProductionValidationError
from core.domain.value_objects.character_acceptance import CharacterHumanCheck


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PreProductionValidationError(f"{field_name} must not be empty.")
    return value.strip()


@dataclass(frozen=True)
class CharacterDesignCandidate:
    storage_key: str
    content_hash: str
    seed: int
    provider: str
    provider_asset_id: str
    width: int
    height: int
    run_id: str
    prompt_hash: str = ""
    workflow_hash: str = ""
    qc_report: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        for field_name in ("storage_key", "provider", "run_id"):
            object.__setattr__(
                self, field_name, _text(getattr(self, field_name), field_name)
            )
        digest = _text(self.content_hash, "content_hash").casefold()
        if len(digest) != 64 or any(
            character not in "0123456789abcdef" for character in digest
        ):
            raise PreProductionValidationError("content_hash must be a SHA-256 digest.")
        object.__setattr__(self, "content_hash", digest)
        if self.seed < 0 or self.width <= 0 or self.height <= 0:
            raise PreProductionValidationError(
                "Candidate dimensions and seed must be positive."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "storage_key": self.storage_key,
            "content_hash": self.content_hash,
            "seed": self.seed,
            "provider": self.provider,
            "provider_asset_id": self.provider_asset_id,
            "width": self.width,
            "height": self.height,
            "run_id": self.run_id,
            "prompt_hash": self.prompt_hash,
            "workflow_hash": self.workflow_hash,
            "qc_report": dict(self.qc_report) if self.qc_report else None,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CharacterDesignCandidate:
        return cls(
            storage_key=data.get("storage_key", ""),
            content_hash=data.get("content_hash", ""),
            seed=int(data.get("seed", -1)),
            provider=data.get("provider", ""),
            provider_asset_id=str(data.get("provider_asset_id", "")),
            width=int(data.get("width", 0)),
            height=int(data.get("height", 0)),
            run_id=data.get("run_id", "legacy"),
            prompt_hash=str(data.get("prompt_hash", "")),
            workflow_hash=str(data.get("workflow_hash", "")),
            qc_report=(
                dict(data["qc_report"])
                if isinstance(data.get("qc_report"), Mapping)
                else None
            ),
        )


@dataclass(frozen=True)
class CharacterDesignCandidatePack:
    schema_version: int
    character_id: str
    brief_hash: str
    candidates: tuple[CharacterDesignCandidate, ...]
    run_id: str

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise PreProductionValidationError(
                "Design candidate pack schema_version must be 1."
            )
        _text(self.character_id, "character_id")
        _text(self.brief_hash, "brief_hash")
        _text(self.run_id, "run_id")
        if not self.candidates:
            raise PreProductionValidationError(
                "Design candidate pack must not be empty."
            )
        if len({candidate.storage_key for candidate in self.candidates}) != len(
            self.candidates
        ):
            raise PreProductionValidationError(
                "Design candidate storage keys must be unique."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "character_id": self.character_id,
            "brief_hash": self.brief_hash,
            "run_id": self.run_id,
            "human_approved": False,
            "next_gate": "HUMAN_CANONICAL_DESIGN_SELECTION",
            "candidates": [candidate.to_dict() for candidate in self.candidates],
        }


@dataclass(frozen=True)
class CharacterAnchorArtifact:
    role: str
    storage_key: str
    content_hash: str
    seed: int
    width: int
    height: int
    provider_asset_id: str
    model_checkpoint: str
    workflow_version: str = "dual-anchor-v1"
    model_hashes: Mapping[str, str] | None = None
    render_duration_sec: float = 0.0
    peak_vram_mb: float | None = None
    prompt_hash: str = ""
    workflow_hash: str = ""

    def __post_init__(self) -> None:
        if self.role not in {"FACE", "FULL_BODY"}:
            raise PreProductionValidationError("Unknown canonical anchor role.")
        for field_name in (
            "storage_key",
            "content_hash",
            "provider_asset_id",
            "model_checkpoint",
            "workflow_version",
        ):
            object.__setattr__(
                self, field_name, _text(getattr(self, field_name), field_name)
            )
        if len(self.content_hash) != 64 or any(
            character not in "0123456789abcdef" for character in self.content_hash
        ):
            raise PreProductionValidationError(
                "Anchor content_hash must be a SHA-256 digest."
            )
        if self.seed < 0 or self.width <= 0 or self.height <= 0:
            raise PreProductionValidationError(
                "Anchor dimensions and seed must be positive."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "storage_key": self.storage_key,
            "content_hash": self.content_hash,
            "seed": self.seed,
            "width": self.width,
            "height": self.height,
            "provider_asset_id": self.provider_asset_id,
            "model_checkpoint": self.model_checkpoint,
            "workflow_version": self.workflow_version,
            "model_hashes": dict(self.model_hashes or {}),
            "render_duration_sec": self.render_duration_sec,
            "peak_vram_mb": self.peak_vram_mb,
            "prompt_hash": self.prompt_hash,
            "workflow_hash": self.workflow_hash,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CharacterAnchorArtifact:
        return cls(
            role=data.get("role", ""),
            storage_key=data.get("storage_key", ""),
            content_hash=data.get("content_hash", ""),
            seed=int(data.get("seed", -1)),
            width=int(data.get("width", 0)),
            height=int(data.get("height", 0)),
            provider_asset_id=str(data.get("provider_asset_id", "")),
            model_checkpoint=data.get("model_checkpoint", ""),
            workflow_version=data.get("workflow_version", "dual-anchor-v1"),
            model_hashes=(
                {str(key): str(value) for key, value in data["model_hashes"].items()}
                if isinstance(data.get("model_hashes"), Mapping)
                else {}
            ),
            render_duration_sec=float(data.get("render_duration_sec", 0.0)),
            peak_vram_mb=(
                float(data["peak_vram_mb"])
                if data.get("peak_vram_mb") is not None
                else None
            ),
            prompt_hash=str(data.get("prompt_hash", "")),
            workflow_hash=str(data.get("workflow_hash", "")),
        )


@dataclass(frozen=True)
class CharacterDualAnchorPack:
    character_id: str
    character_version: int
    brief_hash: str
    canonical_source_key: str
    canonical_source_hash: str
    face_anchor: CharacterAnchorArtifact
    fullbody_anchor: CharacterAnchorArtifact

    def to_dict(self) -> dict[str, Any]:
        return {
            "character_id": self.character_id,
            "character_version": self.character_version,
            "brief_hash": self.brief_hash,
            "canonical_source_key": self.canonical_source_key,
            "canonical_source_hash": self.canonical_source_hash,
            "face_anchor": self.face_anchor.to_dict(),
            "fullbody_anchor": self.fullbody_anchor.to_dict(),
        }


@dataclass(frozen=True)
class CharacterCanonicalApproval:
    schema_version: int
    character_id: str
    character_version: int
    brief_hash: str
    source_candidate_key: str
    canonical_storage_key: str
    canonical_content_hash: str
    provider: str
    provider_asset_id: str
    seed: int
    approved_by: str
    approved_at: datetime
    face_anchor: CharacterAnchorArtifact | None = None
    fullbody_anchor: CharacterAnchorArtifact | None = None
    anchor_provider: str = ""
    anchor_workflow_version: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise PreProductionValidationError(
                "Canonical approval schema_version must be 1."
            )
        if self.character_version < 1 or self.seed < 0:
            raise PreProductionValidationError(
                "Canonical approval version and seed must be positive."
            )
        for field_name in (
            "character_id",
            "brief_hash",
            "source_candidate_key",
            "canonical_storage_key",
            "canonical_content_hash",
            "provider",
            "approved_by",
        ):
            object.__setattr__(
                self, field_name, _text(getattr(self, field_name), field_name)
            )
        if (self.face_anchor is None) != (self.fullbody_anchor is None):
            raise PreProductionValidationError(
                "Canonical approval must contain both anchors or neither."
            )
        if self.face_anchor is not None:
            if self.face_anchor.role != "FACE" or self.fullbody_anchor.role != "FULL_BODY":
                raise PreProductionValidationError(
                    "Canonical approval anchor roles are not correctly assigned."
                )
            object.__setattr__(
                self, "anchor_provider", _text(self.anchor_provider, "anchor_provider")
            )
            object.__setattr__(
                self,
                "anchor_workflow_version",
                _text(self.anchor_workflow_version, "anchor_workflow_version"),
            )

    @property
    def anchors_locked(self) -> bool:
        return self.face_anchor is not None and self.fullbody_anchor is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "character_id": self.character_id,
            "character_version": self.character_version,
            "brief_hash": self.brief_hash,
            "source_candidate_key": self.source_candidate_key,
            "canonical_storage_key": self.canonical_storage_key,
            "canonical_content_hash": self.canonical_content_hash,
            "provider": self.provider,
            "provider_asset_id": self.provider_asset_id,
            "seed": self.seed,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at.isoformat(),
            "anchors_locked": self.anchors_locked,
            "face_anchor": self.face_anchor.to_dict() if self.face_anchor else None,
            "fullbody_anchor": (
                self.fullbody_anchor.to_dict() if self.fullbody_anchor else None
            ),
            "anchor_provider": self.anchor_provider,
            "anchor_workflow_version": self.anchor_workflow_version,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CharacterCanonicalApproval:
        raw_face = data.get("face_anchor")
        raw_fullbody = data.get("fullbody_anchor")
        return cls(
            schema_version=int(data.get("schema_version", 0)),
            character_id=data.get("character_id", ""),
            character_version=int(data.get("character_version", 0)),
            brief_hash=data.get("brief_hash", ""),
            source_candidate_key=data.get("source_candidate_key", ""),
            canonical_storage_key=data.get("canonical_storage_key", ""),
            canonical_content_hash=data.get("canonical_content_hash", ""),
            provider=data.get("provider", ""),
            provider_asset_id=str(data.get("provider_asset_id", "")),
            seed=int(data.get("seed", -1)),
            approved_by=data.get("approved_by", ""),
            approved_at=datetime.fromisoformat(
                _text(data.get("approved_at"), "approved_at")
            ),
            face_anchor=(
                CharacterAnchorArtifact.from_dict(raw_face)
                if isinstance(raw_face, Mapping)
                else None
            ),
            fullbody_anchor=(
                CharacterAnchorArtifact.from_dict(raw_fullbody)
                if isinstance(raw_fullbody, Mapping)
                else None
            ),
            anchor_provider=data.get("anchor_provider", ""),
            anchor_workflow_version=data.get("anchor_workflow_version", ""),
        )


@dataclass(frozen=True)
class CharacterReferenceDraft:
    view: str
    storage_key: str
    content_hash: str
    seed: int
    width: int
    height: int
    conditioning_source_keys: tuple[str, ...] = ()
    conditioning_source_hashes: tuple[str, ...] = ()
    identity_reference_weights: tuple[float, ...] = ()
    provider_asset_id: str = ""
    model_checkpoint: str = ""
    workflow_version: str = "canonical-views-v1"
    qc_report: Mapping[str, Any] | None = None
    prompt_hash: str = ""
    workflow_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "view": self.view,
            "storage_key": self.storage_key,
            "content_hash": self.content_hash,
            "seed": self.seed,
            "width": self.width,
            "height": self.height,
            "conditioning_source_keys": list(self.conditioning_source_keys),
            "conditioning_source_hashes": list(self.conditioning_source_hashes),
            "identity_reference_weights": list(self.identity_reference_weights),
            "provider_asset_id": self.provider_asset_id,
            "model_checkpoint": self.model_checkpoint,
            "workflow_version": self.workflow_version,
            "qc_report": dict(self.qc_report) if self.qc_report else None,
            "prompt_hash": self.prompt_hash,
            "workflow_hash": self.workflow_hash,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CharacterReferenceDraft:
        raw_qc = data.get("qc_report")
        return cls(
            view=data.get("view", ""),
            storage_key=data.get("storage_key", ""),
            content_hash=data.get("content_hash", ""),
            seed=int(data.get("seed", -1)),
            width=int(data.get("width", 0)),
            height=int(data.get("height", 0)),
            conditioning_source_keys=tuple(data.get("conditioning_source_keys", ())),
            conditioning_source_hashes=tuple(
                data.get("conditioning_source_hashes", ())
            ),
            identity_reference_weights=tuple(
                float(value) for value in data.get("identity_reference_weights", ())
            ),
            provider_asset_id=str(data.get("provider_asset_id", "")),
            model_checkpoint=str(data.get("model_checkpoint", "")),
            workflow_version=str(data.get("workflow_version", "canonical-views-v1")),
            qc_report=dict(raw_qc) if isinstance(raw_qc, Mapping) else None,
            prompt_hash=str(data.get("prompt_hash", "")),
            workflow_hash=str(data.get("workflow_hash", "")),
        )


@dataclass(frozen=True)
class CharacterViewQuarantineArtifact:
    view: str
    seed: int
    attempt: int
    image_storage_key: str
    report_storage_key: str
    content_hash: str
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "view": self.view,
            "seed": self.seed,
            "attempt": self.attempt,
            "image_storage_key": self.image_storage_key,
            "report_storage_key": self.report_storage_key,
            "content_hash": self.content_hash,
            "reasons": list(self.reasons),
        }

    @classmethod
    def from_dict(
        cls, data: Mapping[str, Any]
    ) -> CharacterViewQuarantineArtifact:
        return cls(
            view=str(data.get("view", "")),
            seed=int(data.get("seed", -1)),
            attempt=int(data.get("attempt", 0)),
            image_storage_key=str(data.get("image_storage_key", "")),
            report_storage_key=str(data.get("report_storage_key", "")),
            content_hash=str(data.get("content_hash", "")),
            reasons=tuple(str(value) for value in data.get("reasons", ())),
        )


@dataclass(frozen=True)
class CharacterReferenceDraftPack:
    schema_version: int
    character_id: str
    character_version: int
    brief_hash: str
    canonical_storage_key: str
    drafts: tuple[CharacterReferenceDraft, ...]
    status: str = "PENDING_HUMAN_REVIEW"
    quarantined: tuple[CharacterViewQuarantineArtifact, ...] = ()
    contact_sheet_storage_key: str = ""
    contact_sheet_content_hash: str = ""

    def __post_init__(self) -> None:
        expected = {
            "FACE_CLOSEUP",
            "FRONT",
            "PROFILE_LEFT",
            "PROFILE_RIGHT",
            "THREE_QUARTER_LEFT",
            "THREE_QUARTER_RIGHT",
            "BACK",
        }
        actual = {draft.view for draft in self.drafts}
        if self.schema_version != 1 or self.status not in {
            "PENDING_HUMAN_REVIEW",
            "BLOCKED",
        }:
            raise PreProductionValidationError("Invalid reference view-pack state.")
        if self.status == "PENDING_HUMAN_REVIEW" and (
            actual != expected or len(self.drafts) != 7
        ):
            raise PreProductionValidationError(
                "Reference draft pack requires exactly the seven standard views."
            )
        if self.status == "BLOCKED" and actual == expected and len(self.drafts) == 7:
            raise PreProductionValidationError("A complete view pack cannot be blocked.")
        if len(actual) != len(self.drafts):
            raise PreProductionValidationError("Reference view names must be unique.")
        if self.status == "PENDING_HUMAN_REVIEW" and (
            not self.contact_sheet_storage_key or not self.contact_sheet_content_hash
        ):
            raise PreProductionValidationError(
                "A reviewable view pack requires a contact sheet."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "character_id": self.character_id,
            "character_version": self.character_version,
            "brief_hash": self.brief_hash,
            "canonical_storage_key": self.canonical_storage_key,
            "human_approved": False,
            "status": self.status,
            "next_gate": self.status,
            "contact_sheet_storage_key": self.contact_sheet_storage_key,
            "contact_sheet_content_hash": self.contact_sheet_content_hash,
            "quarantined": [item.to_dict() for item in self.quarantined],
            "views": [draft.to_dict() for draft in self.drafts],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CharacterReferenceDraftPack:
        return cls(
            schema_version=int(data.get("schema_version", 0)),
            character_id=str(data.get("character_id", "")),
            character_version=int(data.get("character_version", 0)),
            brief_hash=str(data.get("brief_hash", "")),
            canonical_storage_key=str(data.get("canonical_storage_key", "")),
            drafts=tuple(
                CharacterReferenceDraft.from_dict(item)
                for item in data.get("views", ())
                if isinstance(item, Mapping)
            ),
            status=str(data.get("status", data.get("next_gate", ""))),
            quarantined=tuple(
                CharacterViewQuarantineArtifact.from_dict(item)
                for item in data.get("quarantined", ())
                if isinstance(item, Mapping)
            ),
            contact_sheet_storage_key=str(
                data.get("contact_sheet_storage_key", "")
            ),
            contact_sheet_content_hash=str(
                data.get("contact_sheet_content_hash", "")
            ),
        )


@dataclass(frozen=True)
class CharacterViewPackApproval:
    schema_version: int
    character_id: str
    character_version: int
    brief_hash: str
    approved_by: str
    approved_at: datetime
    contact_sheet_storage_key: str
    contact_sheet_content_hash: str
    view_hashes: Mapping[str, str]
    acceptance_sha256: str = ""
    human_checks: tuple[CharacterHumanCheck, ...] = ()
    verified_evidence: tuple[str, ...] = ()
    automatic_checks_verified: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        expected = {
            "FACE_CLOSEUP",
            "FRONT",
            "PROFILE_LEFT",
            "PROFILE_RIGHT",
            "THREE_QUARTER_LEFT",
            "THREE_QUARTER_RIGHT",
            "BACK",
        }
        if self.schema_version != 1 or set(self.view_hashes) != expected:
            raise PreProductionValidationError(
                "View-pack approval requires hashes for all seven views."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "character_id": self.character_id,
            "character_version": self.character_version,
            "brief_hash": self.brief_hash,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at.isoformat(),
            "human_approved": True,
            "contact_sheet_storage_key": self.contact_sheet_storage_key,
            "contact_sheet_content_hash": self.contact_sheet_content_hash,
            "view_hashes": dict(self.view_hashes),
            "acceptance_sha256": self.acceptance_sha256,
            "human_checks": [check.to_dict() for check in self.human_checks],
            "verified_evidence": list(self.verified_evidence),
            "automatic_checks_verified": list(self.automatic_checks_verified),
            "next_gate": "POSE_PRODUCTION",
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CharacterViewPackApproval:
        raw_hashes = data.get("view_hashes", {})
        if not isinstance(raw_hashes, Mapping):
            raise PreProductionValidationError("view_hashes must be an object.")
        return cls(
            schema_version=int(data.get("schema_version", 0)),
            character_id=str(data.get("character_id", "")),
            character_version=int(data.get("character_version", 0)),
            brief_hash=str(data.get("brief_hash", "")),
            approved_by=str(data.get("approved_by", "")),
            approved_at=datetime.fromisoformat(str(data.get("approved_at", ""))),
            contact_sheet_storage_key=str(
                data.get("contact_sheet_storage_key", "")
            ),
            contact_sheet_content_hash=str(
                data.get("contact_sheet_content_hash", "")
            ),
            view_hashes={str(key): str(value) for key, value in raw_hashes.items()},
            acceptance_sha256=str(data.get("acceptance_sha256", "")),
            human_checks=tuple(
                CharacterHumanCheck.from_dict(item)
                for item in data.get("human_checks", ())
                if isinstance(item, Mapping)
            ),
            verified_evidence=tuple(
                str(item) for item in data.get("verified_evidence", ())
            ),
            automatic_checks_verified=tuple(
                str(item) for item in data.get("automatic_checks_verified", ())
            ),
        )
