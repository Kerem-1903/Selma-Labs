"""Canonical character approval and identity-preserving anchor locking."""

from __future__ import annotations

import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import PurePosixPath

from PIL import Image, UnidentifiedImageError

from core.application.services.production_manifest_service import (
    ProductionManifestService,
)
from core.domain.exceptions import KeyframeGenerationError, StorageError
from core.domain.ports.storage_port import StoragePort
from core.domain.value_objects.character_creation_brief import CharacterCreationBrief
from core.domain.value_objects.character_design import (
    CharacterAnchorArtifact,
    CharacterCanonicalApproval,
    CharacterDesignCandidate,
    CharacterDualAnchorPack,
)
from core.domain.value_objects.character_identity_contract import CharacterIdentityContract


async def _single_chunk(data: bytes):
    yield data


class CharacterCanonicalApprovalService:
    """Own canonical approval, byte locks, dual anchors, and approval evidence."""

    ANCHOR_WORKFLOW_VERSION = "dual-anchor-v2-deterministic"

    def __init__(
        self,
        storage: StoragePort,
        *,
        production_manifest: ProductionManifestService | None = None,
    ) -> None:
        self._storage = storage
        self._production_manifest = production_manifest

    async def approve_candidate(
        self,
        brief: CharacterCreationBrief,
        candidate: CharacterDesignCandidate,
        *,
        approved_by: str,
        character_version: int = 1,
        output_prefix: str = "characters",
        brief_consistency_confirmed: bool = False,
    ) -> CharacterCanonicalApproval:
        approver = approved_by.strip()
        if not approver:
            raise ValueError("Canonical design approval requires a named approver.")
        if character_version < 1:
            raise ValueError("Character version must be at least 1.")
        prefix = self._portable_key(output_prefix)
        expected_candidate_root = PurePosixPath(
            prefix,
            brief.character_id,
            "designs",
            brief.content_hash,
            "runs",
            candidate.run_id,
            "candidates",
        )
        candidate_path = PurePosixPath(self._portable_key(candidate.storage_key))
        if candidate_path.parent != expected_candidate_root:
            raise ValueError(
                "Design candidate does not belong to this confirmed brief."
            )
        if not await self._storage.exists(candidate.storage_key):
            raise StorageError(
                f"Design candidate '{candidate.storage_key}' was not found."
            )
        if candidate.source_type == "PROVIDED_IMAGE" and not brief_consistency_confirmed:
            raise ValueError(
                "Provided canonical image conflicts with the brief until an explicit "
                "human consistency confirmation is recorded."
            )
        image_bytes = await self._storage.load(candidate.storage_key)
        actual_hash = hashlib.sha256(image_bytes).hexdigest()
        if actual_hash != candidate.content_hash:
            raise ValueError("Design candidate changed after generation.")

        version_root = f"{prefix}/{brief.character_id}/v{character_version}"
        canonical_key = f"{version_root}/canonical_source.png"
        if await self._storage.exists(canonical_key):
            existing_hash = hashlib.sha256(
                await self._storage.load(canonical_key)
            ).hexdigest()
            if existing_hash != actual_hash:
                raise ValueError(
                    "Canonical character version is already locked to another image."
                )
        else:
            await self._storage.save(canonical_key, image_bytes, "image/png")

        receipt_key = f"{version_root}/canonical-approval.json"
        if await self._storage.exists(receipt_key):
            existing = CharacterCanonicalApproval.from_dict(
                json.loads((await self._storage.load(receipt_key)).decode("utf-8"))
            )
            if existing.canonical_content_hash != actual_hash:
                raise ValueError(
                    "Canonical approval is already locked to another source image."
                )
            if not existing.anchors_locked:
                raise ValueError(
                    "Existing canonical approval predates the required dual-anchor lock."
                )
            assert existing.face_anchor is not None
            assert existing.fullbody_anchor is not None
            await self.verify_anchor(existing.face_anchor)
            await self.verify_anchor(existing.fullbody_anchor)
            return existing

        anchors = await self.generate_dual_anchors(
            brief,
            canonical_source_key=canonical_key,
            canonical_source_hash=actual_hash,
            source_seed=candidate.seed,
            character_version=character_version,
            output_prefix=prefix,
        )
        approval = CharacterCanonicalApproval(
            schema_version=1,
            character_id=brief.character_id,
            character_version=character_version,
            brief_hash=brief.content_hash,
            source_candidate_key=candidate.storage_key,
            canonical_storage_key=canonical_key,
            canonical_content_hash=actual_hash,
            provider=candidate.provider,
            provider_asset_id=candidate.provider_asset_id,
            seed=candidate.seed,
            approved_by=approver,
            approved_at=datetime.now(timezone.utc),
            face_anchor=anchors.face_anchor,
            fullbody_anchor=anchors.fullbody_anchor,
            anchor_provider="deterministic:canonical-transform",
            anchor_workflow_version=self.ANCHOR_WORKFLOW_VERSION,
            identity_source=("PROVIDED_IMAGE" if candidate.source_type == "PROVIDED_IMAGE" else "GENERATED_DESIGN"),
            identity_source_hash=actual_hash,
            brief_consistency_confirmed=(brief_consistency_confirmed if candidate.source_type == "PROVIDED_IMAGE" else True),
            identity_contract_hash=CharacterIdentityContract.from_brief(brief).content_hash,
        )
        receipt = (
            json.dumps(
                approval.to_dict(), ensure_ascii=False, indent=2, sort_keys=True
            ).encode("utf-8")
            + b"\n"
        )
        await self._storage.save_stream(
            receipt_key, _single_chunk(receipt), "application/json"
        )
        if self._production_manifest is not None:
            self._record_manifest(
                version_root=version_root,
                canonical_key=canonical_key,
                canonical_hash=actual_hash,
                candidate=candidate,
                anchors=anchors,
            )
        return approval

    async def generate_dual_anchors(
        self,
        brief: CharacterCreationBrief,
        *,
        canonical_source_key: str,
        canonical_source_hash: str,
        source_seed: int,
        character_version: int = 1,
        output_prefix: str = "characters",
    ) -> CharacterDualAnchorPack:
        """Derive deterministic face and full-body anchors from the locked source."""
        source_key = self._portable_key(canonical_source_key)
        if not await self._storage.exists(source_key):
            raise StorageError(f"Canonical source '{source_key}' was not found.")
        source_bytes = await self._storage.load(source_key)
        if hashlib.sha256(source_bytes).hexdigest() != canonical_source_hash:
            raise ValueError("Canonical source changed before anchor generation.")

        version_root = (
            f"{self._portable_key(output_prefix)}/{brief.character_id}/v{character_version}"
        )
        specifications = (
            ("FACE", "face_anchor.png", source_seed + 1_000, 1024, 1024),
            ("FULL_BODY", "fullbody_anchor.png", source_seed + 2_000, 768, 1152),
        )
        generated: list[CharacterAnchorArtifact] = []
        for role, filename, seed, width, height in specifications:
            image_bytes = self._derive_anchor_png(
                source_bytes, role=role, width=width, height=height
            )
            digest = hashlib.sha256(image_bytes).hexdigest()
            storage_key = f"{version_root}/{filename}"
            await self._save_locked_asset(storage_key, image_bytes, digest)
            recipe_hash = hashlib.sha256(
                (
                    f"{self.ANCHOR_WORKFLOW_VERSION}:{role}:{width}x{height}:"
                    f"{canonical_source_hash}"
                ).encode()
            ).hexdigest()
            generated.append(
                CharacterAnchorArtifact(
                    role=role,
                    storage_key=storage_key,
                    content_hash=digest,
                    seed=seed,
                    width=width,
                    height=height,
                    provider_asset_id=(
                        f"canonical:{canonical_source_hash[:12]}:{role.casefold()}"
                    ),
                    model_checkpoint="deterministic:canonical-transform",
                    workflow_version=self.ANCHOR_WORKFLOW_VERSION,
                    model_hashes={},
                    render_duration_sec=0.0,
                    peak_vram_mb=None,
                    prompt_hash=recipe_hash,
                    workflow_hash=recipe_hash,
                )
            )
        return CharacterDualAnchorPack(
            character_id=brief.character_id,
            character_version=character_version,
            brief_hash=brief.content_hash,
            canonical_source_key=source_key,
            canonical_source_hash=canonical_source_hash,
            face_anchor=generated[0],
            fullbody_anchor=generated[1],
        )

    async def verify_anchor(self, anchor: CharacterAnchorArtifact) -> None:
        if not await self._storage.exists(anchor.storage_key):
            raise StorageError(
                f"Canonical anchor '{anchor.storage_key}' was not found."
            )
        data = await self._storage.load(anchor.storage_key)
        if hashlib.sha256(data).hexdigest() != anchor.content_hash:
            raise ValueError(f"Canonical {anchor.role} anchor changed after approval.")

    def _record_manifest(
        self,
        *,
        version_root: str,
        canonical_key: str,
        canonical_hash: str,
        candidate: CharacterDesignCandidate,
        anchors: CharacterDualAnchorPack,
    ) -> None:
        assert self._production_manifest is not None
        self._production_manifest.initialize(relative_root=version_root)
        self._production_manifest.record_asset(
            relative_root=version_root,
            asset_id="CANONICAL_SOURCE",
            storage_key=canonical_key,
            content_hash=canonical_hash,
            seed=candidate.seed,
            model_hashes={},
            reference_hashes=(),
            qc_metrics={"human_approved": True},
            render_duration_sec=0.0,
            peak_vram_mb=None,
            prompt_hash=candidate.prompt_hash,
            workflow_hash=candidate.workflow_hash,
            run_id=candidate.run_id,
            state="HUMAN_APPROVED_SOURCE",
        )
        for anchor in (anchors.face_anchor, anchors.fullbody_anchor):
            self._production_manifest.record_asset(
                relative_root=version_root,
                asset_id=f"{anchor.role}_ANCHOR",
                storage_key=anchor.storage_key,
                content_hash=anchor.content_hash,
                seed=anchor.seed,
                model_hashes=dict(anchor.model_hashes or {}),
                reference_hashes=(canonical_hash,),
                qc_metrics={"anchor_locked": True},
                render_duration_sec=anchor.render_duration_sec,
                peak_vram_mb=anchor.peak_vram_mb,
                prompt_hash=anchor.prompt_hash,
                workflow_hash=anchor.workflow_hash,
                run_id=candidate.run_id,
                state="ANCHOR_LOCKED",
            )

    async def _save_locked_asset(
        self, storage_key: str, image_bytes: bytes, content_hash: str
    ) -> None:
        if await self._storage.exists(storage_key):
            existing_hash = hashlib.sha256(
                await self._storage.load(storage_key)
            ).hexdigest()
            if existing_hash != content_hash:
                raise ValueError(
                    f"Canonical asset '{storage_key}' is already locked to other bytes."
                )
            return
        await self._storage.save(storage_key, image_bytes, "image/png")

    @staticmethod
    def _derive_anchor_png(
        source_bytes: bytes, *, role: str, width: int, height: int
    ) -> bytes:
        """Create identity-preserving anchors without redrawing the character."""
        try:
            with Image.open(io.BytesIO(source_bytes)) as opened:
                source = opened.convert("RGB")
        except (UnidentifiedImageError, OSError, ValueError) as error:
            raise KeyframeGenerationError(
                "Canonical character source is not a readable image."
            ) from error

        source_width, source_height = source.size
        if role == "FACE":
            crop_size = max(1, min(source_width, source_height) // 2)
            left = max(0, (source_width - crop_size) // 2)
            top = max(0, min(source_height - crop_size, source_height // 50))
            anchor = source.crop((left, top, left + crop_size, top + crop_size))
        elif role == "FULL_BODY":
            target_ratio = width / height
            crop_width = min(source_width, max(1, round(source_height * target_ratio)))
            crop_height = min(source_height, max(1, round(crop_width / target_ratio)))
            left = max(0, (source_width - crop_width) // 2)
            top = max(0, (source_height - crop_height) // 2)
            anchor = source.crop((left, top, left + crop_width, top + crop_height))
        else:
            raise ValueError(f"Unknown anchor role: {role}")

        resized = anchor.resize((width, height), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        resized.save(output, format="PNG", optimize=True)
        return output.getvalue()

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
            raise ValueError("Character approval storage key must be portable.")
        return path.as_posix()
