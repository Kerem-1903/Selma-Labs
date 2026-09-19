"""Human approval and hash verification for canonical character view packs."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Collection
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from core.application.services.character_pack_rejection_store import (
    load_rejection,
    record_rejection,
)
from core.domain.exceptions import StorageError
from core.domain.ports.storage_port import StoragePort
from core.domain.value_objects.character_acceptance import CharacterAcceptanceList
from core.domain.value_objects.character_design import (
    CharacterReferenceDraftPack,
    CharacterViewPackApproval,
)
from core.domain.value_objects.character_pack_rejection import (
    REJECTION_SCHEMA_VERSION,
    CharacterPackRejection,
)


async def _single_chunk(data: bytes):
    yield data


class CharacterViewPackApprovalService:
    """Own signed acceptance, provenance checks, and downstream approval guards."""

    _DEFAULT_ACCEPTANCE_DIR = (
        Path(__file__).resolve().parents[3] / "config" / "character_acceptance"
    )

    def __init__(
        self,
        storage: StoragePort,
        *,
        acceptance_dir: Path | str | None = None,
    ) -> None:
        self._storage = storage
        self._acceptance_dir = Path(acceptance_dir) if acceptance_dir is not None else None

    async def approve_view_pack(
        self,
        *,
        character_id: str,
        character_version: int,
        approved_by: str,
        output_prefix: str = "characters",
        acceptance_path: str | Path | None = None,
        confirmed_checks: Collection[str] = (),
    ) -> CharacterViewPackApproval:
        if character_version < 1:
            raise ValueError("Character version must be positive.")
        root = self._root(output_prefix, character_id, character_version)
        await self._refuse_rejected_view_pack(root)
        manifest_key = f"{root}/view-pack.json"
        if not await self._storage.exists(manifest_key):
            raise StorageError(f"View-pack manifest '{manifest_key}' was not found.")
        raw_pack = json.loads((await self._storage.load(manifest_key)).decode("utf-8"))
        if not isinstance(raw_pack, dict):
            raise TypeError("View-pack manifest must contain an object.")
        pack = CharacterReferenceDraftPack.from_dict(raw_pack)
        if pack.character_id != character_id or pack.character_version != character_version:
            raise ValueError("View-pack identity does not match the approval request.")
        if pack.status != "PENDING_HUMAN_REVIEW":
            raise ValueError("Only a complete QC-passed view pack can be approved.")
        for draft in pack.drafts:
            image_bytes = await self._storage.load(draft.storage_key)
            if hashlib.sha256(image_bytes).hexdigest() != draft.content_hash:
                raise ValueError(f"View '{draft.view}' changed before human approval.")
            if not draft.qc_report or not bool(draft.qc_report.get("passed")):
                raise ValueError(f"View '{draft.view}' has no passing QC evidence.")
        contact_bytes = await self._storage.load(pack.contact_sheet_storage_key)
        if hashlib.sha256(contact_bytes).hexdigest() != pack.contact_sheet_content_hash:
            raise ValueError("Contact sheet changed before human approval.")

        source = (
            Path(acceptance_path)
            if acceptance_path is not None
            else (self._acceptance_dir or self._DEFAULT_ACCEPTANCE_DIR)
            / f"{self._portable_key(character_id)}-v{character_version}.json"
        )
        if not source.is_file():
            raise ValueError(
                f"Acceptance list '{source}' is required before view-pack approval. "
                f"A list governs exactly one character version, so a pack at "
                f"v{character_version} needs a list whose character_version is "
                f"{character_version} (conventionally "
                f"{self._portable_key(character_id)}-v{character_version}.json "
                f"in the acceptance directory)."
            )
        acceptance_bytes = source.read_bytes()
        raw_acceptance = json.loads(acceptance_bytes.decode("utf-8"))
        if not isinstance(raw_acceptance, dict):
            raise TypeError("Acceptance list must contain an object.")
        acceptance = CharacterAcceptanceList.from_dict(raw_acceptance)
        if acceptance.character_id != character_id:
            raise ValueError(
                f"Acceptance list '{source}' governs character "
                f"'{acceptance.character_id}', not '{character_id}'."
            )
        if acceptance.character_version != character_version:
            # Name both numbers: the bare "another character version" message
            # left the operator guessing which of the two files to fix.
            raise ValueError(
                f"Acceptance list '{source}' governs character version "
                f"v{acceptance.character_version}, but the pack under review is "
                f"v{character_version}. Either approve v"
                f"{acceptance.character_version} or add the version-bound list "
                f"'{self._portable_key(character_id)}-v{character_version}.json'."
            )
        if acceptance.brief_hash != pack.brief_hash:
            raise ValueError(
                "Acceptance list is bound to another brief; review the acceptance file."
            )
        automatic_checks_verified = await self._verify_automatic_acceptance(
            root=root,
            pack=pack,
            acceptance=acceptance,
        )
        confirmed = {str(check) for check in confirmed_checks}
        missing = [
            check.id for check in acceptance.human_checks if check.id not in confirmed
        ]
        if missing:
            raise ValueError(
                "View-pack approval requires signed human checks: " + ", ".join(missing)
            )
        verified_evidence: list[str] = []
        for evidence in acceptance.required_evidence:
            if PurePosixPath(evidence).name == "view-pack-approval.json":
                continue
            evidence_key = f"{root}/{evidence}"
            if not await self._storage.exists(evidence_key):
                raise ValueError(f"Acceptance evidence '{evidence_key}' is missing.")
            verified_evidence.append(evidence)

        approval = CharacterViewPackApproval(
            schema_version=1,
            character_id=character_id,
            character_version=character_version,
            brief_hash=pack.brief_hash,
            approved_by=approved_by,
            approved_at=datetime.now(timezone.utc),
            contact_sheet_storage_key=pack.contact_sheet_storage_key,
            contact_sheet_content_hash=pack.contact_sheet_content_hash,
            view_hashes={draft.view: draft.content_hash for draft in pack.drafts},
            acceptance_sha256=hashlib.sha256(acceptance_bytes).hexdigest(),
            human_checks=acceptance.human_checks,
            verified_evidence=tuple(verified_evidence),
            automatic_checks_verified=automatic_checks_verified,
        )
        approval_key = f"{root}/view-pack-approval.json"
        if await self._storage.exists(approval_key):
            existing_raw = json.loads(
                (await self._storage.load(approval_key)).decode("utf-8")
            )
            existing = CharacterViewPackApproval.from_dict(existing_raw)
            if (
                dict(existing.view_hashes) != dict(approval.view_hashes)
                or existing.contact_sheet_content_hash != approval.contact_sheet_content_hash
                or existing.acceptance_sha256 != approval.acceptance_sha256
            ):
                raise ValueError(
                    "View-pack approval is already locked to other assets or "
                    "an earlier acceptance list."
                )
            return existing
        payload = (json.dumps(approval.to_dict(), indent=2, sort_keys=True) + "\n").encode()
        await self._storage.save_stream(
            approval_key, _single_chunk(payload), "application/json"
        )
        return approval

    async def reject_view_pack(
        self,
        *,
        character_id: str,
        character_version: int,
        rejected_by: str,
        reason: str,
        output_prefix: str = "characters",
        superseded_by_version: int | None = None,
    ) -> CharacterPackRejection:
        """Record a human refusal that no later run can approve past.

        The rejected asset hashes are captured while the pack still exists, so
        the receipt documents exactly what was turned down. Recording is
        idempotent for the same refusal and refuses to rewrite a different one:
        a receipt that could be edited is not a verdict.
        """
        if character_version < 1:
            raise ValueError("Character version must be positive.")
        root = self._root(output_prefix, character_id, character_version)
        rejected_hashes: dict[str, str] = {}
        manifest_key = f"{root}/view-pack.json"
        if await self._storage.exists(manifest_key):
            raw_pack = json.loads(
                (await self._storage.load(manifest_key)).decode("utf-8")
            )
            if isinstance(raw_pack, dict):
                pack = CharacterReferenceDraftPack.from_dict(raw_pack)
                rejected_hashes = {
                    draft.view: draft.content_hash for draft in pack.drafts
                }
        rejection = CharacterPackRejection(
            schema_version=REJECTION_SCHEMA_VERSION,
            character_id=character_id,
            character_version=character_version,
            artifact="VIEW_PACK",
            reason=reason,
            rejected_by=rejected_by,
            rejected_at=datetime.now(timezone.utc),
            rejected_hashes=rejected_hashes,
            superseded_by_version=superseded_by_version,
        )
        return await record_rejection(
            self._storage, f"{root}/{rejection.storage_filename}", rejection
        )

    async def load_view_pack_rejection(
        self,
        *,
        character_id: str,
        character_version: int,
        output_prefix: str = "characters",
    ) -> CharacterPackRejection | None:
        root = self._root(output_prefix, character_id, character_version)
        return await load_rejection(self._storage, f"{root}/view-pack-rejection.json")

    async def _refuse_rejected_view_pack(self, root: str) -> None:
        receipt = await load_rejection(
            self._storage, f"{root}/view-pack-rejection.json"
        )
        if receipt is not None:
            raise ValueError(receipt.refusal_message())

    async def require_view_pack_approval(
        self,
        *,
        character_id: str,
        character_version: int,
        output_prefix: str = "characters",
    ) -> CharacterViewPackApproval:
        """Fail-closed boundary for later pose production."""
        root = self._root(output_prefix, character_id, character_version)
        approval_key = f"{root}/view-pack-approval.json"
        if not await self._storage.exists(approval_key):
            raise ValueError("Pose production requires view-pack-approval.json.")
        raw = json.loads((await self._storage.load(approval_key)).decode("utf-8"))
        if not isinstance(raw, dict):
            raise TypeError("View-pack approval must contain an object.")
        approval = CharacterViewPackApproval.from_dict(raw)
        if (
            approval.character_id != character_id
            or approval.character_version != character_version
        ):
            raise ValueError("View-pack approval belongs to another character version.")
        manifest_key = f"{root}/view-pack.json"
        if not await self._storage.exists(manifest_key):
            raise StorageError("Approved view-pack manifest is missing.")
        manifest_raw = json.loads((await self._storage.load(manifest_key)).decode("utf-8"))
        if not isinstance(manifest_raw, dict):
            raise TypeError("View-pack manifest must contain an object.")
        pack = CharacterReferenceDraftPack.from_dict(manifest_raw)
        current_hashes = {draft.view: draft.content_hash for draft in pack.drafts}
        if current_hashes != dict(approval.view_hashes):
            raise ValueError("Approved view-pack manifest has changed.")
        for draft in pack.drafts:
            if not await self._storage.exists(draft.storage_key):
                raise StorageError(f"Approved view '{draft.view}' is missing.")
            if (
                hashlib.sha256(await self._storage.load(draft.storage_key)).hexdigest()
                != approval.view_hashes[draft.view]
            ):
                raise ValueError(f"Approved view '{draft.view}' has changed.")
        if not await self._storage.exists(approval.contact_sheet_storage_key):
            raise StorageError("Approved contact sheet is missing.")
        if (
            hashlib.sha256(await self._storage.load(approval.contact_sheet_storage_key)).hexdigest()
            != approval.contact_sheet_content_hash
        ):
            raise ValueError("Approved contact sheet has changed.")
        return approval

    async def load_approved_view_pack(
        self,
        *,
        character_id: str,
        character_version: int,
        output_prefix: str = "characters",
    ) -> CharacterReferenceDraftPack:
        await self.require_view_pack_approval(
            character_id=character_id,
            character_version=character_version,
            output_prefix=output_prefix,
        )
        root = self._root(output_prefix, character_id, character_version)
        raw = json.loads((await self._storage.load(f"{root}/view-pack.json")).decode("utf-8"))
        if not isinstance(raw, dict):
            raise TypeError("Approved view-pack manifest must contain an object.")
        return CharacterReferenceDraftPack.from_dict(raw)

    async def _verify_automatic_acceptance(
        self,
        *,
        root: str,
        pack: CharacterReferenceDraftPack,
        acceptance: CharacterAcceptanceList,
    ) -> tuple[str, ...]:
        supported = {
            "exactly_one_person",
            "head_inside_frame",
            "feet_inside_frame",
            "expected_orientation",
            "back_view_no_face",
            "signature_mark_face_closeup",
            "provenance_hashes",
            "consistency_contract_bound",
        }
        unknown = [check for check in acceptance.automatic_checks if check not in supported]
        if unknown:
            raise ValueError(
                "Acceptance list contains unsupported automatic checks: " + ", ".join(unknown)
            )
        reports = {draft.view: dict(draft.qc_report or {}) for draft in pack.drafts}

        def all_views(check_id: str, *, exclude: frozenset[str] = frozenset()) -> bool:
            return all(
                bool(dict(report.get("checks", {})).get(check_id))
                for view, report in reports.items()
                if view not in exclude
            )

        results = {
            "exactly_one_person": all_views("exactly_one_person"),
            "head_inside_frame": all_views("head_inside_frame"),
            "feet_inside_frame": all_views(
                "feet_inside_frame", exclude=frozenset({"FACE_CLOSEUP"})
            ),
            "expected_orientation": all_views("expected_orientation"),
            "back_view_no_face": bool(
                dict(reports.get("BACK", {}).get("checks", {})).get("back_view_no_face")
            ),
            "signature_mark_face_closeup": bool(
                dict(reports.get("FACE_CLOSEUP", {}).get("checks", {})).get(
                    "signature_mark_face_closeup"
                )
            ),
            "provenance_hashes": await self._verify_view_provenance(root=root, pack=pack),
            "consistency_contract_bound": self._verify_consistency_contracts(pack),
        }
        failed = [check for check in acceptance.automatic_checks if not results.get(check)]
        if failed:
            raise ValueError(
                "View-pack automatic acceptance checks failed: " + ", ".join(failed)
            )
        return tuple(acceptance.automatic_checks)

    @staticmethod
    def _verify_consistency_contracts(pack: CharacterReferenceDraftPack) -> bool:
        contract_hashes: set[str] = set()
        for draft in pack.drafts:
            raw_qc = dict(draft.qc_report or {})
            consistency = raw_qc.get("consistency_qc")
            if not isinstance(consistency, dict):
                return False
            if consistency.get("status") != "HUMAN_REVIEW_REQUIRED":
                return False
            if not consistency.get("automatic_passed"):
                return False
            contract_hash = str(consistency.get("contract_hash", ""))
            if not contract_hash:
                return False
            contract_hashes.add(contract_hash)
        return len(contract_hashes) == 1

    async def _verify_view_provenance(
        self, *, root: str, pack: CharacterReferenceDraftPack
    ) -> bool:
        """Prove where each view's bytes actually came from.

        A drawn view must name the model, prompt and workflow that produced it.
        A view *copied* from an approved artifact -- the canonical source or an
        anchor -- has no model run behind it, so demanding model hashes from it
        asks for evidence that cannot exist. That requirement was unsatisfiable
        for FRONT and FACE_CLOSEUP on every pack from v5 onward, which is why no
        pack could be approved at all.

        Both cases are still proven by bytes, not by assertion. Inheritance is
        accepted only when the view's own hash matches the approved artifact it
        is a copy of, read from storage at approval time.
        """
        manifest_key = f"{root}/manifest.json"
        if not await self._storage.exists(manifest_key):
            return False
        raw = json.loads((await self._storage.load(manifest_key)).decode("utf-8"))
        if not isinstance(raw, dict) or not isinstance(raw.get("assets"), list):
            return False
        by_storage_key = {
            str(entry.get("storage_key")): entry
            for entry in raw["assets"]
            if isinstance(entry, dict)
        }
        approved_hashes = await self._approved_artifact_hashes(root=root, pack=pack)
        for draft in pack.drafts:
            entry = by_storage_key.get(draft.storage_key)
            if entry is None:
                return False
            if entry.get("content_hash") != draft.content_hash:
                return False
            if draft.content_hash in approved_hashes:
                # Byte-identical to an approved artifact: that identity *is* the
                # provenance, and it is checked rather than declared.
                continue
            if (
                not draft.prompt_hash
                or not draft.workflow_hash
                or entry.get("prompt_hash") != draft.prompt_hash
                or entry.get("workflow_hash") != draft.workflow_hash
                or not entry.get("model_hashes")
            ):
                return False
        return True

    async def _approved_artifact_hashes(
        self, *, root: str, pack: CharacterReferenceDraftPack
    ) -> frozenset[str]:
        """Hashes of the approved artifacts a view is allowed to be a copy of.

        Derived from what is on disk, so a copy claim is verified against real
        bytes. An empty result can only make the caller stricter: no view can
        then claim inheritance, and every draft must carry full generation
        provenance.
        """
        keys = (
            pack.canonical_storage_key,
            f"{root}/face_anchor.png",
            f"{root}/fullbody_anchor.png",
        )
        hashes: set[str] = set()
        for key in keys:
            if not key or not await self._storage.exists(key):
                continue
            hashes.add(hashlib.sha256(await self._storage.load(key)).hexdigest())
        return frozenset(hashes)

    @staticmethod
    def _portable_key(value: str) -> str:
        normalized = value.strip().replace("\\", "/").strip("/")
        path = PurePosixPath(normalized)
        if (
            not normalized
            or path.is_absolute()
            or ":" in normalized
            or any(part in {"", ".", ".."} for part in path.parts)
        ):
            raise ValueError("Character view-pack storage key must be portable.")
        return path.as_posix()

    @classmethod
    def _root(cls, output_prefix: str, character_id: str, character_version: int) -> str:
        return (
            f"{cls._portable_key(output_prefix)}/"
            f"{cls._portable_key(character_id)}/v{character_version}"
        )
