"""Generate design choices and lock one hash-bound canonical character image."""

from __future__ import annotations

import hashlib
import io
import json
import uuid
from datetime import datetime, timezone
from pathlib import PurePosixPath

from PIL import Image, UnidentifiedImageError

from core.application.services.production_manifest_service import (
    ProductionManifestService,
)
from core.domain.exceptions import KeyframeGenerationError, StorageError
from core.domain.ports.keyframe_generation_port import KeyframeGenerationPort
from core.domain.ports.storage_port import StoragePort
from core.domain.value_objects.character_creation_brief import CharacterCreationBrief
from core.domain.value_objects.character_design import (
    CharacterAnchorArtifact,
    CharacterCanonicalApproval,
    CharacterDesignCandidate,
    CharacterDesignCandidatePack,
    CharacterDualAnchorPack,
    CharacterReferenceDraft,
    CharacterReferenceDraftPack,
    CharacterViewPackApproval,
    CharacterViewQuarantineArtifact,
)
from core.domain.value_objects.character_view_qc import (
    CharacterViewObservation,
    CharacterViewQcReport,
)
from core.domain.value_objects.keyframe_generation_request import (
    KeyframeGenerationRequest,
)

ConditioningReference = tuple[str, str, str, float]


async def _single_chunk(data: bytes):
    yield data


class _OfflineFakeViewQualityGate:
    """Deterministic QC evidence used only with the explicit fake generator."""

    async def evaluate(
        self, *, image_bytes: bytes, view: str, seed: int
    ) -> CharacterViewQcReport:
        del image_bytes
        orientation = {
            "FACE_CLOSEUP": "front",
            "FRONT": "front",
            "PROFILE_LEFT": "profile_left",
            "PROFILE_RIGHT": "profile_right",
            "THREE_QUARTER_LEFT": "three_quarter_left",
            "THREE_QUARTER_RIGHT": "three_quarter_right",
            "BACK": "back",
        }[view]
        return CharacterViewQcReport(
            view=view,
            seed=seed,
            passed=True,
            reasons=(),
            observation=CharacterViewObservation(
                person_count=1,
                face_count=0 if view == "BACK" else 1,
                head_inside_frame=True,
                feet_inside_frame=True,
                orientation=orientation,
                confidence=1.0,
                provider="fake:character-view-qc",
            ),
            framing_metrics={},
        )

    async def evaluate_design_candidate(
        self, *, image_bytes: bytes, seed: int, signature_marks=()
    ) -> CharacterViewQcReport:
        del signature_marks
        return await self.evaluate(image_bytes=image_bytes, view="FRONT", seed=seed)


