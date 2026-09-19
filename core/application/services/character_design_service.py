"""Generate unapproved character design candidates."""

from __future__ import annotations

import hashlib
import io
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from PIL import Image, UnidentifiedImageError

from core.application.services.character_identity_prompt_service import (
    CharacterIdentityPromptService,
)
from core.application.services.production_manifest_service import ProductionManifestService
from core.domain.exceptions import KeyframeGenerationError, StorageError
from core.domain.ports.keyframe_generation_port import KeyframeGenerationPort
from core.domain.ports.storage_port import StoragePort
from core.domain.value_objects.character_creation_brief import CharacterCreationBrief
from core.domain.value_objects.character_design import (
    CharacterDesignCandidate,
    CharacterDesignCandidatePack,
    CharacterViewQuarantineArtifact,
)
from core.domain.value_objects.character_view_qc import CharacterViewQcReport
from core.domain.value_objects.keyframe_generation_request import KeyframeGenerationRequest


async def _single_chunk(data: bytes):
    yield data


class _OfflineFakeViewQualityGate:
    """Deterministic QC evidence used only with the explicit fake generator."""

    async def evaluate(self, *, image_bytes: bytes, view: str, seed: int, signature_marks=()) -> CharacterViewQcReport:
        del image_bytes, signature_marks
        orientation = {
            "FACE_CLOSEUP": "front",
            "FRONT": "front",
            "PROFILE_LEFT": "profile_left",
            "PROFILE_RIGHT": "profile_right",
            "THREE_QUARTER_LEFT": "three_quarter_left",
            "THREE_QUARTER_RIGHT": "three_quarter_right",
            "BACK": "back",
        }[view]
        from core.domain.value_objects.character_view_qc import CharacterViewObservation

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
            checks={
                "exactly_one_person": True,
                "head_inside_frame": True,
                "feet_inside_frame": True,
                "expected_orientation": True,
                "back_view_no_face": True,
                "signature_mark_face_closeup": True,
                "framing": True,
            },
        )

    async def evaluate_design_candidate(
        self, *, image_bytes: bytes, seed: int, signature_marks=(), face_priority: bool = False
    ) -> CharacterViewQcReport:
        del signature_marks, face_priority
        return await self.evaluate(image_bytes=image_bytes, view="FRONT", seed=seed)


