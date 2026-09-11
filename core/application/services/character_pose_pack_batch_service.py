"""Resumable batch orchestration for the pre-animation character library."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.application.services.character_pose_pack_service import (
    CharacterPosePackService,
)
from core.application.services.series_style_lock_service import SeriesStyleLockService
from core.domain.value_objects.character_creation_brief import CharacterCreationBrief
from core.domain.value_objects.character_design import CharacterCanonicalApproval
from core.domain.value_objects.style_lock import StyleLockSnapshot


class CharacterPosePackBatchService:
    """Run independent character pose packs without losing completed work.

    Production batches pin one active-series style snapshot at their first
    invocation. The compatibility fallback without a resolver exists only for
    old offline/unit callers and remains DISCOVERY-only.
    """

    def __init__(
        self,
        pose_pack_service: CharacterPosePackService,
        *,
        style_lock_resolver: SeriesStyleLockService | None = None,
    ) -> None:
        self._pose_pack_service = pose_pack_service
        self._style_lock_resolver = style_lock_resolver

    async def run(
        self,
        jobs: list[dict[str, Any]],
        *,
        output_manifest: str | Path,
        continue_on_error: bool = True,
        active_series_path: str | Path | None = None,
        workflow_path: str | Path | None = None,
    ) -> dict[str, Any]:
        target = Path(output_manifest)
        existing = self._load_existing(target)
        pinned_snapshot = self._load_snapshot(existing)
        production = (
            pinned_snapshot is not None
            or self._style_lock_resolver is not None
            or active_series_path is not None
        )
        if production:
            if (
                self._style_lock_resolver is None
                or active_series_path is None
                or workflow_path is None
            ):
                raise ValueError(
                    "Production batch requires an active style-lock resolver and workflow."
                )
            resolved_snapshot = self._style_lock_resolver.resolve_production(
                active_series_path,
                workflow_path=workflow_path,
            )
            if pinned_snapshot is not None and pinned_snapshot != resolved_snapshot:
                raise ValueError(
                    "Existing batch style-lock snapshot no longer matches the active production lock."
                )
            pinned_snapshot = resolved_snapshot
        by_character = {
            str(item.get("character_id")): dict(item)
            for item in existing.get("characters", [])
            if isinstance(item, dict) and item.get("character_id")
        }
        batch_id = str(existing.get("batch_id") or self._batch_id(jobs))
        for job in jobs:
            character_id = str(job.get("character_id", "")).strip()
            if not character_id:
                raise ValueError("Every pose-pack batch job requires character_id.")
            try:
                brief = self._load_brief(job["brief"])
                approval = self._load_approval(job["approval"])
                if brief.character_id != character_id:
                    raise ValueError("Batch job character_id does not match its brief.")
                if production:
                    manifest = await self._pose_pack_service.generate_pack(
                        brief,
                        approval,
                        mode="PRODUCTION",
                        production_snapshot=pinned_snapshot,
                        active_series_path=active_series_path,
                        output_prefix=str(job.get("output_prefix", "characters")),
                        run_id=str(job.get("run_id", batch_id)),
                    )
                else:
                    manifest = await self._pose_pack_service.generate_pack(
                        brief,
                        approval,
                        mode="DISCOVERY",
                        style_id=str(job["style_id"]),
                        style_reference_path=str(job["style_reference"]),
                        output_prefix=str(job.get("output_prefix", "characters")),
                        run_id=str(job.get("run_id", batch_id)),
                    )
                by_character[character_id] = {
                    "character_id": character_id,
                    "version": approval.character_version,
                    "status": manifest.status,
                    "complete": manifest.complete,
                    "manifest_storage_key": manifest.manifest_storage_key,
                    "contact_sheet_storage_key": manifest.contact_sheet_storage_key,
                    "pose_count": len(manifest.poses),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            except Exception as error:
                by_character[character_id] = {
                    "character_id": character_id,
                    "status": "FAILED",
                    "complete": False,
                    "error": str(error),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
                if not continue_on_error:
                    self._write(target, batch_id, by_character, pinned_snapshot)
                    raise
            self._write(target, batch_id, by_character, pinned_snapshot)
        payload = {
            "schema_version": 1,
            "batch_id": batch_id,
            "status": self._batch_status(by_character, len(jobs)),
            "artifact_mode": "PRODUCTION" if production else "DISCOVERY",
            "production_eligible": bool(production and pinned_snapshot),
            "style_lock_snapshot": pinned_snapshot.to_dict() if pinned_snapshot else {},
            "character_count": len(jobs),
            "complete_count": sum(
                item.get("status") == "PENDING_HUMAN_REVIEW"
                for item in by_character.values()
            ),
            "characters": list(by_character.values()),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self._write_payload(target, payload)
        return payload

    @staticmethod
    def _load_snapshot(payload: dict[str, Any]) -> StyleLockSnapshot | None:
        raw = payload.get("style_lock_snapshot")
        if not isinstance(raw, dict) or not raw:
            return None
        return StyleLockSnapshot(
            series_id=str(raw.get("series_id", "")),
            style_id=str(raw.get("style_id", "")),
            style_version=int(raw.get("style_version", 0)),
            style_approval_receipt_sha256=str(raw.get("style_approval_receipt_sha256", "")),
            production_lock_digest=str(raw.get("production_lock_digest", "")),
            reference_sha256=str(raw.get("reference_sha256", "")),
            style_bible_sha256=str(raw.get("style_bible_sha256", "")),
            source=str(raw.get("source", "")),
            reference_asset=str(raw.get("reference_asset", "")),
        )

    @staticmethod
    def _load_brief(path: str | Path) -> CharacterCreationBrief:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise TypeError("Batch brief must contain an object.")
        return CharacterCreationBrief.from_dict(raw.get("character_creation_brief", raw))

    @staticmethod
    def _load_approval(path: str | Path) -> CharacterCanonicalApproval:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise TypeError("Batch approval must contain an object.")
        return CharacterCanonicalApproval.from_dict(raw)

    @staticmethod
    def _load_existing(path: Path) -> dict[str, Any]:
        if not path.is_file():
            return {}
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or int(raw.get("schema_version", 0)) != 1:
            raise ValueError("Existing pose-pack batch manifest is malformed.")
        return raw

    @staticmethod
    def _batch_id(jobs: list[dict[str, Any]]) -> str:
        payload = json.dumps(jobs, ensure_ascii=False, sort_keys=True).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()[:16]

    @staticmethod
    def _batch_status(characters: dict[str, dict[str, Any]], expected: int) -> str:
        if len(characters) < expected:
            return "IN_PROGRESS"
        statuses = {str(item.get("status")) for item in characters.values()}
        if statuses and statuses <= {"PENDING_HUMAN_REVIEW"}:
            return "PENDING_HUMAN_REVIEW"
        if "FAILED" in statuses:
            return "PARTIAL_FAILURE"
        return "IN_PROGRESS"

    @staticmethod
    def _write(
        path: Path,
        batch_id: str,
        characters: dict[str, dict[str, Any]],
        snapshot: StyleLockSnapshot | None,
    ) -> None:
        payload = {
            "schema_version": 1,
            "batch_id": batch_id,
            "status": "IN_PROGRESS",
            "artifact_mode": "PRODUCTION" if snapshot else "DISCOVERY",
            "production_eligible": bool(snapshot),
            "style_lock_snapshot": snapshot.to_dict() if snapshot else {},
            "character_count": len(characters),
            "characters": list(characters.values()),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        CharacterPosePackBatchService._write_payload(path, payload)

    @staticmethod
    def _write_payload(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
