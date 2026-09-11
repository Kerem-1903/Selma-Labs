"""Durable review evidence for one start/end keyframe pair."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any

from core.domain.exceptions import PreProductionValidationError

_PAIR_CHECKS = (
    "identity_consistent",
    "outfit_consistent",
    "start_pose_matches",
    "end_pose_matches",
    "start_end_continuity",
)
_PAIR_STATUSES = {"PENDING_HUMAN_REVIEW", "BLOCKED"}


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
class KeyframePairFrameEvidence:
    label: str
    storage_key: str
    content_hash: str
    pose_storage_key: str
    pose_content_hash: str
    seed: int
    width: int
    height: int
    reference_asset_ids: tuple[str, ...] = ()
    reference_hashes: tuple[str, ...] = ()
    qc_report: Mapping[str, Any] | None = None
    prompt_hash: str = ""
    workflow_hash: str = ""
    model_hashes: Mapping[str, str] | None = None

    def __post_init__(self) -> None:
        if self.label not in {"start", "end"}:
            raise PreProductionValidationError("Pair frame label must be start or end.")
        object.__setattr__(self, "storage_key", _key(self.storage_key, "storage_key"))
        object.__setattr__(self, "pose_storage_key", _key(self.pose_storage_key, "pose_storage_key"))
        object.__setattr__(self, "content_hash", _hash(self.content_hash, "content_hash"))
        object.__setattr__(self, "pose_content_hash", _hash(self.pose_content_hash, "pose_content_hash"))
        if self.seed < 0 or self.width <= 0 or self.height <= 0:
            raise PreProductionValidationError("Pair frame dimensions and seed must be positive.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "storage_key": self.storage_key,
            "content_hash": self.content_hash,
            "pose_storage_key": self.pose_storage_key,
            "pose_content_hash": self.pose_content_hash,
            "seed": self.seed,
            "width": self.width,
            "height": self.height,
            "reference_asset_ids": list(self.reference_asset_ids),
            "reference_hashes": list(self.reference_hashes),
            "qc_report": dict(self.qc_report or {}),
            "prompt_hash": self.prompt_hash,
            "workflow_hash": self.workflow_hash,
            "model_hashes": dict(self.model_hashes or {}),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> KeyframePairFrameEvidence:
        raw_qc = data.get("qc_report", {})
        return cls(
            label=str(data.get("label", "")),
            storage_key=str(data.get("storage_key", "")),
            content_hash=str(data.get("content_hash", "")),
            pose_storage_key=str(data.get("pose_storage_key", "")),
            pose_content_hash=str(data.get("pose_content_hash", "")),
            seed=int(data.get("seed", -1)),
            width=int(data.get("width", 0)),
            height=int(data.get("height", 0)),
            reference_asset_ids=tuple(str(item) for item in data.get("reference_asset_ids", ())),
            reference_hashes=tuple(str(item) for item in data.get("reference_hashes", ())),
            qc_report=dict(raw_qc) if isinstance(raw_qc, Mapping) else {},
            prompt_hash=str(data.get("prompt_hash", "")),
            workflow_hash=str(data.get("workflow_hash", "")),
            model_hashes=(
                {str(key): str(value) for key, value in data["model_hashes"].items()}
                if isinstance(data.get("model_hashes"), Mapping)
                else {}
            ),
        )


@dataclass(frozen=True)
class KeyframePairManifest:
    schema_version: int
    shot_id: str
    character_id: str
    character_version: int
    prompt_start: str
    prompt_end: str
    start_pose_reference_key: str
    end_pose_reference_key: str
    frames: tuple[KeyframePairFrameEvidence, ...]
    status: str = "PENDING_HUMAN_REVIEW"
    contact_sheet_storage_key: str = ""
    contact_sheet_content_hash: str = ""
    quarantined: tuple[Mapping[str, Any], ...] = ()

    def __post_init__(self) -> None:
        if self.schema_version != 1 or self.status not in _PAIR_STATUSES:
            raise PreProductionValidationError("Invalid keyframe pair manifest state.")
        object.__setattr__(self, "shot_id", _text(self.shot_id, "shot_id"))
        object.__setattr__(self, "character_id", _text(self.character_id, "character_id"))
        object.__setattr__(self, "prompt_start", _text(self.prompt_start, "prompt_start"))
        object.__setattr__(self, "prompt_end", _text(self.prompt_end, "prompt_end"))
        object.__setattr__(self, "start_pose_reference_key", _key(self.start_pose_reference_key, "start_pose_reference_key"))
        object.__setattr__(self, "end_pose_reference_key", _key(self.end_pose_reference_key, "end_pose_reference_key"))
        if self.start_pose_reference_key == self.end_pose_reference_key:
            raise PreProductionValidationError("Pair pose references must differ.")
        labels = {frame.label for frame in self.frames}
        if self.status == "PENDING_HUMAN_REVIEW" and (
            labels != {"start", "end"} or len(self.frames) != 2
        ):
            raise PreProductionValidationError(
                "A reviewable pair requires exactly one start and one end evidence."
            )
        if self.status == "PENDING_HUMAN_REVIEW":
            if not self.contact_sheet_storage_key or not self.contact_sheet_content_hash:
                raise PreProductionValidationError("A reviewable pair requires a contact sheet.")
            object.__setattr__(self, "contact_sheet_storage_key", _key(self.contact_sheet_storage_key, "contact_sheet_storage_key"))
            object.__setattr__(self, "contact_sheet_content_hash", _hash(self.contact_sheet_content_hash, "contact_sheet_content_hash"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "shot_id": self.shot_id,
            "character_id": self.character_id,
            "character_version": self.character_version,
            "prompt_start": self.prompt_start,
            "prompt_end": self.prompt_end,
            "start_pose_reference_key": self.start_pose_reference_key,
            "end_pose_reference_key": self.end_pose_reference_key,
            "frames": [frame.to_dict() for frame in self.frames],
            "status": self.status,
            "next_gate": "HUMAN_KEYFRAME_PAIR_APPROVAL" if self.status == "PENDING_HUMAN_REVIEW" else "PAIR_REGENERATION",
            "contact_sheet_storage_key": self.contact_sheet_storage_key,
            "contact_sheet_content_hash": self.contact_sheet_content_hash,
            "quarantined": [dict(item) for item in self.quarantined],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> KeyframePairManifest:
        return cls(
            schema_version=int(data.get("schema_version", 0)),
            shot_id=str(data.get("shot_id", "")),
            character_id=str(data.get("character_id", "")),
            character_version=int(data.get("character_version", 0)),
            prompt_start=str(data.get("prompt_start", "")),
            prompt_end=str(data.get("prompt_end", "")),
            start_pose_reference_key=str(data.get("start_pose_reference_key", "")),
            end_pose_reference_key=str(data.get("end_pose_reference_key", "")),
            frames=tuple(
                KeyframePairFrameEvidence.from_dict(item)
                for item in data.get("frames", ())
                if isinstance(item, Mapping)
            ),
            status=str(data.get("status", "")),
            contact_sheet_storage_key=str(data.get("contact_sheet_storage_key", "")),
            contact_sheet_content_hash=str(data.get("contact_sheet_content_hash", "")),
            quarantined=tuple(
                dict(item) for item in data.get("quarantined", ()) if isinstance(item, Mapping)
            ),
        )


@dataclass(frozen=True)
class KeyframePairApproval:
    schema_version: int
    shot_id: str
    character_id: str
    character_version: int
    approved_by: str
    approved_at: datetime
    manifest_storage_key: str
    manifest_content_hash: str
    contact_sheet_content_hash: str
    frame_hashes: Mapping[str, str]
    confirmed_checks: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise PreProductionValidationError("Keyframe pair approval schema_version must be 1.")
        object.__setattr__(self, "shot_id", _text(self.shot_id, "shot_id"))
        object.__setattr__(self, "character_id", _text(self.character_id, "character_id"))
        object.__setattr__(self, "approved_by", _text(self.approved_by, "approved_by"))
        object.__setattr__(self, "manifest_storage_key", _key(self.manifest_storage_key, "manifest_storage_key"))
        object.__setattr__(self, "manifest_content_hash", _hash(self.manifest_content_hash, "manifest_content_hash"))
        object.__setattr__(self, "contact_sheet_content_hash", _hash(self.contact_sheet_content_hash, "contact_sheet_content_hash"))
        if set(self.frame_hashes) != {"start", "end"}:
            raise PreProductionValidationError("Pair approval requires start and end frame hashes.")
        for label, digest in self.frame_hashes.items():
            _hash(digest, f"{label}_frame_hash")
        if set(self.confirmed_checks) != set(_PAIR_CHECKS):
            raise PreProductionValidationError("Pair approval requires every human check.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "shot_id": self.shot_id,
            "character_id": self.character_id,
            "character_version": self.character_version,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at.isoformat(),
            "human_approved": True,
            "manifest_storage_key": self.manifest_storage_key,
            "manifest_content_hash": self.manifest_content_hash,
            "contact_sheet_content_hash": self.contact_sheet_content_hash,
            "frame_hashes": dict(self.frame_hashes),
            "confirmed_checks": list(self.confirmed_checks),
            "next_gate": "ANIMATION_PRODUCTION",
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> KeyframePairApproval:
        raw_frames = data.get("frame_hashes", {})
        return cls(
            schema_version=int(data.get("schema_version", 0)),
            shot_id=str(data.get("shot_id", "")),
            character_id=str(data.get("character_id", "")),
            character_version=int(data.get("character_version", 0)),
            approved_by=str(data.get("approved_by", "")),
            approved_at=datetime.fromisoformat(str(data.get("approved_at", ""))),
            manifest_storage_key=str(data.get("manifest_storage_key", "")),
            manifest_content_hash=str(data.get("manifest_content_hash", "")),
            contact_sheet_content_hash=str(data.get("contact_sheet_content_hash", "")),
            frame_hashes={str(key): str(value) for key, value in raw_frames.items()} if isinstance(raw_frames, Mapping) else {},
            confirmed_checks=tuple(str(item) for item in data.get("confirmed_checks", ())),
        )


PAIR_HUMAN_CHECKS = _PAIR_CHECKS