class CharacterDesignService:
    """Provider-neutral candidate-generation stage of the character engine."""

    def __init__(
        self,
        generator: KeyframeGenerationPort,
        storage: StoragePort,
        quality_gate=None,
        *,
        max_view_attempts: int = 3,
        production_manifest: ProductionManifestService | None = None,
        acceptance_dir: Path | str | None = None,
        prompt_service: CharacterIdentityPromptService | None = None,
        drift_service=None,
    ) -> None:
        if not 1 <= max_view_attempts <= 10:
            raise ValueError("View generation attempts must be between 1 and 10.")
        self._generator = generator
        self._storage = storage
        self._prompt_service = prompt_service or CharacterIdentityPromptService()
        self._drift_service = drift_service
        self._quality_gate = quality_gate
        if self._quality_gate is None and generator.name.startswith("fake:"):
            self._quality_gate = _OfflineFakeViewQualityGate()
        self._max_view_attempts = max_view_attempts
        # Kept as dependency data for callers migrating to the view-pack service.
        self._production_manifest = production_manifest
        self._acceptance_dir = Path(acceptance_dir) if acceptance_dir is not None else None

    async def import_candidate(
        self,
        brief: CharacterCreationBrief,
        image_path: str | Path,
        *,
        output_prefix: str = "characters",
        run_id: str | None = None,
    ) -> CharacterDesignCandidatePack:
        """Register a supplied front-view image without redrawing it.

        The image remains an unapproved candidate. Canonical approval is the
        only step allowed to lock it as the identity source.
        """
        source = Path(image_path)
        if not source.is_file():
            raise FileNotFoundError(f"Provided character image was not found: {source}")
        prefix = self._portable_key(output_prefix)
        selected_run_id = (run_id or uuid.uuid4().hex[:12]).strip()
        if (
            not selected_run_id
            or self._portable_key(selected_run_id) != selected_run_id
            or "/" in selected_run_id
        ):
            raise ValueError("Character design run_id must be one portable path segment.")
        if self._quality_gate is None:
            raise RuntimeError("Character design QC is not configured; refusing to persist candidates.")
        image_bytes, width, height = self._normalized_png(source.read_bytes())
        digest = hashlib.sha256(image_bytes).hexdigest()
        report = await self._quality_gate.evaluate_design_candidate(
            image_bytes=image_bytes,
            seed=0,
            signature_marks=brief.signature_marks,
            face_priority=False,
        )
        if not report.passed:
            raise KeyframeGenerationError(
                "Provided character image failed structural QC: "
                + ", ".join(report.reasons)
            )
        root = f"{prefix}/{brief.character_id}/designs/{brief.content_hash}/runs/{selected_run_id}"
        storage_key = f"{root}/candidates/provided-{digest[:12]}.png"
        await self._save_locked_asset(storage_key, image_bytes, digest)
        candidate = CharacterDesignCandidate(
            storage_key=storage_key,
            content_hash=digest,
            seed=0,
            provider="human:provided-image",
            provider_asset_id=f"provided:{digest[:12]}",
            width=width,
            height=height,
            run_id=selected_run_id,
            source_type="PROVIDED_IMAGE",
            prompt_hash="",
            workflow_hash="",
            qc_report=report.to_dict(),
        )
        pack = CharacterDesignCandidatePack(
            schema_version=1,
            character_id=brief.character_id,
            brief_hash=brief.content_hash,
            candidates=(candidate,),
            run_id=selected_run_id,
        )
        await self._persist_design_run_manifest(
            root=root,
            brief=brief,
            run_id=selected_run_id,
            candidates=[candidate],
            attempts=[{
                "candidate_index": 1,
                "attempt": 1,
                "seed": 0,
                "content_hash": digest,
                "provider_asset_id": candidate.provider_asset_id,
                "storage_key": storage_key,
                "source_type": candidate.source_type,
                "state": "QC_PASSED",
                "qc_report": report.to_dict(),
            }],
            status="PENDING_HUMAN_REVIEW",
            style_reference=None,
        )
        return pack

    async def generate_candidates(
        self,
        brief: CharacterCreationBrief,
        *,
        count: int = 5,
        output_prefix: str = "characters",
        run_id: str | None = None,
        style_reference_path: str | Path | None = None,
        style_weight: float = 0.35,
    ) -> CharacterDesignCandidatePack:
        if not 1 <= count <= 8:
            raise ValueError("Character design candidate count must be between 1 and 8.")
        if style_reference_path is not None and not 0.0 < style_weight <= 1.0:
            raise ValueError("style_weight must be between 0 and 1.")
        prefix = self._portable_key(output_prefix)
        selected_run_id = (run_id or uuid.uuid4().hex[:12]).strip()
        if (
            not selected_run_id
            or self._portable_key(selected_run_id) != selected_run_id
            or "/" in selected_run_id
        ):
            raise ValueError("Character design run_id must be one portable path segment.")
        if self._quality_gate is None:
            raise RuntimeError("Character design QC is not configured; refusing to persist candidates.")

        base_seed = int(brief.content_hash[:8], 16)
        candidates: list[CharacterDesignCandidate] = []
        attempts: list[dict[str, object]] = []
        design_root = (
            f"{prefix}/{brief.character_id}/designs/{brief.content_hash}/"
            f"runs/{selected_run_id}"
        )
        run_manifest_key = f"{design_root}/run-manifest.json"
        if await self._storage.exists(run_manifest_key):
            raise ValueError(f"Character design run_id '{selected_run_id}' already exists.")

        style_reference: dict[str, object] | None = None
        if style_reference_path is not None:
            raw_style_bytes = Path(style_reference_path).read_bytes()
            style_bytes, _style_width, _style_height = self._normalized_png(raw_style_bytes)
            style_digest = hashlib.sha256(style_bytes).hexdigest()
            style_key = f"{design_root}/style/{style_digest[:12]}.png"
            if not await self._storage.exists(style_key):
                stored_style = await self._storage.save(style_key, style_bytes, "image/png")
                if stored_style.key != style_key:
                    raise StorageError("Storage adapter returned a different style-seed key.")
            style_reference = {
                "content_hash": style_digest,
                "storage_key": style_key,
                "weight": style_weight,
            }
        await self._persist_design_run_manifest(
            root=design_root,
            brief=brief,
            run_id=selected_run_id,
            candidates=candidates,
            attempts=attempts,
            status="IN_PROGRESS",
            style_reference=style_reference,
        )
        style_conditioning = (
            None
            if style_reference is None
            else (
                str(style_reference["storage_key"]),
                str(style_reference["content_hash"]),
                float(style_reference["weight"]),
            )
        )
        for index in range(count):
            accepted: CharacterDesignCandidate | None = None
            for attempt in range(1, self._max_view_attempts + 1):
                seed = base_seed + index * 10_000 + (attempt - 1) * 1_000
                request = self._prompt_service.build_design_request(
                    brief,
                    seed=seed,
                    variant=index + 1,
                    style_reference=style_conditioning,
                )
                prompt_hash = self._request_hash(request)
                generated = await self._generator.generate_keyframe(request)
                image_bytes, width, height = self._normalized_png(generated.image_bytes)
                digest = hashlib.sha256(image_bytes).hexdigest()
                gate_kwargs = {
                    "image_bytes": image_bytes,
                    "seed": seed,
                    "signature_marks": brief.signature_marks,
                }
                if brief.style_preset.casefold() == "selma-anime-v3-face":
                    gate_kwargs["face_priority"] = True
                report = await self._quality_gate.evaluate_design_candidate(**gate_kwargs)
                if not report.passed:
                    quarantine = await self._quarantine_view(
                        root=design_root,
                        view=f"DESIGN_{index + 1:02d}",
                        seed=seed,
                        attempt=attempt,
                        image_bytes=image_bytes,
                        content_hash=digest,
                        report=report,
                        forensic_evidence={
                            "brief_hash": brief.content_hash,
                            "brief": brief.to_dict(),
                            "prompt": request.visual_constraints.get("prompt", ""),
                            "negative_prompts": list(request.negative_prompts),
                            "request": request.to_dict(),
                            "prompt_hash": prompt_hash,
                            "workflow_hash": str(generated.metadata.get("workflow_hash", "")),
                            "model_hashes": generated.metadata.get("model_hashes", {}),
                            "model_checkpoint": generated.metadata.get("model_checkpoint", ""),
                            "provider_asset_id": generated.provider_asset_id,
                            "state_reason_codes": list(report.reasons),
                        },
                    )
                    attempts.append(
                        {
                            "candidate_index": index + 1,
                            "attempt": attempt,
                            "seed": seed,
                            "content_hash": digest,
                            "brief_hash": brief.content_hash,
                            "brief": brief.to_dict(),
                            "prompt": request.visual_constraints.get("prompt", ""),
                            "negative_prompts": list(request.negative_prompts),
                            "request": request.to_dict(),
                            "prompt_hash": prompt_hash,
                            "workflow_hash": str(generated.metadata.get("workflow_hash", "")),
                            "model_hashes": generated.metadata.get("model_hashes", {}),
                            "model_checkpoint": generated.metadata.get("model_checkpoint", ""),
                            "provider_asset_id": generated.provider_asset_id,
                            "storage_key": quarantine.image_storage_key,
                            "state": "QUARANTINED",
                            "state_reason_codes": list(report.reasons),
                            "qc_report": report.to_dict(),
                        }
                    )
                    continue
                storage_key = f"{design_root}/candidates/design-{index + 1:02d}-{digest[:12]}.png"
                stored = await self._storage.save(storage_key, image_bytes, "image/png")
                if stored.key != storage_key:
                    raise StorageError("Storage adapter returned a different design candidate key.")
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
                    style_reference=style_reference,
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
            style_reference=style_reference,
        )
        return pack

    def _legacy_view_pack_services(self):
        """Build the compatibility façade used by older in-process callers.

        The production container wires these services explicitly. Keeping this
        narrow adapter lets legacy tests and library callers migrate without
        restoring the old implementation inside the design generator.
        """
        from core.application.services.character_canonical_approval_service import (
            CharacterCanonicalApprovalService,
        )
        from core.application.services.character_view_pack_approval_service import (
            CharacterViewPackApprovalService,
        )
        from core.application.services.character_view_pack_asset_service import (
            CharacterViewPackAssetService,
        )
        from core.application.services.character_view_pack_generation_service import (
            CharacterViewPackGenerationService,
        )

        approval_service = CharacterViewPackApprovalService(
            self._storage,
            acceptance_dir=self._acceptance_dir,
        )
        legacy_pose_template_keys = {
            "PROFILE_LEFT": "characters/_pose_templates/pose_profile_left.png",
            "PROFILE_RIGHT": "characters/_pose_templates/pose_profile_right.png",
            "BACK": "characters/_pose_templates/pose_back.png",
        }
        legacy_pose_template_sources = {
            "PROFILE_LEFT": "pose_profile_left.png",
            "PROFILE_RIGHT": "pose_profile_right.png",
            "BACK": "pose_back.png",
        }
        asset_service = CharacterViewPackAssetService(
            self._storage,
            production_manifest=self._production_manifest,
            pose_template_keys=legacy_pose_template_keys,
            pose_template_sources=legacy_pose_template_sources,
        )
        generation_service = CharacterViewPackGenerationService(
            self._generator,
            self._storage,
            quality_gate=self._quality_gate,
            max_view_attempts=self._max_view_attempts,
            production_manifest=self._production_manifest,
            prompt_service=self._prompt_service,
            approval_service=approval_service,
            asset_service=asset_service,
            pose_template_keys=legacy_pose_template_keys,
            pose_template_sources=legacy_pose_template_sources,
            legacy_reference_policy=True,
            drift_service=self._drift_service,
        )
        canonical_service = CharacterCanonicalApprovalService(
            self._storage,
            production_manifest=self._production_manifest,
        )
        return canonical_service, generation_service

    async def approve_candidate(
        self,
        brief: CharacterCreationBrief,
        candidate: CharacterDesignCandidate,
        *,
        approved_by: str,
        character_version: int = 1,
        output_prefix: str = "characters",
        brief_consistency_confirmed: bool = False,
    ):
        canonical_service, _generation_service = self._legacy_view_pack_services()
        return await canonical_service.approve_candidate(
            brief,
            candidate,
            approved_by=approved_by,
            character_version=character_version,
            output_prefix=output_prefix,
            brief_consistency_confirmed=brief_consistency_confirmed,
        )

    async def generate_dual_anchors(self, *args, **kwargs):
        canonical_service, _generation_service = self._legacy_view_pack_services()
        return await canonical_service.generate_dual_anchors(*args, **kwargs)

    async def generate_reference_drafts(
        self,
        brief: CharacterCreationBrief,
        approval,
        *,
        output_prefix: str = "characters",
        view_candidate_count: int | None = None,
        rerender_views=None,
    ):
        _canonical_service, generation_service = self._legacy_view_pack_services()
        return await generation_service.generate_canonical_views(
            brief,
            approval,
            output_prefix=output_prefix,
            view_candidate_count=view_candidate_count,
            rerender_views=rerender_views,
        )

    async def generate_canonical_views(
        self,
        brief: CharacterCreationBrief,
        approval,
        *,
        output_prefix: str = "characters",
        view_candidate_count: int | None = None,
        rerender_views=None,
    ):
        return await self.generate_reference_drafts(
            brief,
            approval,
            output_prefix=output_prefix,
            view_candidate_count=view_candidate_count,
            rerender_views=rerender_views,
        )

    async def restore_superseded_views(
        self,
        brief: CharacterCreationBrief,
        approval,
        *,
        views,
        restored_by: str,
        reason: str = "",
        output_prefix: str = "characters",
    ):
        """Put a targeted re-render back to the render the human preferred."""
        _canonical_service, generation_service = self._legacy_view_pack_services()
        return await generation_service.restore_superseded_views(
            brief,
            approval,
            views=views,
            restored_by=restored_by,
            reason=reason,
            output_prefix=output_prefix,
        )

    async def approve_view_pack(self, **kwargs):
        _canonical_service, generation_service = self._legacy_view_pack_services()
        return await generation_service.approve_view_pack(**kwargs)

    async def require_view_pack_approval(self, **kwargs):
        _canonical_service, generation_service = self._legacy_view_pack_services()
        return await generation_service.require_view_pack_approval(**kwargs)

    async def load_approved_view_pack(self, **kwargs):
        _canonical_service, generation_service = self._legacy_view_pack_services()
        return await generation_service.load_approved_view_pack(**kwargs)

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
        style_reference: dict[str, object] | None = None,
    ) -> None:
        payload = {
            "schema_version": 1,
            "character_id": brief.character_id,
            "brief_hash": brief.content_hash,
            "run_id": run_id,
            "status": status,
            "failure": failure or None,
            "style_reference": style_reference,
            "candidates": [candidate.to_dict() for candidate in candidates],
            "attempts": attempts,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        data = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
        await self._storage.save_stream(f"{root}/run-manifest.json", _single_chunk(data), "application/json")

    async def _save_locked_asset(
        self, storage_key: str, data: bytes, content_hash: str
    ) -> None:
        if await self._storage.exists(storage_key):
            if hashlib.sha256(await self._storage.load(storage_key)).hexdigest() != content_hash:
                raise ValueError(f"Character asset '{storage_key}' is already locked to other bytes.")
            return
        stored = await self._storage.save(storage_key, data, "image/png")
        if stored.key != storage_key:
            raise StorageError("Storage adapter returned a different character asset key.")

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
        forensic_evidence: dict[str, object] | None = None,
    ) -> CharacterViewQuarantineArtifact:
        reason = report.reasons[0] if report.reasons else "unknown"
        reason = "".join(character if character.isalnum() or character in "-_" else "-" for character in reason)[:80]
        stem = f"{view.casefold()}_seed{seed}_fail_{reason}_{content_hash[:12]}"
        image_key = f"{root}/quarantine/{stem}.png"
        report_key = f"{root}/quarantine/{stem}.json"
        await self._save_locked_asset(image_key, image_bytes, content_hash)
        payload = {
            "schema_version": 1,
            "attempt": attempt,
            "content_hash": content_hash,
            "state_reason_codes": list(report.reasons),
            **(forensic_evidence or {}),
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

    @staticmethod
    def _request_hash(request: KeyframeGenerationRequest) -> str:
        payload = json.dumps(request.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    async def _save_locked_asset(
        self,
        storage_key: str,
        data: bytes,
        content_hash: str,
        *,
        content_type: str = "image/png",
    ) -> None:
        if await self._storage.exists(storage_key):
            existing_hash = hashlib.sha256(await self._storage.load(storage_key)).hexdigest()
            if existing_hash != content_hash:
                raise ValueError(f"Character asset '{storage_key}' is already locked to other bytes.")
            return
        stored = await self._storage.save(storage_key, data, content_type)
        if stored.key != storage_key:
            raise StorageError("Storage adapter returned a different character asset key.")

    @staticmethod
    def _normalized_png(data: bytes) -> tuple[bytes, int, int]:
        try:
            with Image.open(io.BytesIO(data)) as source:
                image = source.convert("RGB")
                width, height = image.size
                output = io.BytesIO()
                image.save(output, format="PNG", optimize=True)
        except (UnidentifiedImageError, OSError, ValueError) as error:
            raise KeyframeGenerationError("Character design provider returned an unreadable image.") from error
        if width <= 0 or height <= 0:
            raise KeyframeGenerationError("Character design provider returned invalid image dimensions.")
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