class CharacterDesignService:
    """Provider-neutral first stage of the no-LoRA character engine."""

    _NEGATIVES = (
        "multiple characters",
        "duplicate character",
        "duplicate person",
        "2boys",
        "3boys",
        "2girls",
        "3girls",
        "4girls",
        "5girls",
        "group",
        "lineup",
        "collage",
        "multiple views",
        "multiple poses",
        "character sheet",
        "split panel",
        "background figure",
        "giant silhouette",
        "oversized shadow",
        "cast shadow shaped like a person",
        "dynamic pose",
        "action pose",
        "crouching",
        "wide stance",
        "cropped head",
        "cropped feet",
        "extra limbs",
        "bad hands",
        "text",
        "watermark",
    )
    _STANDARD_VIEWS = (
        (
            "FRONT",
            (
                "strict front view, full body neutral standing character reference, "
                "complete silhouette, entire head and both feet visible"
            ),
        ),
        (
            "FACE_CLOSEUP",
            "front-facing close-up headshot, neutral expression, face and complete hair visible",
        ),
        (
            "PROFILE_LEFT",
            (
                "strict left side profile, full body neutral standing character reference, "
                "entire head and both feet visible"
            ),
        ),
        (
            "PROFILE_RIGHT",
            (
                "strict right side profile, full body neutral standing character reference, "
                "entire head and both feet visible"
            ),
        ),
        (
            "THREE_QUARTER_LEFT",
            (
                "left three-quarter view, full body neutral standing character reference, "
                "entire head and both feet visible"
            ),
        ),
        (
            "THREE_QUARTER_RIGHT",
            (
                "right three-quarter view, full body neutral standing character reference, "
                "entire head and both feet visible"
            ),
        ),
        (
            "BACK",
            (
                "strict back view, full body neutral standing pose, complete back "
                "silhouette, head and feet visible"
            ),
        ),
    )
    _ANCHOR_WORKFLOW_VERSION = "dual-anchor-v1"
    _VIEW_WORKFLOW_VERSION = "canonical-views-v1"

    def __init__(
        self,
        generator: KeyframeGenerationPort,
        storage: StoragePort,
        quality_gate=None,
        *,
        max_view_attempts: int = 3,
        production_manifest: ProductionManifestService | None = None,
    ) -> None:
        if not 1 <= max_view_attempts <= 10:
            raise ValueError("View generation attempts must be between 1 and 10.")
        self._generator = generator
        self._storage = storage
        self._quality_gate = quality_gate
        if quality_gate is None and generator.name.startswith("fake:"):
            self._quality_gate = _OfflineFakeViewQualityGate()
        self._max_view_attempts = max_view_attempts
        self._production_manifest = production_manifest

    async def generate_candidates(
        self,
        brief: CharacterCreationBrief,
        *,
        count: int = 5,
        output_prefix: str = "characters",
        run_id: str | None = None,
    ) -> CharacterDesignCandidatePack:
        if not 1 <= count <= 8:
            raise ValueError(
                "Character design candidate count must be between 1 and 8."
            )
        prefix = self._portable_key(output_prefix)
        selected_run_id = (run_id or uuid.uuid4().hex[:12]).strip()
        if (
            not selected_run_id
            or self._portable_key(selected_run_id) != selected_run_id
            or "/" in selected_run_id
        ):
            raise ValueError("Character design run_id must be one portable path segment.")
        base_seed = int(brief.content_hash[:8], 16)
        candidates = []
        attempts: list[dict[str, object]] = []
        if self._quality_gate is None:
            raise RuntimeError(
                "Character design QC is not configured; refusing to persist candidates."
            )
        design_root = (
            f"{prefix}/{brief.character_id}/designs/{brief.content_hash}/"
            f"runs/{selected_run_id}"
        )
        run_manifest_key = f"{design_root}/run-manifest.json"
        if await self._storage.exists(run_manifest_key):
            raise ValueError(
                f"Character design run_id '{selected_run_id}' already exists."
            )
        await self._persist_design_run_manifest(
            root=design_root,
            brief=brief,
            run_id=selected_run_id,
            candidates=candidates,
            attempts=attempts,
            status="IN_PROGRESS",
        )
        for index in range(count):
            accepted = None
            for attempt in range(1, self._max_view_attempts + 1):
                seed = base_seed + index * 10_000 + (attempt - 1) * 1_000
                request = self._request(brief, seed=seed, variant=index + 1)
                prompt_hash = self._request_hash(request)
                generated = await self._generator.generate_keyframe(request)
                image_bytes, width, height = self._normalized_png(
                    generated.image_bytes
                )
                digest = hashlib.sha256(image_bytes).hexdigest()
                report = await self._quality_gate.evaluate_design_candidate(
                    image_bytes=image_bytes,
                    seed=seed,
                    signature_marks=brief.signature_marks,
                )
                if not report.passed:
                    quarantine = await self._quarantine_view(
                        root=design_root,
                        view=f"DESIGN_{index + 1:02d}",
                        seed=seed,
                        attempt=attempt,
                        image_bytes=image_bytes,
                        content_hash=digest,
                        report=report,
                    )
                    attempts.append(
                        {
                            "candidate_index": index + 1,
                            "attempt": attempt,
                            "seed": seed,
                            "content_hash": digest,
                            "prompt_hash": prompt_hash,
                            "workflow_hash": str(
                                generated.metadata.get("workflow_hash", "")
                            ),
                            "provider_asset_id": generated.provider_asset_id,
                            "storage_key": quarantine.image_storage_key,
                            "state": "QUARANTINED",
                            "qc_report": report.to_dict(),
                        }
                    )
                    continue
                storage_key = (
                    f"{design_root}/candidates/"
                    f"design-{index + 1:02d}-{digest[:12]}.png"
                )
                stored = await self._storage.save(
                    storage_key, image_bytes, "image/png"
                )
                if stored.key != storage_key:
                    raise StorageError(
                        "Storage adapter returned a different design candidate key."
                    )
                accepted = CharacterDesignCandidate(
                    storage_key=storage_key,
                    content_hash=digest,
                    seed=seed,
                    provider=self._generator.name,
                    provider_asset_id=generated.provider_asset_id,
                    width=width,
                    height=height,
                    run_id=selected_run_id,
                    prompt_hash=prompt_hash,
                    workflow_hash=str(generated.metadata.get("workflow_hash", "")),
                    qc_report=report.to_dict(),
                )
                candidates.append(accepted)
                attempts.append(
                    {
                        "candidate_index": index + 1,
                        "attempt": attempt,
                        "seed": seed,
                        "content_hash": digest,
                        "prompt_hash": prompt_hash,
                        "workflow_hash": accepted.workflow_hash,
                        "provider_asset_id": generated.provider_asset_id,
                        "storage_key": storage_key,
                        "state": "QC_PASSED",
                        "qc_report": report.to_dict(),
                    }
                )
                break
            if accepted is None:
                await self._persist_design_run_manifest(
                    root=design_root,
                    brief=brief,
                    run_id=selected_run_id,
                    candidates=candidates,
                    attempts=attempts,
                    status="BLOCKED",
                    failure=(
                        f"Design candidate {index + 1} failed QC after "
                        f"{self._max_view_attempts} attempts."
                    ),
                )
                raise KeyframeGenerationError(
                    f"Design candidate {index + 1} failed QC after "
                    f"{self._max_view_attempts} attempts."
                )
        pack = CharacterDesignCandidatePack(
            schema_version=1,
            character_id=brief.character_id,
            brief_hash=brief.content_hash,
            candidates=tuple(candidates),
            run_id=selected_run_id,
        )
        await self._persist_design_run_manifest(
            root=design_root,
            brief=brief,
            run_id=selected_run_id,
            candidates=candidates,
            attempts=attempts,
            status="PENDING_HUMAN_REVIEW",
        )
        return pack

    async def approve_candidate(
        self,
        brief: CharacterCreationBrief,
        candidate: CharacterDesignCandidate,
        *,
        approved_by: str,
        character_version: int = 1,
        output_prefix: str = "characters",
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
            await self._verify_anchor(existing.face_anchor)
            await self._verify_anchor(existing.fullbody_anchor)
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
            anchor_provider=self._generator.name,
            anchor_workflow_version=self._ANCHOR_WORKFLOW_VERSION,
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
            self._production_manifest.initialize(relative_root=version_root)
            self._production_manifest.record_asset(
                relative_root=version_root,
                asset_id="CANONICAL_SOURCE",
                storage_key=canonical_key,
                content_hash=actual_hash,
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
                    reference_hashes=(actual_hash,),
                    qc_metrics={"anchor_locked": True},
                    render_duration_sec=anchor.render_duration_sec,
                    peak_vram_mb=anchor.peak_vram_mb,
                    prompt_hash=anchor.prompt_hash,
                    workflow_hash=anchor.workflow_hash,
                    run_id=candidate.run_id,
                    state="ANCHOR_LOCKED",
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
        """Derive the face and full-body anchors from one canonical source."""
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
        generated_anchors: list[CharacterAnchorArtifact] = []
        for role, filename, seed, width, height in specifications:
            request = self._anchor_request(
                brief,
                canonical_source_key=source_key,
                canonical_source_hash=canonical_source_hash,
                role=role,
                seed=seed,
                width=width,
                height=height,
            )
            generated = await self._generator.generate_keyframe(request)
            image_bytes, actual_width, actual_height = self._normalized_png(
                generated.image_bytes
            )
            digest = hashlib.sha256(image_bytes).hexdigest()
            storage_key = f"{version_root}/{filename}"
            await self._save_locked_asset(storage_key, image_bytes, digest)
            generated_anchors.append(
                CharacterAnchorArtifact(
                    role=role,
                    storage_key=storage_key,
                    content_hash=digest,
                    seed=seed,
                    width=actual_width,
                    height=actual_height,
                    provider_asset_id=generated.provider_asset_id,
                    model_checkpoint=str(
                        generated.metadata.get("model_checkpoint")
                        or self._generator.name
                    ),
                    workflow_version=self._ANCHOR_WORKFLOW_VERSION,
                    model_hashes=(
                        {
                            str(key): str(value)
                            for key, value in generated.metadata.get(
                                "model_hashes", {}
                            ).items()
                        }
                        if isinstance(generated.metadata.get("model_hashes"), dict)
                        else {}
                    ),
                    render_duration_sec=float(
                        generated.metadata.get("render_duration_sec", 0.0)
                    ),
                    peak_vram_mb=(
                        float(generated.metadata["peak_vram_mb"])
                        if generated.metadata.get("peak_vram_mb") is not None
                        else None
                    ),
                    prompt_hash=self._request_hash(request),
                    workflow_hash=str(generated.metadata.get("workflow_hash", "")),
                )
            )
        face_anchor, fullbody_anchor = generated_anchors
        return CharacterDualAnchorPack(
            character_id=brief.character_id,
            character_version=character_version,
            brief_hash=brief.content_hash,
            canonical_source_key=source_key,
            canonical_source_hash=canonical_source_hash,
            face_anchor=face_anchor,
            fullbody_anchor=fullbody_anchor,
        )

    async def generate_reference_drafts(
        self,
        brief: CharacterCreationBrief,
        approval: CharacterCanonicalApproval,
        *,
        output_prefix: str = "characters",
    ) -> CharacterReferenceDraftPack:
        """Compatibility name for the canonical seven-view generation stage."""
        return await self.generate_canonical_views(
            brief, approval, output_prefix=output_prefix
        )

    async def generate_canonical_views(
        self,
        brief: CharacterCreationBrief,
        approval: CharacterCanonicalApproval,
        *,
        output_prefix: str = "characters",
    ) -> CharacterReferenceDraftPack:
        relative_root = (
            f"{self._portable_key(output_prefix)}/{brief.character_id}/"
            f"v{approval.character_version}"
        )
        if self._production_manifest is None:
            return await self._generate_canonical_views_unlocked(
                brief, approval, output_prefix=output_prefix
            )
        with self._production_manifest.work_lock(relative_root):
            self._production_manifest.initialize(relative_root=relative_root)
            try:
                return await self._generate_canonical_views_unlocked(
                    brief, approval, output_prefix=output_prefix
                )
            except Exception as error:
                status = (
                    "BLOCKED_PREFLIGHT"
                    if "BLOCKED_PREFLIGHT" in str(error)
                    else "FAILED"
                )
                self._production_manifest.finalize(
                    relative_root=relative_root, status=status
                )
                raise

    async def _generate_canonical_views_unlocked(
        self,
        brief: CharacterCreationBrief,
        approval: CharacterCanonicalApproval,
        *,
        output_prefix: str = "characters",
    ) -> CharacterReferenceDraftPack:
        """Generate, QC and persist seven views through the staged chain."""
        if approval.character_id != brief.character_id:
            raise ValueError("Canonical approval belongs to another character.")
        if approval.brief_hash != brief.content_hash:
            raise ValueError("Canonical approval belongs to another character brief.")
        if not await self._storage.exists(approval.canonical_storage_key):
            raise StorageError(
                f"Canonical design '{approval.canonical_storage_key}' was not found."
            )
        canonical = await self._storage.load(approval.canonical_storage_key)
        if hashlib.sha256(canonical).hexdigest() != approval.canonical_content_hash:
            raise ValueError("Canonical design changed after human approval.")
        if not approval.anchors_locked:
            raise ValueError("Canonical approval does not contain locked dual anchors.")
        assert approval.face_anchor is not None
        assert approval.fullbody_anchor is not None
        await self._verify_anchor(approval.face_anchor)
        await self._verify_anchor(approval.fullbody_anchor)
        if self._quality_gate is None:
            raise RuntimeError(
                "Character view QC is not configured; refusing to persist generated views."
            )

        prefix = self._portable_key(output_prefix)
        root = f"{prefix}/{brief.character_id}/v{approval.character_version}"
        base_seed = int(brief.content_hash[8:16], 16)
        directions = dict(self._STANDARD_VIEWS)
        face = approval.face_anchor
        fullbody = approval.fullbody_anchor
        drafts: list[CharacterReferenceDraft] = []
        quarantined: list[CharacterViewQuarantineArtifact] = []
        produced: dict[str, CharacterReferenceDraft] = {}
        production_order = (
            "FACE_CLOSEUP",
            "FRONT",
            "PROFILE_LEFT",
            "PROFILE_RIGHT",
            "THREE_QUARTER_LEFT",
            "THREE_QUARTER_RIGHT",
            "BACK",
        )
        for index, view in enumerate(production_order):
            references = (
                (
                    "FACE_CLOSEUP",
                    face.storage_key,
                    face.content_hash,
                    0.85,
                ),
            ) if view == "FACE_CLOSEUP" else self._conditioning_references(
                view=view, face_anchor=face, fullbody_anchor=fullbody, produced=produced
            )
            accepted: CharacterReferenceDraft | None = None
            for attempt in range(1, self._max_view_attempts + 1):
                seed = (
                    face.seed
                    if view == "FACE_CLOSEUP" and attempt == 1
                    else base_seed + index * 10_000 + (attempt - 1) * 1_000
                )
                if view == "FACE_CLOSEUP" and attempt == 1:
                    raw_bytes = await self._storage.load(face.storage_key)
                    provider_asset_id = face.provider_asset_id
                    model_checkpoint = face.model_checkpoint
                    generation_metadata: dict[str, object] = {
                        "model_hashes": dict(face.model_hashes or {}),
                        "render_duration_sec": 0.0,
                        "peak_vram_mb": None,
                        "prompt_hash": face.prompt_hash,
                        "workflow_hash": face.workflow_hash,
                    }
                else:
                    request = self._reference_request(
                        brief,
                        view=view,
                        direction=directions[view],
                        seed=seed,
                        references=references,
                    )
                    generated = await self._generator.generate_keyframe(request)
                    raw_bytes = generated.image_bytes
                    provider_asset_id = generated.provider_asset_id
                    model_checkpoint = str(
                        generated.metadata.get("model_checkpoint")
                        or self._generator.name
                    )
                    generation_metadata = dict(generated.metadata)
                    generation_metadata.setdefault(
                        "prompt_hash", self._request_hash(request)
                    )
                image_bytes, width, height = self._normalized_png(raw_bytes)
                report = await self._quality_gate.evaluate(
                    image_bytes=image_bytes, view=view, seed=seed
                )
                digest = hashlib.sha256(image_bytes).hexdigest()
                if not report.passed:
                    quarantine = await self._quarantine_view(
                        root=root,
                        view=view,
                        seed=seed,
                        attempt=attempt,
                        image_bytes=image_bytes,
                        content_hash=digest,
                        report=report,
                    )
                    quarantined.append(quarantine)
                    self._record_manifest_asset(
                        root=root,
                        asset_id=f"{view}:attempt-{attempt}",
                        storage_key=quarantine.image_storage_key,
                        content_hash=digest,
                        seed=seed,
                        reference_hashes=tuple(item[2] for item in references),
                        report=report,
                        generation_metadata=generation_metadata,
                        state="QUARANTINED",
                    )
                    continue
                key = f"{root}/views/{view.casefold().replace('_', '-')}.png"
                await self._save_locked_asset(key, image_bytes, digest)
                accepted = CharacterReferenceDraft(
                    view=view,
                    storage_key=key,
                    content_hash=digest,
                    seed=seed,
                    width=width,
                    height=height,
                    conditioning_source_keys=tuple(item[1] for item in references),
                    conditioning_source_hashes=tuple(item[2] for item in references),
                    identity_reference_weights=tuple(item[3] for item in references),
                    provider_asset_id=provider_asset_id,
                    model_checkpoint=model_checkpoint,
                    workflow_version=self._VIEW_WORKFLOW_VERSION,
                    qc_report=report.to_dict(),
                    prompt_hash=str(generation_metadata.get("prompt_hash", "")),
                    workflow_hash=str(generation_metadata.get("workflow_hash", "")),
                )
                drafts.append(accepted)
                produced[view] = accepted
                self._record_manifest_asset(
                    root=root,
                    asset_id=f"{view}:attempt-{attempt}",
                    storage_key=key,
                    content_hash=digest,
                    seed=seed,
                    reference_hashes=tuple(item[2] for item in references),
                    report=report,
                    generation_metadata=generation_metadata,
                    state="QC_PASSED",
                )
                break
            if accepted is None:
                return await self._persist_view_pack(
                    root=root,
                    brief=brief,
                    approval=approval,
                    drafts=drafts,
                    quarantined=quarantined,
                    status="BLOCKED",
                )
        return await self._persist_view_pack(
            root=root,
            brief=brief,
            approval=approval,
            drafts=drafts,
            quarantined=quarantined,
            status="PENDING_HUMAN_REVIEW",
        )

    async def _persist_view_pack(
        self,
        *,
        root: str,
        brief: CharacterCreationBrief,
        approval: CharacterCanonicalApproval,
        drafts: list[CharacterReferenceDraft],
        quarantined: list[CharacterViewQuarantineArtifact],
        status: str,
    ) -> CharacterReferenceDraftPack:
        contact_key = ""
        contact_hash = ""
        if status == "PENDING_HUMAN_REVIEW":
            contact_bytes = await self._contact_sheet(drafts)
            contact_hash = hashlib.sha256(contact_bytes).hexdigest()
            contact_key = f"{root}/contact-sheets/views.png"
            await self._save_locked_asset(contact_key, contact_bytes, contact_hash)
        pack = CharacterReferenceDraftPack(
            schema_version=1,
            character_id=brief.character_id,
            character_version=approval.character_version,
            brief_hash=brief.content_hash,
            canonical_storage_key=approval.canonical_storage_key,
            drafts=tuple(drafts),
            status=status,
            quarantined=tuple(quarantined),
            contact_sheet_storage_key=contact_key,
            contact_sheet_content_hash=contact_hash,
        )
        payload = (json.dumps(pack.to_dict(), indent=2, sort_keys=True) + "\n").encode()
        await self._storage.save_stream(
            f"{root}/view-pack.json", _single_chunk(payload), "application/json"
        )
        if self._production_manifest is not None:
            self._production_manifest.finalize(relative_root=root, status=status)
        return pack

    def _record_manifest_asset(
        self,
        *,
        root: str,
        asset_id: str,
        storage_key: str,
        content_hash: str,
        seed: int,
        reference_hashes: tuple[str, ...],
        report: CharacterViewQcReport,
        generation_metadata: dict[str, object],
        state: str,
    ) -> None:
        if self._production_manifest is None:
            return
        raw_model_hashes = generation_metadata.get("model_hashes", {})
        model_hashes = (
            {str(key): str(value) for key, value in raw_model_hashes.items()}
            if isinstance(raw_model_hashes, dict)
            else {}
        )
        raw_peak = generation_metadata.get("peak_vram_mb")
        peak_vram_mb = float(raw_peak) if raw_peak is not None else None
        self._production_manifest.record_asset(
            relative_root=root,
            asset_id=asset_id,
            storage_key=storage_key,
            content_hash=content_hash,
            seed=seed,
            model_hashes=model_hashes,
            reference_hashes=reference_hashes,
            qc_metrics=report.to_dict(),
            render_duration_sec=float(
                generation_metadata.get("render_duration_sec", 0.0)
            ),
            peak_vram_mb=peak_vram_mb,
            state=state,
            prompt_hash=str(generation_metadata.get("prompt_hash", "")),
            workflow_hash=str(generation_metadata.get("workflow_hash", "")),
        )

    @staticmethod
    def _request_hash(request: KeyframeGenerationRequest) -> str:
        payload = json.dumps(
            request.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    async def _persist_design_run_manifest(
        self,
        *,
        root: str,
        brief: CharacterCreationBrief,
        run_id: str,
        candidates: list[CharacterDesignCandidate],
        attempts: list[dict[str, object]],
        status: str,
        failure: str = "",
    ) -> None:
        payload = {
            "schema_version": 1,
            "character_id": brief.character_id,
            "brief_hash": brief.content_hash,
            "run_id": run_id,
            "status": status,
            "failure": failure or None,
            "candidates": [candidate.to_dict() for candidate in candidates],
            "attempts": attempts,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        data = (
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        await self._storage.save_stream(
            f"{root}/run-manifest.json",
            _single_chunk(data),
            "application/json",
        )

    async def _quarantine_view(
        self,
        *,
        root: str,
        view: str,
        seed: int,
        attempt: int,
        image_bytes: bytes,
        content_hash: str,
        report: CharacterViewQcReport,
    ) -> CharacterViewQuarantineArtifact:
        reason = report.reasons[0] if report.reasons else "unknown"
        reason = "".join(
            character if character.isalnum() or character in "-_" else "-"
            for character in reason
        )[:80]
        stem = f"{view.casefold()}_seed{seed}_fail_{reason}"
        image_key = f"{root}/quarantine/{stem}.png"
        report_key = f"{root}/quarantine/{stem}.json"
        await self._save_locked_asset(image_key, image_bytes, content_hash)
        payload = {
            "schema_version": 1,
            "attempt": attempt,
            "content_hash": content_hash,
            **report.to_dict(),
        }
        report_bytes = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
        await self._save_locked_asset(
            report_key,
            report_bytes,
            hashlib.sha256(report_bytes).hexdigest(),
            content_type="application/json",
        )
        return CharacterViewQuarantineArtifact(
            view=view,
            seed=seed,
            attempt=attempt,
            image_storage_key=image_key,
            report_storage_key=report_key,
            content_hash=content_hash,
            reasons=report.reasons,
        )

    async def _contact_sheet(
        self, drafts: list[CharacterReferenceDraft]
    ) -> bytes:
        tile_width, tile_height, label_height = 320, 480, 32
        sheet = Image.new("RGB", (tile_width * 4, (tile_height + label_height) * 2), "white")
        for index, draft in enumerate(drafts):
            image_bytes = await self._storage.load(draft.storage_key)
            if hashlib.sha256(image_bytes).hexdigest() != draft.content_hash:
                raise ValueError(f"View '{draft.view}' changed before contact-sheet creation.")
            with Image.open(io.BytesIO(image_bytes)) as source:
                tile = source.convert("RGB")
                tile.thumbnail((tile_width, tile_height), Image.Resampling.LANCZOS)
            left = (index % 4) * tile_width + (tile_width - tile.width) // 2
            top = (index // 4) * (tile_height + label_height)
            sheet.paste(tile, (left, top))
            from PIL import ImageDraw

            ImageDraw.Draw(sheet).text(
                ((index % 4) * tile_width + 8, top + tile_height + 8),
                draft.view.replace("_", " "),
                fill="black",
            )
        output = io.BytesIO()
        sheet.save(output, format="PNG", optimize=True)
        return output.getvalue()

    async def approve_view_pack(
        self,
        *,
        character_id: str,
        character_version: int,
        approved_by: str,
        output_prefix: str = "characters",
    ) -> CharacterViewPackApproval:
        if character_version < 1:
            raise ValueError("Character version must be positive.")
        root = (
            f"{self._portable_key(output_prefix)}/"
            f"{self._portable_key(character_id)}/v{character_version}"
        )
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
        )
        approval_key = f"{root}/view-pack-approval.json"
        if await self._storage.exists(approval_key):
            existing_raw = json.loads(
                (await self._storage.load(approval_key)).decode("utf-8")
            )
            existing = CharacterViewPackApproval.from_dict(existing_raw)
            if (
                dict(existing.view_hashes) != dict(approval.view_hashes)
                or existing.contact_sheet_content_hash
                != approval.contact_sheet_content_hash
            ):
                raise ValueError("View-pack approval is already locked to other assets.")
            return existing
        payload = (json.dumps(approval.to_dict(), indent=2, sort_keys=True) + "\n").encode()
        await self._storage.save_stream(
            approval_key, _single_chunk(payload), "application/json"
        )
        return approval

    async def require_view_pack_approval(
        self,
        *,
        character_id: str,
        character_version: int,
        output_prefix: str = "characters",
    ) -> CharacterViewPackApproval:
        """Fail-closed boundary for the later pose-production stage."""
        root = (
            f"{self._portable_key(output_prefix)}/"
            f"{self._portable_key(character_id)}/v{character_version}"
        )
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
        manifest_raw = json.loads(
            (await self._storage.load(f"{root}/view-pack.json")).decode("utf-8")
        )
        if not isinstance(manifest_raw, dict):
            raise TypeError("View-pack manifest must contain an object.")
        pack = CharacterReferenceDraftPack.from_dict(manifest_raw)
        current_hashes = {draft.view: draft.content_hash for draft in pack.drafts}
        if current_hashes != dict(approval.view_hashes):
            raise ValueError("Approved view-pack manifest has changed.")
        for draft in pack.drafts:
            if hashlib.sha256(
                await self._storage.load(draft.storage_key)
            ).hexdigest() != approval.view_hashes[draft.view]:
                raise ValueError(f"Approved view '{draft.view}' has changed.")
        if hashlib.sha256(
            await self._storage.load(approval.contact_sheet_storage_key)
        ).hexdigest() != approval.contact_sheet_content_hash:
            raise ValueError("Approved contact sheet has changed.")
        return approval

    async def load_approved_view_pack(
        self,
        *,
        character_id: str,
        character_version: int,
        output_prefix: str = "characters",
    ) -> CharacterReferenceDraftPack:
        """Return the hash-verified pack used by downstream keyframe work."""
        await self.require_view_pack_approval(
            character_id=character_id,
            character_version=character_version,
            output_prefix=output_prefix,
        )
        root = (
            f"{self._portable_key(output_prefix)}/"
            f"{self._portable_key(character_id)}/v{character_version}"
        )
        raw = json.loads(
            (await self._storage.load(f"{root}/view-pack.json")).decode("utf-8")
        )
        if not isinstance(raw, dict):
            raise TypeError("Approved view-pack manifest must contain an object.")
        return CharacterReferenceDraftPack.from_dict(raw)

    @classmethod
    def _request(
        cls, brief: CharacterCreationBrief, *, seed: int, variant: int
    ) -> KeyframeGenerationRequest:
        identity = ", ".join(
            value
            for value in (
                brief.age_band,
                brief.gender_presentation,
                brief.body_type,
                brief.face,
                brief.eyes,
                brief.hair,
                brief.outfit,
                *(mark.label for mark in brief.signature_marks),
                *brief.props,
            )
            if value
        )
        palette = ", ".join(brief.palette)
        personality = ", ".join(brief.personality)
        prompt = ", ".join(
            value
            for value in (
                "masterpiece, original single anime character design",
                brief.concept,
                identity,
                personality,
                f"character palette: {palette}" if palette else "",
                brief.style_preset,
                (
                    "one isolated figure only, strict neutral front standing pose, "
                    "arms relaxed at sides, feet shoulder-width apart, full body, "
                    "entire head and both feet visible, centered and occupying about "
                    "seventy percent of the canvas"
                ),
                "clean softly graded studio background",
                f"design variation {variant}",
                brief.additional_notes,
            )
            if value
        )
        return KeyframeGenerationRequest(
            shot_contract_id=f"character-design-{brief.character_id}-{seed}",
            camera_constraints={
                "angle": "full body front view",
                "lens": "50mm",
                "movement": "locked",
            },
            action_constraints={"primary_action": "neutral standing pose"},
            visual_constraints={
                "prompt": prompt,
                "composition_contract": "one centered character; full silhouette visible",
                "environment_style": "soft gradient studio background",
                "latent_mode": "empty",
                "extra_tags": "solo",
            },
            negative_prompts=tuple(dict.fromkeys((*brief.avoid, *cls._NEGATIVES))),
            width=1024,
            height=1024,
            seed=seed,
        )

    @classmethod
    def _anchor_request(
        cls,
        brief: CharacterCreationBrief,
        *,
        canonical_source_key: str,
        canonical_source_hash: str,
        role: str,
        seed: int,
        width: int,
        height: int,
    ) -> KeyframeGenerationRequest:
        subject_tag = cls._subject_tag(brief.gender_presentation)
        identity = cls._identity_description(brief)
        if role == "FACE":
            direction = (
                "front-facing close-up portrait, neutral expression, complete hair and "
                "hairline visible, preserve eye shape and facial marks"
            )
            negatives = ("full body", "long shot", "feet", "distant subject")
            latent_mode = "reference"
            strength = 0.85
        elif role == "FULL_BODY":
            direction = (
                "strict front view, neutral standing pose, full body from head to feet, "
                "preserve body proportions, outfit layers and palette"
            )
            negatives = ("close-up", "portrait crop", "cropped head", "cropped feet")
            latent_mode = "empty"
            strength = 0.65
        else:
            raise ValueError(f"Unknown anchor role: {role}")
        reference = {
            "view": "FRONT",
            "asset_id": canonical_source_hash,
            "storage_key": canonical_source_key,
        }
        return KeyframeGenerationRequest(
            shot_contract_id=(
                f"character-anchor-{brief.character_id}-{role.casefold()}-{seed}"
            ),
            camera_constraints={
                "angle": direction,
                "lens": "50mm",
                "movement": "locked",
            },
            action_constraints={"primary_action": "neutral character reference"},
            visual_constraints={
                "prompt": ", ".join(
                    (
                        f"masterpiece, {subject_tag}, solo, one person only",
                        brief.concept,
                        identity,
                        direction,
                        brief.style_preset,
                        "plain softly graded studio background",
                    )
                ),
                "composition_contract": direction,
                "environment_style": "plain softly graded studio background",
                "latent_mode": latent_mode,
                "identity_mode": "identity_only",
                "identity_strength": strength,
                "identity_end_at": 0.85,
                "extra_tags": f"{subject_tag}, solo, one person, single image",
                "workflow_version": cls._ANCHOR_WORKFLOW_VERSION,
            },
            character_conditioning=(
                {
                    "character_id": brief.character_id,
                    "identity_constraints": {"description": identity},
                    "active_outfit": {"description": brief.outfit},
                    "references": [reference],
                },
            ),
            reference_asset_ids=(canonical_source_hash,),
            reference_storage_keys=(canonical_source_key,),
            negative_prompts=tuple(
                dict.fromkeys((*brief.avoid, *cls._NEGATIVES, *negatives))
            ),
            width=width,
            height=height,
            seed=seed,
        )

    @classmethod
    def _reference_request(
        cls,
        brief: CharacterCreationBrief,
        *,
        view: str,
        direction: str,
        seed: int,
        references: tuple[ConditioningReference, ...],
    ) -> KeyframeGenerationRequest:
        identity = cls._identity_description(brief)
        subject_tag = cls._subject_tag(brief.gender_presentation)
        prompt = ", ".join(
            value
            for value in (
                f"masterpiece, {subject_tag}, solo, one person only",
                brief.concept,
                identity,
                direction,
                brief.style_preset,
                "plain softly graded studio background",
            )
            if value
        )
        weights = tuple(item[3] for item in references)
        reference_ids = tuple(
            f"{reference_view.casefold()}:{content_hash}"
            for reference_view, _storage_key, content_hash, _weight in references
        )
        return KeyframeGenerationRequest(
            shot_contract_id=f"character-reference-{brief.character_id}-{view.casefold()}",
            camera_constraints={
                "angle": direction,
                "lens": "50mm",
                "movement": "locked",
            },
            action_constraints={"primary_action": "neutral reference pose"},
            visual_constraints={
                "prompt": prompt,
                "composition_contract": direction,
                "environment_style": "plain softly graded studio background",
                "latent_mode": "empty",
                "identity_mode": "identity_only",
                "identity_strength": max(weights),
                "identity_reference_weights": list(weights),
                "identity_end_at": 0.65 if view == "BACK" else 0.85,
                "extra_tags": f"{subject_tag}, solo, one person, single image",
                "workflow_version": cls._VIEW_WORKFLOW_VERSION,
            },
            character_conditioning=tuple(
                {
                    "character_id": brief.character_id,
                    "identity_constraints": {
                        "description": identity,
                        "immutable_marks": [
                            mark.label for mark in brief.signature_marks
                        ],
                    },
                    "active_outfit": {"description": brief.outfit},
                    "references": [
                        {
                            "view": reference_view,
                            "asset_id": asset_id,
                            "storage_key": storage_key,
                        }
                    ],
                }
                for (
                    reference_view,
                    storage_key,
                    content_hash,
                    _weight,
                ), asset_id in zip(references, reference_ids)
            ),
            reference_asset_ids=reference_ids,
            reference_storage_keys=tuple(item[1] for item in references),
            negative_prompts=tuple(
                dict.fromkeys(
                    (
                        *brief.avoid,
                        *cls._NEGATIVES,
                        *cls._view_negatives(view),
                    )
                )
            ),
            width=768,
            height=1152,
            seed=seed,
        )

    @staticmethod
    def _conditioning_references(
        *,
        view: str,
        face_anchor: CharacterAnchorArtifact,
        fullbody_anchor: CharacterAnchorArtifact,
        produced: dict[str, CharacterReferenceDraft],
    ) -> tuple[ConditioningReference, ...]:
        face = (
            "FACE_CLOSEUP",
            face_anchor.storage_key,
            face_anchor.content_hash,
            0.80,
        )
        body = (
            "FRONT",
            fullbody_anchor.storage_key,
            fullbody_anchor.content_hash,
            0.50,
        )

        def generated(reference_view: str, weight: float) -> ConditioningReference:
            draft = produced[reference_view]
            return (
                reference_view,
                draft.storage_key,
                draft.content_hash,
                weight,
            )

        if view == "FRONT":
            return (face, body)
        if view in {"PROFILE_LEFT", "PROFILE_RIGHT"}:
            return (generated("FRONT", 0.65), face)
        if view in {"THREE_QUARTER_LEFT", "THREE_QUARTER_RIGHT"}:
            return (generated("FRONT", 0.75),)
        if view == "BACK":
            return (
                generated("FRONT", 0.55),
                generated("PROFILE_LEFT", 0.40),
            )
        raise ValueError(f"Unknown canonical view: {view}")

    async def _verify_anchor(self, anchor: CharacterAnchorArtifact) -> None:
        if not await self._storage.exists(anchor.storage_key):
            raise StorageError(f"Canonical anchor '{anchor.storage_key}' was not found.")
        data = await self._storage.load(anchor.storage_key)
        if hashlib.sha256(data).hexdigest() != anchor.content_hash:
            raise ValueError(f"Canonical {anchor.role} anchor changed after approval.")

    async def _save_locked_asset(
        self,
        storage_key: str,
        image_bytes: bytes,
        content_hash: str,
        *,
        content_type: str = "image/png",
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
        await self._storage.save(storage_key, image_bytes, content_type)

    @staticmethod
    def _identity_description(brief: CharacterCreationBrief) -> str:
        return ", ".join(
            value
            for value in (
                brief.age_band,
                brief.gender_presentation,
                brief.body_type,
                brief.face,
                brief.eyes,
                brief.hair,
                brief.outfit,
                *(mark.label for mark in brief.signature_marks),
                *brief.props,
            )
            if value
        )

    @staticmethod
    def _view_negatives(view: str) -> tuple[str, ...]:
        if view == "FACE_CLOSEUP":
            return ("full body", "long shot", "feet", "distant subject")
        if view == "PROFILE_LEFT":
            return (
                "front view",
                "right profile",
                "three-quarter view",
                "looking at viewer",
            )
        if view == "PROFILE_RIGHT":
            return (
                "front view",
                "left profile",
                "three-quarter view",
                "looking at viewer",
            )
        if view == "THREE_QUARTER_LEFT":
            return ("front view", "right three-quarter view", "back view")
        if view == "THREE_QUARTER_RIGHT":
            return ("front view", "left three-quarter view", "back view")
        if view == "BACK":
            return (
                "front view",
                "face",
                "eyes",
                "face visible",
                "looking at viewer",
                "looking back",
                "three-quarter view",
            )
        return ()

    @staticmethod
    def _subject_tag(gender_presentation: str) -> str:
        presentation = gender_presentation.casefold()
        feminine_tokens = ("feminine", "female", "woman", "girl")
        masculine_tokens = ("masculine", "male", "man", "boy")
        if any(token in presentation for token in feminine_tokens):
            return "1girl"
        if any(token in presentation for token in masculine_tokens):
            return "1boy"
        return "one person"

    @staticmethod
    def _normalized_png(data: bytes) -> tuple[bytes, int, int]:
        try:
            with Image.open(io.BytesIO(data)) as source:
                image = source.convert("RGB")
                width, height = image.size
                output = io.BytesIO()
                image.save(output, format="PNG", optimize=True)
        except (UnidentifiedImageError, OSError, ValueError) as error:
            raise KeyframeGenerationError(
                "Character design provider returned an unreadable image."
            ) from error
        if width <= 0 or height <= 0:
            raise KeyframeGenerationError(
                "Character design provider returned invalid image dimensions."
            )
        return output.getvalue(), width, height

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
            raise ValueError("Character design storage key must be portable.")
        return path.as_posix()
