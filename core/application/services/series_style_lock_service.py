"""Authoritative resolver and receipt operations for production style locks."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from core.application.services.model_lock_service import (
    load_model_lock,
    verify_model_lock,
)
from core.domain.exceptions import StyleLockError
from core.domain.value_objects.series_project import SeriesProject
from core.domain.value_objects.style_lock import (
    DISCOVERY,
    LOCK_COMPATIBLE,
    LOCK_PENDING_SMOKE,
    PRODUCTION,
    ProductionStyleLock,
    StyleApprovalReceipt,
    StyleLockSnapshot,
    canonical_style_hash,
)


class SeriesStyleLockService:
    """Resolve, create, and verify the two independent style lock receipts."""

    def __init__(self, workspace_root: str | Path) -> None:
        self._workspace_root = Path(workspace_root).resolve()

    def resolve_production(
        self,
        project_path: str | Path,
        *,
        workflow_path: str | Path,
    ) -> StyleLockSnapshot:
        """Resolve the active series style or fail before any render is queued."""
        project_file = self._inside_workspace(project_path)
        try:
            raw_project = json.loads(project_file.read_text(encoding="utf-8"))
            project = SeriesProject.from_dict(raw_project)
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
            raise StyleLockError("STYLE_LOCK_MISSING", "Active series manifest is unavailable or invalid.") from error

        style = project.style_bible
        if style.status != "APPROVED":
            raise StyleLockError(
                "STYLE_LOCK_UNAPPROVED",
                f"Series style '{style.style_id}' is {style.status}, not APPROVED.",
            )
        if not project.style_approval_receipt or not project.production_style_lock:
            raise StyleLockError(
                "STYLE_LOCK_MISSING",
                "Active series does not reference both style approval and production lock receipts.",
            )

        style_path = self._inside_workspace(style.reference_asset)
        actual_reference_hash = self._hash_file(style_path, "STYLE_LOCK_TAMPERED")
        if actual_reference_hash != style.reference_sha256:
            raise StyleLockError("STYLE_LOCK_TAMPERED", "Style reference hash does not match the active series.")

        style_payload_hash = canonical_style_hash(style.to_dict())
        approval_path = self._inside_workspace(project.style_approval_receipt)
        approval_bytes = self._read_file(approval_path, "STYLE_LOCK_MISSING")
        try:
            approval = StyleApprovalReceipt.from_dict(json.loads(approval_bytes.decode("utf-8")))
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            raise StyleLockError("STYLE_LOCK_TAMPERED", "Style approval receipt is invalid.") from error
        approval_digest = hashlib.sha256(approval_bytes).hexdigest()
        if (
            approval.series_id != project.series_id
            or approval.style_id != style.style_id
            or approval.style_version != style.style_version
            or approval.reference_sha256 != actual_reference_hash
            or approval.style_bible_sha256 != style_payload_hash
            or approval.artifact_mode != DISCOVERY
        ):
            raise StyleLockError("STYLE_LOCK_TAMPERED", "Style approval receipt does not match the active style.")

        lock_path = self._inside_workspace(project.production_style_lock)
        lock_bytes = self._read_file(lock_path, "STYLE_LOCK_MISSING")
        try:
            lock = ProductionStyleLock.from_dict(json.loads(lock_bytes.decode("utf-8")))
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            raise StyleLockError("STYLE_LOCK_TAMPERED", "Production style lock is invalid.") from error
        if not lock.production_eligible or lock.compatibility_status != LOCK_COMPATIBLE:
            raise StyleLockError("STYLE_LOCK_UNAPPROVED", "Production style lock has not passed technical compatibility.")
        if (
            lock.series_id != project.series_id
            or lock.style_id != style.style_id
            or lock.style_version != style.style_version
            or lock.style_approval_receipt_sha256 != approval_digest
        ):
            raise StyleLockError("STYLE_LOCK_TAMPERED", "Production style lock does not match the active style approval.")

        model_lock_path = self._inside_workspace(project.model_lock)
        model_lock_bytes = self._read_file(model_lock_path, "STYLE_LOCK_MISSING")
        if hashlib.sha256(model_lock_bytes).hexdigest() != lock.model_lock_sha256:
            raise StyleLockError("STYLE_LOCK_TAMPERED", "Production lock points to a different model lock.")
        model_lock = load_model_lock(model_lock_path)
        current_model_hashes = {entry.role: entry.sha256 for entry in model_lock.entries}
        if dict(lock.model_hashes) != current_model_hashes:
            raise StyleLockError("STYLE_LOCK_STALE", "Production model hashes no longer match models.lock.json.")
        model_checks = verify_model_lock(model_lock)
        if any(not check.passed and not check.warning for check in model_checks):
            raise StyleLockError("STYLE_LOCK_STALE", "A locked production model is missing or changed on disk.")

        workflow_file = self._inside_workspace(workflow_path)
        actual_workflow_hash = self._hash_file(workflow_file, "STYLE_LOCK_MISSING")
        if actual_workflow_hash != lock.workflow_sha256:
            raise StyleLockError("STYLE_LOCK_STALE", "Production workflow changed after the lock was created.")

        return StyleLockSnapshot(
            series_id=project.series_id,
            style_id=style.style_id,
            style_version=style.style_version,
            style_approval_receipt_sha256=approval_digest,
            production_lock_digest=lock.digest,
            reference_sha256=actual_reference_hash,
            style_bible_sha256=style_payload_hash,
            reference_asset=style.reference_asset,
        )

    def create_style_approval(
        self,
        project_path: str | Path,
        *,
        approved_by: str,
        approval_criteria: tuple[str, ...],
    ) -> StyleApprovalReceipt:
        """Create the creative receipt only after an explicit human action."""
        project_file = self._inside_workspace(project_path)
        raw = json.loads(project_file.read_text(encoding="utf-8"))
        project = SeriesProject.from_dict(raw)
        style = project.style_bible
        if not approval_criteria:
            raise StyleLockError("STYLE_LOCK_UNAPPROVED", "At least one creative approval criterion is required.")
        reference_hash = self._hash_file(self._inside_workspace(style.reference_asset), "STYLE_LOCK_TAMPERED")
        if reference_hash != style.reference_sha256:
            raise StyleLockError("STYLE_LOCK_TAMPERED", "Style reference hash does not match the style bible.")
        return StyleApprovalReceipt(
            schema_version=1,
            artifact_mode=DISCOVERY,
            series_id=project.series_id,
            style_id=style.style_id,
            style_version=style.style_version,
            reference_sha256=reference_hash,
            style_bible_sha256=canonical_style_hash(style.to_dict()),
            approval_status="APPROVED",
            approval_criteria=tuple(approval_criteria),
            approved_by=approved_by,
            approved_at=datetime.now(timezone.utc),
            receipt_storage_key=project.style_approval_receipt,
        )

    def create_production_lock(
        self,
        project_path: str | Path,
        *,
        workflow_path: str | Path,
        style_approval_receipt_sha256: str,
        width: int,
        height: int,
        sampler: str,
        steps: int,
        cfg: float,
        denoise: float,
        lock_version: int = 1,
    ) -> ProductionStyleLock:
        """Create a pending technical lock bound to the creative receipt."""
        project_file = self._inside_workspace(project_path)
        project = SeriesProject.from_dict(
            json.loads(project_file.read_text(encoding="utf-8"))
        )
        approval_path = self._inside_workspace(project.style_approval_receipt)
        approval_bytes = self._read_file(approval_path, "STYLE_LOCK_MISSING")
        actual_approval_digest = hashlib.sha256(approval_bytes).hexdigest()
        if actual_approval_digest != style_approval_receipt_sha256:
            raise StyleLockError(
                "STYLE_LOCK_TAMPERED",
                "Production lock must reference the active style approval receipt.",
            )
        approval = StyleApprovalReceipt.from_dict(
            json.loads(approval_bytes.decode("utf-8"))
        )
        if (
            approval.series_id != project.series_id
            or approval.style_id != project.style_bible.style_id
            or approval.style_version != project.style_bible.style_version
            or approval.reference_sha256 != project.style_bible.reference_sha256
            or approval.style_bible_sha256 != canonical_style_hash(project.style_bible.to_dict())
            or approval.artifact_mode != DISCOVERY
        ):
            raise StyleLockError(
                "STYLE_LOCK_TAMPERED",
                "Style approval receipt does not match the active series style.",
            )
        model_lock_path = self._inside_workspace(project.model_lock)
        model_lock_bytes = self._read_file(model_lock_path, "STYLE_LOCK_MISSING")
        model_lock = load_model_lock(model_lock_path)
        workflow_file = self._inside_workspace(workflow_path)
        workflow_bytes = self._read_file(workflow_file, "STYLE_LOCK_MISSING")
        return ProductionStyleLock(
            schema_version=1,
            artifact_mode=PRODUCTION,
            series_id=project.series_id,
            style_id=project.style_bible.style_id,
            style_version=project.style_bible.style_version,
            style_approval_receipt_sha256=style_approval_receipt_sha256,
            model_lock_sha256=hashlib.sha256(model_lock_bytes).hexdigest(),
            model_hashes={entry.role: entry.sha256 for entry in model_lock.entries},
            workflow_id=workflow_file.name,
            workflow_sha256=hashlib.sha256(workflow_bytes).hexdigest(),
            component_hashes={
                entry.role: entry.sha256
                for entry in model_lock.entries
                if entry.role != "checkpoint"
            },
            width=width,
            height=height,
            sampler=sampler,
            steps=steps,
            cfg=cfg,
            denoise=denoise,
            lock_version=lock_version,
            compatibility_status=LOCK_PENDING_SMOKE,
            production_eligible=False,
            lock_storage_key=project.production_style_lock,
        )

    def write_style_approval(
        self,
        project_path: str | Path,
        *,
        approved_by: str,
        approval_criteria: tuple[str, ...],
    ) -> StyleApprovalReceipt:
        """Create and persist a creative receipt without promoting production."""
        project_file = self._inside_workspace(project_path)
        project = SeriesProject.from_dict(
            json.loads(project_file.read_text(encoding="utf-8"))
        )
        receipt = self.create_style_approval(
            project_path,
            approved_by=approved_by,
            approval_criteria=approval_criteria,
        )
        target = self._inside_workspace(project.style_approval_receipt)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            existing_bytes = self._read_file(target, "STYLE_LOCK_TAMPERED")
            try:
                existing = StyleApprovalReceipt.from_dict(
                    json.loads(existing_bytes.decode("utf-8"))
                )
            except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as error:
                raise StyleLockError(
                    "STYLE_LOCK_TAMPERED",
                    "Existing style approval receipt is invalid.",
                ) from error
            existing_payload = existing.to_dict()
            receipt_payload = receipt.to_dict()
            # ``approved_at`` is evidence created by the first successful
            # invocation, not a caller-controlled decision input. Repeating
            # the same command must return that immutable receipt rather than
            # fail only because the current clock moved forward.
            existing_payload.pop("approved_at", None)
            receipt_payload.pop("approved_at", None)
            if existing_payload != receipt_payload:
                raise StyleLockError(
                    "STYLE_LOCK_TAMPERED",
                    "Style approval receipt is immutable and already contains different evidence.",
                )
            return existing
        target.write_text(
            json.dumps(receipt.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        return receipt

    def promote_style(self, project_path: str | Path) -> StyleApprovalReceipt:
        """Promote an already persisted creative receipt to active APPROVED style."""
        project_file = self._inside_workspace(project_path)
        raw_project = json.loads(project_file.read_text(encoding="utf-8"))
        project = SeriesProject.from_dict(raw_project)
        if not project.style_approval_receipt:
            raise StyleLockError("STYLE_LOCK_MISSING", "Style approval receipt path is missing.")
        receipt_path = self._inside_workspace(project.style_approval_receipt)
        receipt_bytes = self._read_file(receipt_path, "STYLE_LOCK_MISSING")
        receipt = StyleApprovalReceipt.from_dict(
            json.loads(receipt_bytes.decode("utf-8"))
        )
        expected_hash = canonical_style_hash(project.style_bible.to_dict())
        if (
            receipt.series_id != project.series_id
            or receipt.style_id != project.style_bible.style_id
            or receipt.style_version != project.style_bible.style_version
            or receipt.reference_sha256 != project.style_bible.reference_sha256
            or receipt.style_bible_sha256 != expected_hash
        ):
            raise StyleLockError("STYLE_LOCK_TAMPERED", "Style approval receipt does not match the active style.")
        updated = dict(raw_project)
        style = dict(updated["style_bible"])
        style["status"] = "APPROVED"
        updated["style_bible"] = style
        project_file.write_text(
            json.dumps(updated, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return receipt

    def write_production_lock(
        self,
        project_path: str | Path,
        *,
        workflow_path: str | Path,
        style_approval_receipt_sha256: str,
        width: int,
        height: int,
        sampler: str,
        steps: int,
        cfg: float,
        denoise: float,
        lock_version: int = 1,
    ) -> ProductionStyleLock:
        """Persist a pending technical lock bound to the creative receipt."""
        project_file = self._inside_workspace(project_path)
        project = SeriesProject.from_dict(
            json.loads(project_file.read_text(encoding="utf-8"))
        )
        if project.style_bible.status != "APPROVED":
            raise StyleLockError("STYLE_LOCK_UNAPPROVED", "Promote the creative style approval before creating a production lock.")
        lock = self.create_production_lock(
            project_path,
            workflow_path=workflow_path,
            style_approval_receipt_sha256=style_approval_receipt_sha256,
            width=width,
            height=height,
            sampler=sampler,
            steps=steps,
            cfg=cfg,
            denoise=denoise,
            lock_version=lock_version,
        )
        target = self._inside_workspace(project.production_style_lock)
        target.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(lock.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if target.exists():
            existing_bytes = self._read_file(target, "STYLE_LOCK_TAMPERED")
            try:
                existing = ProductionStyleLock.from_dict(
                    json.loads(existing_bytes.decode("utf-8"))
                )
            except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
                raise StyleLockError(
                    "STYLE_LOCK_TAMPERED",
                    "Existing production style lock is invalid.",
                ) from error
            if existing.to_dict() != lock.to_dict():
                raise StyleLockError(
                    "STYLE_LOCK_TAMPERED",
                    "Production style lock is immutable and already contains different evidence.",
                )
            return existing
        target.write_text(serialized, encoding="utf-8")
        return lock

    def mark_production_compatible(
        self,
        project_path: str | Path,
        *,
        smoke_test_receipt_path: str | Path,
    ) -> ProductionStyleLock:
        """Attach hash evidence from a real smoke receipt and enable production."""
        project_file = self._inside_workspace(project_path)
        project = SeriesProject.from_dict(
            json.loads(project_file.read_text(encoding="utf-8"))
        )
        lock_path = self._inside_workspace(project.production_style_lock)
        lock = ProductionStyleLock.from_dict(
            json.loads(self._read_file(lock_path, "STYLE_LOCK_MISSING").decode("utf-8"))
        )
        smoke_path = self._inside_workspace(smoke_test_receipt_path)
        smoke_bytes = self._read_file(smoke_path, "STYLE_LOCK_MISSING")
        try:
            smoke_payload = json.loads(smoke_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as error:
            raise StyleLockError(
                "STYLE_LOCK_TAMPERED",
                "Smoke-test evidence must be a valid JSON receipt.",
            ) from error
        if not isinstance(smoke_payload, dict):
            raise StyleLockError(
                "STYLE_LOCK_TAMPERED",
                "Smoke-test evidence must contain a JSON object.",
            )
        status = str(smoke_payload.get("status", "")).upper()
        passed = smoke_payload.get("passed") is True
        if status not in {"PASSED", "SUCCESS", "PRODUCTION_COMPATIBLE"} and not passed:
            raise StyleLockError(
                "STYLE_LOCK_UNAPPROVED",
                "Smoke-test receipt does not prove a successful technical run.",
            )
        expected_lock_digest = lock.digest
        smoke_lock_digest = str(smoke_payload.get("production_lock_digest", ""))
        if smoke_lock_digest != expected_lock_digest:
            raise StyleLockError(
                "STYLE_LOCK_TAMPERED",
                "Smoke-test receipt is not bound to the pending production lock digest.",
            )
        smoke_hash = hashlib.sha256(smoke_bytes).hexdigest()
        data = lock.to_dict()
        data.pop("artifact_type", None)
        data["compatibility_status"] = LOCK_COMPATIBLE
        data["production_eligible"] = True
        data["smoke_test_receipt_sha256"] = smoke_hash
        updated = ProductionStyleLock.from_dict(data)
        lock_path.write_text(
            json.dumps(updated.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return updated

    @property
    def workspace_root(self) -> Path:
        return self._workspace_root

    def _inside_workspace(self, path: str | Path) -> Path:
        candidate = Path(path)
        resolved = (candidate if candidate.is_absolute() else self._workspace_root / candidate).resolve()
        try:
            resolved.relative_to(self._workspace_root)
        except ValueError as error:
            raise StyleLockError("STYLE_LOCK_TAMPERED", "Style lock path leaves the workspace.") from error
        return resolved

    @staticmethod
    def _read_file(path: Path, reason: str) -> bytes:
        try:
            return path.read_bytes()
        except OSError as error:
            raise StyleLockError(reason, f"Required style-lock file is unavailable: {path}") from error

    @classmethod
    def _hash_file(cls, path: Path, reason: str) -> str:
        return hashlib.sha256(cls._read_file(path, reason)).hexdigest()


__all__ = ["SeriesStyleLockService"]
