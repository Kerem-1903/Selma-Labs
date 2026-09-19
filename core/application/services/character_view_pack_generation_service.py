"""Canonical turnaround generation and view-pack production orchestration."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Collection, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import ClassVar

from core.application.services.character_identity_prompt_service import (
    CharacterIdentityPromptService,
    edit_canvas_for,
)
from core.application.services.character_turnaround_drift_service import (
    CharacterTurnaroundDriftService,
)
from core.application.services.character_view_pack_approval_service import CharacterViewPackApprovalService
from core.application.services.character_view_pack_asset_service import CharacterViewPackAssetService
from core.application.services.production_manifest_service import ProductionManifestService
from core.domain.value_objects.character_identity_contract import CharacterIdentityContract
from core.domain.value_objects.character_view_consistency_qc import CharacterViewConsistencyQc
from core.domain.exceptions import KeyframeGenerationError, StorageError
from core.domain.services.turnaround_view_policy import (
    EDIT_TURNAROUND_FIXED_VIEWS,
    edit_turnaround_dependencies,
    edit_turnaround_production_order,
)
from core.domain.ports.keyframe_generation_port import KeyframeGenerationPort
from core.domain.ports.storage_port import StoragePort
from core.domain.value_objects.character_creation_brief import CharacterCreationBrief
from core.domain.value_objects.character_design import (
    CharacterAnchorArtifact,
    CharacterCanonicalApproval,
    CharacterReferenceDraft,
    CharacterReferenceDraftPack,
    CharacterViewPackApproval,
    CharacterViewQuarantineArtifact,
)
from core.domain.value_objects.character_view_qc import CharacterViewObservation, CharacterViewQcReport


class _OfflineFakeViewQualityGate:
    """Deterministic structural evidence used only with the explicit fake provider."""

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


async def _single_chunk(data: bytes):
    yield data


@dataclass(frozen=True)
class _ViewCandidate:
    """One rendered seed for a view, before it is accepted or quarantined."""

    slot: int
    seed: int
    image_bytes: bytes
    width: int
    height: int
    digest: str
    report: CharacterViewQcReport
    provider_asset_id: str
    model_checkpoint: str
    generation_metadata: dict[str, object]
    drift_metrics: dict[str, object] | None = None


@dataclass(frozen=True)
class _InheritedView:
    """A human-approved artifact that stands in for a generated view.

    FACE_CLOSEUP always comes from the approved face anchor; in the source-led
    edit dialect FRONT comes from the approved canonical image itself, so the
    turnaround never regenerates the one view a human already signed off on.
    """

    storage_key: str
    content_hash: str
    seed: int
    provider_asset_id: str
    model_checkpoint: str
    workflow_version: str
    model_hashes: dict[str, str] | None = None
    prompt_hash: str = ""
    workflow_hash: str = ""
    human_approved: bool = False

    @classmethod
    def from_anchor(cls, anchor: CharacterAnchorArtifact) -> "_InheritedView":
        return cls(
            storage_key=anchor.storage_key,
            content_hash=anchor.content_hash,
            seed=anchor.seed,
            provider_asset_id=anchor.provider_asset_id,
            model_checkpoint=anchor.model_checkpoint,
            workflow_version=anchor.workflow_version,
            model_hashes=dict(anchor.model_hashes or {}),
            prompt_hash=anchor.prompt_hash,
            workflow_hash=anchor.workflow_hash,
        )


class CharacterViewPackGenerationService:
    """Generate the seven canonical views while delegating asset concerns."""

    _VIEW_WORKFLOW_VERSION = "canonical-views-v2-direction-control"
    _EDIT_VIEW_WORKFLOW_VERSION = "canonical-views-v3-source-led-edit"
    _ANCHOR_WORKFLOW_VERSION = "dual-anchor-v2-deterministic"
    _STANDARD_PRODUCTION_ORDER = (
        "FACE_CLOSEUP",
        "FRONT",
        "PROFILE_LEFT",
        "PROFILE_RIGHT",
        "THREE_QUARTER_LEFT",
        "THREE_QUARTER_RIGHT",
        "BACK",
    )
    #: Source-led edit order. Each wing is derived from the approved source so a
    #: left/right error cannot propagate across the body, and BACK can see both
    #: profiles because the bag only reads correctly from the character's right.
    _EDIT_PRODUCTION_ORDER = edit_turnaround_production_order()
    _EDIT_FIXED_VIEWS = EDIT_TURNAROUND_FIXED_VIEWS
    _STANDARD_VIEWS = (
        ("FRONT", "strict front view, full body neutral standing character reference, complete silhouette, entire head and both feet visible"),
        ("FACE_CLOSEUP", "front-facing close-up headshot, neutral expression, face and complete hair visible"),
        ("PROFILE_LEFT", "strict left side profile, full body neutral standing character reference, nose points to the left edge, only one eye visible, shoulders and hips overlap in silhouette, entire head and both feet visible"),
        ("PROFILE_RIGHT", "strict right side profile, unmistakable right-facing full body neutral standing character reference, nose and chin point to the right edge of the image, back of head remains on the left, only one eye visible, shoulders and hips overlap in silhouette, entire head and both feet visible"),
        ("THREE_QUARTER_LEFT", "left three-quarter view, full body neutral standing character reference, entire head and both feet visible"),
        ("THREE_QUARTER_RIGHT", "unmistakable right-facing three-quarter view, nose and chin point to the right edge of the image, back of head remains on the left, full body neutral standing character reference, entire head and both feet visible"),
        ("BACK", "strict rear-facing back view, unmistakable back of head and complete back silhouette, face fully turned away from camera, no face, no eyes, no nose, wide full-body neutral standing pose, generous empty margin above the head and below both feet, subject occupies at most 78 percent of frame height"),
    )
    _POSE_TEMPLATE_KEYS: ClassVar[dict[str, str]] = {
        "PROFILE_LEFT": "characters/_pose_templates/pose_profile_left.png",
        "PROFILE_RIGHT": "characters/_pose_templates/pose_profile_right.png",
        "BACK": "characters/_pose_templates/pose_back_v5.png",
    }

    def __init__(
        self,
        generator: KeyframeGenerationPort,
        storage: StoragePort,
        quality_gate=None,
        *,
        max_view_attempts: int = 3,
        production_manifest: ProductionManifestService | None = None,
        prompt_service: CharacterIdentityPromptService | None = None,
        approval_service: CharacterViewPackApprovalService | None = None,
        asset_service: CharacterViewPackAssetService | None = None,
        acceptance_dir: Path | str | None = None,
        pose_template_keys: dict[str, str] | None = None,
        pose_template_sources: dict[str, str] | None = None,
        legacy_reference_policy: bool = False,
        edit_dialect: bool = False,
        drift_service: CharacterTurnaroundDriftService | None = None,
        view_candidate_count: int = 1,
    ) -> None:
        if not 1 <= max_view_attempts <= 10:
            raise ValueError("View generation attempts must be between 1 and 10.")
        if not 1 <= view_candidate_count <= 6:
            raise ValueError("View candidate count must be between 1 and 6.")
        self._generator = generator
        self._storage = storage
        self._quality_gate = quality_gate
        if self._quality_gate is None and generator.name.startswith("fake:"):
            self._quality_gate = _OfflineFakeViewQualityGate()
        self._max_view_attempts = max_view_attempts
        self._pose_template_keys = dict(pose_template_keys or self._POSE_TEMPLATE_KEYS)
        self._legacy_reference_policy = legacy_reference_policy
        self._edit_dialect = edit_dialect
        self._drift_service = drift_service
        self._view_candidate_count = view_candidate_count
        self._production_manifest = production_manifest
        self._prompt_service = prompt_service or CharacterIdentityPromptService()
        self._asset_service = asset_service or CharacterViewPackAssetService(
            storage,
            production_manifest=production_manifest,
            pose_template_keys=pose_template_keys,
            pose_template_sources=pose_template_sources,
        )
        self._approval_service = approval_service or CharacterViewPackApprovalService(
            storage, acceptance_dir=acceptance_dir
        )

    async def generate_canonical_views(
        self,
        brief: CharacterCreationBrief,
        approval: CharacterCanonicalApproval,
        *,
        output_prefix: str = "characters",
        view_candidate_count: int | None = None,
        rerender_views: Collection[str] | None = None,
    ) -> CharacterReferenceDraftPack:
        candidates = (
            self._view_candidate_count
            if view_candidate_count is None
            else view_candidate_count
        )
        if not 1 <= candidates <= 6:
            raise ValueError("View candidate count must be between 1 and 6.")
        targets = tuple(
            dict.fromkeys(str(view).strip().upper() for view in (rerender_views or ()))
        )
        relative_root = f"{self._portable_key(output_prefix)}/{brief.character_id}/v{approval.character_version}"
        # The bytes each render may overwrite, keyed by the key it overwrites.
        # The loop replaces images as it goes and the pack manifest is written
        # last, so a failure in between would leave a pack whose recorded hashes
        # no longer match its images -- and such a pack refuses to load at all.
        restore_journal: dict[str, bytes] = {}
        if self._production_manifest is None:
            try:
                return await self._generate_unlocked(
                    brief,
                    approval,
                    output_prefix=output_prefix,
                    view_candidate_count=candidates,
                    rerender_views=targets,
                    restore_journal=restore_journal,
                )
            except Exception:
                await self._restore_replaced_views(restore_journal)
                raise
        with self._production_manifest.work_lock(relative_root):
            self._production_manifest.initialize(relative_root=relative_root)
            try:
                return await self._generate_unlocked(
                    brief,
                    approval,
                    output_prefix=output_prefix,
                    view_candidate_count=candidates,
                    rerender_views=targets,
                    restore_journal=restore_journal,
                )
            except Exception as error:
                await self._restore_replaced_views(restore_journal)
                status = "BLOCKED_PREFLIGHT" if "BLOCKED_PREFLIGHT" in str(error) else "FAILED"
                self._production_manifest.finalize(relative_root=relative_root, status=status)
                raise

    async def _restore_replaced_views(self, restore_journal: Mapping[str, bytes]) -> None:
        """Put back every render a failed re-render had already overwritten.

        Called only on the failure path: a half-applied re-render is worse than
        a failed one, and the error still reaches the operator.
        """
        for storage_key, data in restore_journal.items():
            await self._storage.save(storage_key, data, "image/png")

    async def _generate_unlocked(
        self,
        brief: CharacterCreationBrief,
        approval: CharacterCanonicalApproval,
        *,
        output_prefix: str,
        view_candidate_count: int,
        rerender_views: tuple[str, ...] = (),
        restore_journal: dict[str, bytes] | None = None,
    ) -> CharacterReferenceDraftPack:
        if approval.character_id != brief.character_id:
            raise ValueError("Canonical approval belongs to another character.")
        if approval.brief_hash != brief.content_hash:
            raise ValueError("Canonical approval belongs to another character brief.")
        if approval.identity_source_hash and approval.identity_source_hash != approval.canonical_content_hash:
            raise ValueError("Canonical identity source hash does not match the locked image.")
        if approval.identity_contract_hash and approval.identity_contract_hash != CharacterIdentityContract.from_brief(brief).content_hash:
            raise ValueError("Canonical identity contract does not match the confirmed brief.")
        if approval.identity_source == "PROVIDED_IMAGE" and not approval.brief_consistency_confirmed:
            raise ValueError("Provided canonical image requires explicit brief consistency confirmation.")
        if not await self._storage.exists(approval.canonical_storage_key):
            raise StorageError(f"Canonical design '{approval.canonical_storage_key}' was not found.")
        canonical = await self._storage.load(approval.canonical_storage_key)
        if hashlib.sha256(canonical).hexdigest() != approval.canonical_content_hash:
            raise ValueError("Canonical design changed after human approval.")
        if not approval.anchors_locked:
            raise ValueError("Canonical approval does not contain locked dual anchors.")
        assert approval.face_anchor is not None
        assert approval.fullbody_anchor is not None
        await self._asset_service.verify_anchor(approval.face_anchor)
        await self._asset_service.verify_anchor(approval.fullbody_anchor)
        if self._quality_gate is None:
            raise RuntimeError("Character view QC is not configured; refusing to persist generated views.")
        if not self._edit_dialect:
            await self._asset_service.ensure_pose_templates()

        root = f"{self._portable_key(output_prefix)}/{brief.character_id}/v{approval.character_version}"
        base_seed = int(brief.content_hash[8:16], 16)
        drift_for_brief = self._drift_for(brief)
        directions = dict(self._STANDARD_VIEWS)
        face, fullbody = approval.face_anchor, approval.fullbody_anchor
        edit_canvas = await self._edit_canvas(approval)
        drafts: list[CharacterReferenceDraft] = []
        quarantined: list[CharacterViewQuarantineArtifact] = []
        blocked_views: dict[str, tuple[str, ...]] = {}
        produced: dict[str, CharacterReferenceDraft] = {}
        existing_pack = await self._load_existing_view_pack(root=root, brief=brief, approval=approval)
        existing_by_view = {draft.view: draft for draft in (existing_pack.drafts if existing_pack else ())}
        if existing_pack is not None:
            drafts.extend(existing_pack.drafts)
            quarantined.extend(existing_pack.quarantined)

        production_order = (
            self._EDIT_PRODUCTION_ORDER
            if self._edit_dialect
            else self._STANDARD_PRODUCTION_ORDER
        )
        # A targeted re-render deliberately skips the short-circuit below: the
        # whole point is to draw the named views again inside a pack that would
        # otherwise be handed back untouched.
        if rerender_views:
            await self._retire_views_for_rerender(
                root=root,
                views=rerender_views,
                production_order=production_order,
                existing_by_view=existing_by_view,
                drafts=drafts,
                quarantined=quarantined,
                base_seed=base_seed,
                has_existing_pack=existing_pack is not None,
                restore_journal=restore_journal if restore_journal is not None else {},
            )
        elif existing_pack is not None and existing_pack.status in {"PENDING_HUMAN_REVIEW", "APPROVED", "READY"}:
            return existing_pack
        for index, view in enumerate(production_order):
            existing = existing_by_view.get(view)
            if existing is not None:
                produced[view] = existing
                continue
            previous_attempts = max((item.attempt for item in quarantined if item.view == view), default=0)
            try:
                references = self._view_conditioning_references(
                    view=view,
                    approval=approval,
                    face_anchor=face,
                    fullbody_anchor=fullbody,
                    produced=produced,
                )
            except ValueError as error:
                # One failed view must not cost the whole run: the remaining
                # views are still rendered, measured, and shown to the human.
                blocked_views[view] = ("blocked_by_reference", str(error))
                continue
            accepted: CharacterReferenceDraft | None = None
            # Views that are copied from an approved artifact by contract -- the
            # canonical front image and the locked face anchor -- have nothing to
            # choose between, so a seed sweep there spends GPU renders on output
            # that is discarded. Sweep only the views that are actually drawn.
            inherited_source = self._inherited_view(
                view=view, approval=approval, face=face, fullbody=fullbody
            )
            slots_to_render = 1 if inherited_source is not None else view_candidate_count
            for attempt in range(previous_attempts + 1, previous_attempts + self._max_view_attempts + 1):
                candidates: list[_ViewCandidate] = []
                for slot in range(slots_to_render):
                    inherited = inherited_source if (slot == 0 and attempt == 1) else None
                    seed = (
                        inherited.seed
                        if inherited is not None and attempt == 1
                        else base_seed
                        + index * 10_000
                        + (attempt - 1) * 1_000
                        + slot * 101
                    )
                    if inherited is not None and attempt == 1:
                        raw_bytes = await self._storage.load(inherited.storage_key)
                        provider_asset_id = inherited.provider_asset_id
                        model_checkpoint = inherited.model_checkpoint
                        generation_metadata: dict[str, object] = {
                            "model_hashes": dict(inherited.model_hashes or {}),
                            "render_duration_sec": 0.0,
                            "peak_vram_mb": None,
                            "prompt_hash": inherited.prompt_hash,
                            "workflow_hash": inherited.workflow_hash,
                        }
                    else:
                        pose_key = (
                            ""
                            if self._edit_dialect
                            else self._pose_template_keys.get(view, "")
                        )
                        if pose_key and not await self._storage.exists(pose_key):
                            raise StorageError(f"Pose template '{pose_key}' for view {view} is missing.")
                        request = self._prompt_service.build_reference_request(brief, view=view, direction=directions[view], seed=seed, references=references, pose_storage_key=pose_key, canvas=edit_canvas)
                        generated = await self._generator.generate_keyframe(request)
                        raw_bytes = generated.image_bytes
                        provider_asset_id = generated.provider_asset_id
                        model_checkpoint = str(generated.metadata.get("model_checkpoint") or self._generator.name)
                        generation_metadata = dict(generated.metadata)
                        generation_metadata.setdefault("prompt_hash", self._asset_service.request_hash(request))
                    image_bytes, width, height = self._asset_service.normalized_png(raw_bytes)
                    report = await self._quality_gate.evaluate(image_bytes=image_bytes, view=view, seed=seed, signature_marks=brief.signature_marks)
                    if (
                        inherited is not None
                        and attempt == 1
                        and (
                            inherited.human_approved
                            or inherited.workflow_version == self._ANCHOR_WORKFLOW_VERSION
                        )
                    ):
                        report = self._inherit_canonical_approval(report)
                    candidates.append(
                        _ViewCandidate(
                            slot=slot,
                            seed=seed,
                            image_bytes=image_bytes,
                            width=width,
                            height=height,
                            digest=hashlib.sha256(image_bytes).hexdigest(),
                            report=report,
                            provider_asset_id=provider_asset_id,
                            model_checkpoint=model_checkpoint,
                            generation_metadata=generation_metadata,
                        )
                    )
                blocked = [item for item in candidates if not item.report.passed]
                for item in blocked:
                    await self._quarantine_candidate(
                        root=root,
                        view=view,
                        attempt=attempt,
                        candidate=item,
                        references=references,
                        quarantined=quarantined,
                    )
                passing = [item for item in candidates if item.report.passed]
                if not passing:
                    continue
                chosen, outranked = await self._select_view_candidate(
                    view=view,
                    approval=approval,
                    candidates=passing,
                    drift=drift_for_brief,
                )
                for item in outranked:
                    await self._quarantine_candidate(
                        root=root,
                        view=view,
                        attempt=attempt,
                        candidate=replace(
                            item,
                            report=replace(
                                item.report,
                                passed=False,
                                reasons=("advisory_drift_outranked_sibling_seed",),
                            ),
                        ),
                        references=references,
                        quarantined=quarantined,
                    )
                consistency_qc = self._build_consistency_qc(
                    brief=brief,
                    view=view,
                    references=references,
                )
                key = f"{root}/views/{view.casefold().replace('_', '-')}.png"
                await self._asset_service.save_locked_asset(
                    key,
                    chosen.image_bytes,
                    chosen.digest,
                    allow_replace=view in rerender_views,
                )
                qc_payload = chosen.report.to_dict()
                qc_payload["consistency_qc"] = consistency_qc.to_dict()
                if chosen.drift_metrics is not None:
                    qc_payload["advisory_drift"] = chosen.drift_metrics
                accepted = CharacterReferenceDraft(view=view, storage_key=key, content_hash=chosen.digest, seed=chosen.seed, width=chosen.width, height=chosen.height, conditioning_source_keys=tuple(item[1] for item in references), conditioning_source_hashes=tuple(item[2] for item in references), identity_reference_weights=tuple(item[3] for item in references), provider_asset_id=chosen.provider_asset_id, model_checkpoint=chosen.model_checkpoint, workflow_version=(self._EDIT_VIEW_WORKFLOW_VERSION if self._edit_dialect else self._VIEW_WORKFLOW_VERSION), qc_report=qc_payload, prompt_hash=str(chosen.generation_metadata.get("prompt_hash", "")), workflow_hash=str(chosen.generation_metadata.get("workflow_hash", "")))
                drafts.append(accepted)
                produced[view] = accepted
                self._asset_service.record_manifest_asset(root=root, asset_id=f"{view}:attempt-{attempt}-slot-{chosen.slot}", storage_key=key, content_hash=chosen.digest, seed=chosen.seed, reference_hashes=tuple(item[2] for item in references), report=chosen.report, generation_metadata=chosen.generation_metadata, state="QC_PASSED")
                break
            if accepted is None:
                blocked_views[view] = tuple(
                    sorted(
                        {
                            reason
                            for item in quarantined
                            if item.view == view
                            for reason in item.reasons
                        }
                    )
                ) or ("no_candidate_passed_qc",)
                continue
        return await self._persist_view_pack(
            root=root,
            brief=brief,
            approval=approval,
            drafts=drafts,
            quarantined=quarantined,
            blocked=blocked_views,
            status="BLOCKED" if blocked_views else "PENDING_HUMAN_REVIEW",
            allow_replace=bool(rerender_views),
        )

    async def approve_view_pack(self, **kwargs) -> CharacterViewPackApproval:
        return await self._approval_service.approve_view_pack(**kwargs)

    async def reject_view_pack(self, **kwargs):
        """Record a human refusal so this version can never be approved."""
        return await self._approval_service.reject_view_pack(**kwargs)

    async def require_view_pack_approval(self, **kwargs) -> CharacterViewPackApproval:
        return await self._approval_service.require_view_pack_approval(**kwargs)

    async def restore_superseded_views(
        self,
        brief: CharacterCreationBrief,
        approval: CharacterCanonicalApproval,
        *,
        views: Collection[str],
        restored_by: str,
        reason: str = "",
        output_prefix: str = "characters",
    ) -> CharacterReferenceDraftPack:
        """Put a targeted re-render back to the render the human preferred.

        Restoring is a byte operation, not a re-render. A seed is a pure
        function of the brief hash, the view index, the attempt and the slot,
        so asking the model for the same view again cannot return the frame the
        human was looking at; the bytes filed as quarantine evidence when the
        view was retired are the only copy of it.

        Nothing is written on trust. The archived bytes must still match the
        hash they were filed under, the render being displaced must still match
        its own record, the restored frame must still pass the view QC gate, and
        the manifest must still carry a record naming the model, prompt and
        workflow that produced it -- without which the pack could never be
        approved again. Any of those failing refuses the restore.
        """
        actor = restored_by.strip()
        if not actor:
            raise ValueError(
                "Restoring a view pack requires the human who decided it."
            )
        targets = tuple(dict.fromkeys(str(view).strip().upper() for view in views))
        if not targets:
            raise ValueError("Name at least one view to restore.")
        fixed = [view for view in targets if view in EDIT_TURNAROUND_FIXED_VIEWS]
        if fixed:
            raise ValueError(
                "These views are contract copies of the approved canonical "
                "artifact and are never drawn, so no render of them was ever "
                "superseded: " + ", ".join(fixed)
            )
        if self._production_manifest is None:
            raise RuntimeError(
                "View-pack restore needs the production manifest: without it the "
                "restored bytes carry no recorded provenance and the pack can no "
                "longer be approved."
            )
        root = (
            f"{self._portable_key(output_prefix)}/"
            f"{brief.character_id}/v{approval.character_version}"
        )
        restore_journal: dict[str, bytes] = {}
        with self._production_manifest.work_lock(root):
            self._production_manifest.initialize(relative_root=root)
            try:
                return await self._apply_restore(
                    brief=brief,
                    approval=approval,
                    root=root,
                    targets=targets,
                    actor=actor,
                    reason=reason,
                    restore_journal=restore_journal,
                )
            except Exception as error:
                # Images are swapped as the loop reaches them and the pack
                # manifest is written last, so a failure in between would leave
                # a pack whose recorded hashes no longer match its files -- a
                # pack that then refuses to load. Put the displaced renders
                # back before re-raising.
                await self._restore_replaced_views(restore_journal)
                status = (
                    "BLOCKED_PREFLIGHT"
                    if "BLOCKED_PREFLIGHT" in str(error)
                    else "FAILED"
                )
                self._production_manifest.finalize(relative_root=root, status=status)
                raise

    async def _apply_restore(
        self,
        *,
        brief: CharacterCreationBrief,
        approval: CharacterCanonicalApproval,
        root: str,
        targets: tuple[str, ...],
        actor: str,
        reason: str,
        restore_journal: dict[str, bytes],
    ) -> CharacterReferenceDraftPack:
        for verdict, message in (
            (
                "view-pack-approval.json",
                "This view pack is already approved; replacing its bytes now would "
                "leave the approval pointing at evidence that no longer exists. "
                "Produce a newer character version instead.",
            ),
            (
                "view-pack-rejection.json",
                "This view pack was rejected by a human, and a refusal is final "
                "for the version it names. Produce a newer character version "
                "instead.",
            ),
        ):
            if await self._storage.exists(f"{root}/{verdict}"):
                raise ValueError(message)
        existing = await self._load_existing_view_pack(
            root=root, brief=brief, approval=approval
        )
        if existing is None:
            raise ValueError(
                "Targeted restore needs an existing view pack to restore into."
            )
        production_order = (
            self._EDIT_PRODUCTION_ORDER
            if self._edit_dialect
            else self._STANDARD_PRODUCTION_ORDER
        )
        unknown = [view for view in targets if view not in production_order]
        if unknown:
            raise ValueError(
                "Unknown turnaround views: "
                + ", ".join(unknown)
                + ". Known views: "
                + ", ".join(production_order)
            )
        if self._quality_gate is None:
            raise RuntimeError(
                "Character view QC is not configured; refusing to restore a "
                "render that cannot be re-measured."
            )
        manifest_key = f"{root}/manifest.json"
        if not await self._storage.exists(manifest_key):
            raise StorageError(
                f"View-pack provenance manifest is missing: {manifest_key}"
            )
        manifest = json.loads((await self._storage.load(manifest_key)).decode("utf-8"))
        assets = manifest.get("assets") if isinstance(manifest, dict) else None
        if not isinstance(assets, list):
            raise TypeError("View-pack manifest must contain an asset list.")
        base_seed = int(brief.content_hash[8:16], 16)
        canonical = await self._storage.load(approval.canonical_storage_key)
        drift = self._drift_for(brief)
        drafts = list(existing.drafts)
        quarantined = list(existing.quarantined)
        restored: list[dict[str, object]] = []
        for view in targets:
            draft = next((item for item in drafts if item.view == view), None)
            if draft is None:
                raise ValueError(
                    f"View '{view}' has no accepted render in this pack, so none "
                    "was ever superseded."
                )
            # The newest displacement, because the archives are an undo stack:
            # a targeted re-render files the frame it replaced, and a restore
            # files the frame *it* replaces. So the same command both undoes a
            # re-render and undoes an undo, which is the only way back after a
            # human changes their mind twice. QC failures are never candidates:
            # those frames were rejected on merit, and re-measuring them would
            # refuse the restore anyway.
            archived = next(
                (
                    item
                    for item in reversed(quarantined)
                    if item.view == view
                    and tuple(item.reasons) in _SUPERSEDED_RENDER_REASONS
                ),
                None,
            )
            if archived is None:
                raise ValueError(
                    f"Nothing that displaced a render of view '{view}' has been "
                    "archived, so there is nothing to restore."
                )
            if draft.seed == archived.seed:
                raise ValueError(
                    f"View '{view}' already holds the archived render."
                )
            displaced_bytes = await self._storage.load(draft.storage_key)
            if hashlib.sha256(displaced_bytes).hexdigest() != draft.content_hash:
                raise ValueError(
                    f"Accepted view '{view}' changed on disk; refusing to "
                    "overwrite evidence that no longer matches its record."
                )
            archived_bytes = await self._storage.load(archived.image_storage_key)
            if hashlib.sha256(archived_bytes).hexdigest() != archived.content_hash:
                raise ValueError(
                    f"Archived render of '{view}' no longer matches the hash it "
                    "was filed under."
                )
            provenance = next(
                (
                    entry
                    for entry in assets
                    if isinstance(entry, dict)
                    and entry.get("storage_key") == draft.storage_key
                    and entry.get("content_hash") == archived.content_hash
                    and entry.get("prompt_hash")
                    and entry.get("workflow_hash")
                    and entry.get("model_hashes")
                ),
                None,
            )
            if provenance is None:
                raise ValueError(
                    f"Refusing to restore '{view}': the manifest holds no record "
                    "naming the model, prompt and workflow that produced the "
                    "archived render, and a pack without that provenance cannot "
                    "be approved."
                )
            reference_hashes = tuple(
                str(value) for value in (provenance.get("reference_hashes") or ())
            )
            if len(reference_hashes) != len(draft.conditioning_source_keys):
                raise ValueError(
                    f"Archived provenance for '{view}' names "
                    f"{len(reference_hashes)} conditioning references while the "
                    f"pack records {len(draft.conditioning_source_keys)}; "
                    "refusing to guess which is which."
                )
            report = await self._quality_gate.evaluate(
                image_bytes=archived_bytes,
                view=view,
                seed=archived.seed,
                signature_marks=brief.signature_marks,
            )
            if not report.passed:
                raise ValueError(
                    f"Refusing to restore '{view}': its archived render does not "
                    "pass the view QC gate now ("
                    + ", ".join(report.reasons)
                    + ")."
                )
            # File the render being displaced first, so the swap is recorded
            # even if the write below fails halfway.
            quarantined.append(
                await self._asset_service.quarantine_view(
                    root=root,
                    view=view,
                    seed=draft.seed,
                    attempt=self._attempt_block_of_seed(
                        draft.seed, base_seed=base_seed, index=production_order.index(view)
                    ),
                    image_bytes=displaced_bytes,
                    content_hash=draft.content_hash,
                    report=replace(
                        CharacterViewQcReport.from_dict(draft.qc_report or {}),
                        passed=False,
                        reasons=("superseded_by_restored_render",),
                    ),
                )
            )
            restore_journal[draft.storage_key] = displaced_bytes
            await self._asset_service.save_locked_asset(
                draft.storage_key,
                archived_bytes,
                archived.content_hash,
                allow_replace=True,
            )
            _, width, height = self._asset_service.normalized_png(archived_bytes)
            previous_qc = dict(draft.qc_report or {})
            qc_payload = report.to_dict()
            if previous_qc.get("consistency_qc") is not None:
                # The identity contract belongs to the view's dependencies, not
                # to one frame, so the archived render stands under the contract
                # the pack already recorded.
                qc_payload["consistency_qc"] = previous_qc["consistency_qc"]
            if drift is not None:
                view_drift = drift.evaluate(
                    source_bytes=canonical, views={view: archived_bytes}
                )["views"][0]
                qc_payload["advisory_drift"] = {
                    "view": view,
                    "status": view_drift["status"],
                    "reasons": list(view_drift["reasons"]),
                    **{
                        name: float(value)
                        for name, value in view_drift["metrics"].items()
                    },
                }
            qc_payload["restored_from"] = {
                "archived_storage_key": archived.image_storage_key,
                "superseded_hash": draft.content_hash,
                "superseded_seed": draft.seed,
                "restored_by": actor,
                "reason": reason,
            }
            drafts = [
                (
                    replace(
                        draft,
                        content_hash=archived.content_hash,
                        seed=archived.seed,
                        width=width,
                        height=height,
                        qc_report=qc_payload,
                        prompt_hash=str(provenance.get("prompt_hash", "")),
                        workflow_hash=str(provenance.get("workflow_hash", "")),
                        conditioning_source_hashes=reference_hashes,
                    )
                    if item.view == view
                    else item
                )
                for item in drafts
            ]
            self._asset_service.record_manifest_asset(
                root=root,
                asset_id=f"{view}:restored-from-{archived.content_hash[:12]}",
                storage_key=draft.storage_key,
                content_hash=archived.content_hash,
                seed=archived.seed,
                reference_hashes=reference_hashes,
                report=report,
                generation_metadata={
                    "model_hashes": dict(provenance.get("model_hashes") or {}),
                    "render_duration_sec": float(
                        provenance.get("render_duration_sec") or 0.0
                    ),
                    "peak_vram_mb": provenance.get("peak_vram_mb"),
                    "prompt_hash": str(provenance.get("prompt_hash", "")),
                    "workflow_hash": str(provenance.get("workflow_hash", "")),
                },
                state="QC_PASSED",
            )
            restored.append(
                {
                    "view": view,
                    "restored_seed": archived.seed,
                    "restored_hash": archived.content_hash,
                    "displaced_seed": draft.seed,
                    "displaced_hash": draft.content_hash,
                    "archived_storage_key": archived.image_storage_key,
                    "archive_reason": list(archived.reasons),
                }
            )
        pack = await self._persist_view_pack(
            root=root,
            brief=brief,
            approval=approval,
            drafts=drafts,
            quarantined=quarantined,
            status="BLOCKED" if existing.blocked_views else "PENDING_HUMAN_REVIEW",
            blocked=existing.blocked_views,
            allow_replace=True,
        )
        await self._record_restore_receipt(
            root=root,
            brief=brief,
            approval=approval,
            actor=actor,
            reason=reason,
            entries=restored,
        )
        return pack

    async def _record_restore_receipt(
        self,
        *,
        root: str,
        brief: CharacterCreationBrief,
        approval: CharacterCanonicalApproval,
        actor: str,
        reason: str,
        entries: list[dict[str, object]],
    ) -> None:
        """File the human verdict that put a superseded render back.

        Kept beside the approval receipt rather than inside the pack, so the
        pack keeps describing the images it holds while the receipt records who
        decided otherwise and when. Repeated restores append, because two
        decisions are two decisions.
        """
        key = f"{root}/view-pack-restore.json"
        record = {
            "character_id": brief.character_id,
            "character_version": approval.character_version,
            "restored_by": actor,
            "restored_at": datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
            "reason": reason,
            "views": entries,
        }
        payload: dict[str, object] = {
            "schema_version": 1,
            "character_id": brief.character_id,
            "character_version": approval.character_version,
            "restores": [],
        }
        if await self._storage.exists(key):
            existing = json.loads((await self._storage.load(key)).decode("utf-8"))
            if isinstance(existing, dict) and isinstance(existing.get("restores"), list):
                payload = {**existing, **payload, "restores": list(existing["restores"])}
        payload["restores"] = [*payload["restores"], record]
        await self._storage.save(
            key,
            (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode(),
            "application/json",
        )

    async def load_approved_view_pack(self, **kwargs) -> CharacterReferenceDraftPack:
        return await self._approval_service.load_approved_view_pack(**kwargs)

    async def _load_existing_view_pack(self, *, root: str, brief: CharacterCreationBrief, approval: CharacterCanonicalApproval) -> CharacterReferenceDraftPack | None:
        manifest_key = f"{root}/view-pack.json"
        if not await self._storage.exists(manifest_key):
            return None
        raw = json.loads((await self._storage.load(manifest_key)).decode("utf-8"))
        if not isinstance(raw, dict):
            raise TypeError("Existing view-pack manifest must contain an object.")
        pack = CharacterReferenceDraftPack.from_dict(raw)
        if pack.character_id != brief.character_id or pack.character_version != approval.character_version or pack.brief_hash != brief.content_hash or pack.canonical_storage_key != approval.canonical_storage_key:
            raise ValueError("Existing view-pack belongs to another canonical character.")
        if pack.status not in {"BLOCKED", "PENDING_HUMAN_REVIEW"}:
            raise ValueError("Existing view-pack has an unsupported resumable state.")
        for draft in pack.drafts:
            if not await self._storage.exists(draft.storage_key):
                raise StorageError(f"Existing accepted view '{draft.view}' is missing.")
            image_bytes = await self._storage.load(draft.storage_key)
            if hashlib.sha256(image_bytes).hexdigest() != draft.content_hash:
                raise ValueError(f"Existing accepted view '{draft.view}' changed.")
            if not draft.qc_report or not bool(draft.qc_report.get("passed")):
                raise ValueError(f"Existing accepted view '{draft.view}' has no passing QC evidence.")
        return pack

    @staticmethod
    def _inherit_canonical_approval(report: CharacterViewQcReport) -> CharacterViewQcReport:
        checks = {**dict(report.checks or {}), "canonical_source_inherited": True}
        checks.update({name: True for name in checks})
        observation = CharacterViewObservation(person_count=1, face_count=1, head_inside_frame=True, feet_inside_frame=True, orientation="front", confidence=max(report.observation.confidence, 0.99), provider=f"{report.observation.provider}+canonical-human-approval", face_bbox=report.observation.face_bbox)
        return CharacterViewQcReport(view=report.view, seed=report.seed, passed=True, reasons=(), observation=observation, framing_metrics=report.framing_metrics, checks=checks)

    async def _quarantine_candidate(
        self,
        *,
        root: str,
        view: str,
        attempt: int,
        candidate: _ViewCandidate,
        references: tuple[ConditioningReference, ...],
        quarantined: list[CharacterViewQuarantineArtifact],
    ) -> None:
        quarantine = await self._asset_service.quarantine_view(
            root=root,
            view=view,
            seed=candidate.seed,
            attempt=attempt,
            image_bytes=candidate.image_bytes,
            content_hash=candidate.digest,
            report=candidate.report,
        )
        quarantined.append(quarantine)
        self._asset_service.record_manifest_asset(
            root=root,
            asset_id=f"{view}:attempt-{attempt}-slot-{candidate.slot}",
            storage_key=quarantine.image_storage_key,
            content_hash=candidate.digest,
            seed=candidate.seed,
            reference_hashes=tuple(item[2] for item in references),
            report=candidate.report,
            generation_metadata=candidate.generation_metadata,
            state="QUARANTINED",
        )

    def _drift_for(self, brief: CharacterCreationBrief):
        """Measure drift against this character's own signature mark.

        The configured accent colour is one deployment-wide value, so a
        character with a differently coloured mark was measured with the wrong
        accent: its accent fraction read ``0.0`` and every drawn view came back
        ``palette_drift`` -- an alarm the bytes cannot support, which is how a
        real flag gets ignored. The brief declares both the colour and the side.
        """
        service = self._drift_service
        if service is None:
            return None
        mark = next(
            (
                item
                for item in brief.signature_marks
                if str(item.colour).strip()
            ),
            None,
        )
        if mark is None:
            return service
        side = mark.character_side if mark.character_side in {"left", "right"} else ""
        return service.for_character(accent_colour=mark.colour, mark_side=side)

    async def _select_view_candidate(
        self,
        *,
        view: str,
        approval: CharacterCanonicalApproval,
        candidates: list[_ViewCandidate],
        drift=None,
    ) -> tuple[_ViewCandidate, list[_ViewCandidate]]:
        """Pick the seed that drifted least from the approved source.

        The drift report is advisory, but ranking sibling renders of the *same*
        view is a comparison, not a verdict: every candidate already passed the
        structural QC gate, so choosing the least-drifted one cannot loosen an
        approval requirement. With a single candidate nothing is reordered.
        """
        drift = drift if drift is not None else self._drift_service
        if len(candidates) == 1 or drift is None:
            return candidates[0], []
        source_bytes = await self._storage.load(approval.canonical_storage_key)
        ranked: list[tuple[tuple[int, float], _ViewCandidate]] = []
        for item in candidates:
            report = drift.evaluate(
                source_bytes=source_bytes, views={view: item.image_bytes}
            )
            view_report = report["views"][0]
            score = (
                len(view_report["reasons"]),
                float(view_report["metrics"]["palette_distance"]),
            )
            ranked.append(
                (
                    score,
                    replace(
                        item,
                        drift_metrics={
                            "view": view,
                            "status": view_report["status"],
                            "reasons": list(view_report["reasons"]),
                            **{
                                name: float(value)
                                for name, value in view_report["metrics"].items()
                            },
                        },
                    ),
                )
            )
        ranked.sort(key=lambda pair: pair[0])
        return ranked[0][1], [item for _score, item in ranked[1:]]

    async def _retire_views_for_rerender(
        self,
        *,
        root: str,
        views: tuple[str, ...],
        production_order: tuple[str, ...],
        existing_by_view: dict[str, CharacterReferenceDraft],
        drafts: list[CharacterReferenceDraft],
        quarantined: list[CharacterViewQuarantineArtifact],
        base_seed: int,
        has_existing_pack: bool,
        restore_journal: dict[str, bytes],
    ) -> None:
        """Retire the accepted render of each named view so it is drawn again.

        The retired render is filed as quarantine evidence instead of being
        dropped, for two reasons. It is the image the human was looking at, so
        it is part of the record; and filing it advances the attempt loop, which
        is what makes the replacement a *different* frame. A seed is a pure
        function of the brief hash, the view index, the attempt and the slot, so
        without advancing the attempt a re-render would reproduce the previous
        image byte for byte.

        The retired bytes are also handed to ``restore_journal`` so a later
        failure can put them back where they were.
        """
        if not has_existing_pack:
            raise ValueError(
                "Targeted re-render needs an existing view pack to draw into; "
                "run a full turnaround first."
            )
        fixed = [view for view in views if view in EDIT_TURNAROUND_FIXED_VIEWS]
        if fixed:
            raise ValueError(
                "These views are contract copies of the approved canonical "
                "artifact and are never drawn, so re-rendering them would "
                "replace the character's identity: " + ", ".join(fixed)
            )
        unknown = [view for view in views if view not in production_order]
        if unknown:
            raise ValueError(
                "Unknown turnaround views: "
                + ", ".join(unknown)
                + ". Known views: "
                + ", ".join(production_order)
            )
        for view in views:
            draft = existing_by_view.pop(view, None)
            if draft is None:
                # The view never produced an accepted render. There is nothing
                # to retire, and its quarantined attempts already move the next
                # seed block forward.
                continue
            index = production_order.index(view)
            attempt = self._attempt_block_of_seed(
                draft.seed, base_seed=base_seed, index=index
            )
            image_bytes = await self._storage.load(draft.storage_key)
            if hashlib.sha256(image_bytes).hexdigest() != draft.content_hash:
                raise ValueError(
                    f"Accepted view '{view}' changed on disk; refusing to "
                    "replace evidence that no longer matches its record."
                )
            # Keep the measured checks and metrics; only the verdict changes,
            # because this render is being retired rather than rejected on merit.
            report = replace(
                CharacterViewQcReport.from_dict(draft.qc_report or {}),
                passed=False,
                reasons=("superseded_by_targeted_rerender",),
            )
            quarantined.append(
                await self._asset_service.quarantine_view(
                    root=root,
                    view=view,
                    seed=draft.seed,
                    attempt=attempt,
                    image_bytes=image_bytes,
                    content_hash=draft.content_hash,
                    report=report,
                )
            )
            drafts.remove(draft)
            restore_journal[draft.storage_key] = image_bytes

    @staticmethod
    def _attempt_block_of_seed(seed: int, *, base_seed: int, index: int) -> int:
        """Recover which attempt block a stored seed was drawn from.

        Inverts ``base_seed + index * 10_000 + (attempt - 1) * 1_000 + slot * 101``.
        A slot contributes at most 505, so integer division by 1_000 inside an
        attempt block lands on that block.
        """
        offset = seed - base_seed - index * 10_000
        if offset < 0:
            return 1
        return offset // 1_000 + 1

    async def _persist_view_pack(self, *, root: str, brief: CharacterCreationBrief, approval: CharacterCanonicalApproval, drafts: list[CharacterReferenceDraft], quarantined: list[CharacterViewQuarantineArtifact], status: str, blocked: Mapping[str, tuple[str, ...]] | None = None, allow_replace: bool = False) -> CharacterReferenceDraftPack:
        contact_key = ""
        contact_hash = ""
        if drafts:
            # Even a blocked pack is reviewed and measured: the human needs to
            # see what the run did produce, and a partial pack that carries no
            # evidence is how a silent failure hides.
            contact_bytes = await self._asset_service.contact_sheet(drafts)
            contact_hash = hashlib.sha256(contact_bytes).hexdigest()
            contact_key = f"{root}/contact-sheets/views.png"
            await self._asset_service.save_locked_asset(
                contact_key, contact_bytes, contact_hash, allow_replace=allow_replace
            )
            await self._write_drift_report(
                root=root,
                brief=brief,
                approval=approval,
                drafts=drafts,
                allow_replace=allow_replace,
            )
        pack = CharacterReferenceDraftPack(schema_version=1, character_id=brief.character_id, character_version=approval.character_version, brief_hash=brief.content_hash, canonical_storage_key=approval.canonical_storage_key, drafts=tuple(drafts), status=status, quarantined=tuple(quarantined), blocked_views=dict(blocked or {}), contact_sheet_storage_key=contact_key, contact_sheet_content_hash=contact_hash)
        payload = (json.dumps(pack.to_dict(), indent=2, sort_keys=True) + "\n").encode()
        await self._storage.save_stream(f"{root}/view-pack.json", _single_chunk(payload), "application/json")
        if self._production_manifest is not None:
            self._production_manifest.finalize(relative_root=root, status=status)
        return pack

    async def _write_drift_report(
        self,
        *,
        root: str,
        brief: CharacterCreationBrief,
        approval: CharacterCanonicalApproval,
        drafts: list[CharacterReferenceDraft],
        allow_replace: bool = False,
    ) -> None:
        """Persist advisory drift evidence next to the pack.

        The acceptance list can then require ``drift-report.json``, so a pack
        cannot be approved without at least one deterministic measurement of
        how far each view moved from the approved source.

        Only *drawn* views are measured. The front image and the face close-up
        are contract copies of approved artifacts rather than model output, so
        there is no drift to measure: the front image is byte-identical to the
        source and would be compared with itself, and the face close-up is a
        head crop whose subject box and head density cannot be compared with a
        full-body source at all. Measuring either produces an alarm the bytes
        cannot support, which is how a real flag gets ignored.
        """
        drift = self._drift_for(brief)
        if drift is None:
            return
        measured = [
            draft for draft in drafts if not self._view_is_inherited(draft.view, approval)
        ]
        if not measured:
            # Nothing was drawn, so there is nothing to measure. A report over
            # zero views would be a file that claims measurement happened; the
            # acceptance list requires ``drift-report.json``, so a pack with no
            # drawn view fails loudly at approval instead.
            return
        source_bytes = await self._storage.load(approval.canonical_storage_key)
        views: dict[str, bytes] = {}
        labels: dict[str, str] = {"source": approval.canonical_storage_key}
        for draft in measured:
            views[draft.view] = await self._storage.load(draft.storage_key)
            labels[draft.view] = draft.storage_key
        report = drift.evaluate(
            source_bytes=source_bytes, views=views, labels=labels
        )
        report["character_id"] = brief.character_id
        report["character_version"] = approval.character_version
        report["workflow_version"] = self._EDIT_VIEW_WORKFLOW_VERSION
        drift_payload = (
            json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        ).encode()
        key = f"{root}/drift-report.json"
        await self._asset_service.save_locked_asset(
            key,
            drift_payload,
            hashlib.sha256(drift_payload).hexdigest(),
            allow_replace=allow_replace,
        )

    @staticmethod
    def _build_consistency_qc(
        *,
        brief: CharacterCreationBrief,
        view: str,
        references: tuple[ConditioningReference, ...],
    ) -> CharacterViewConsistencyQc:
        contract = CharacterIdentityContract.from_brief(brief)
        return CharacterViewConsistencyQc(
            contract_hash=contract.content_hash,
            view=view,
            reference_hashes=tuple(item[2] for item in references),
            automatic_checks={
                "identity_contract_bound": bool(contract.content_hash),
                "reference_chain_bound": bool(references) and all(bool(item[2]) for item in references),
                "single_view_contract": len({item[0] for item in references}) == len(references),
            },
        )

    async def _edit_canvas(
        self, approval: CharacterCanonicalApproval
    ) -> tuple[int, int] | None:
        """Target canvas for the edit dialect: the source's own aspect ratio.

        ``None`` for the pose-driven dialect, whose portrait canvas the recipe
        was calibrated on. The edit dialect instead derives the canvas from the
        approved canonical image, because its contract is "change only the
        viewpoint": a canvas that disagrees with the source turns a rotation
        into a re-frame as well.
        """
        if not self._edit_dialect:
            return None
        canonical = await self._storage.load(approval.canonical_storage_key)
        _, width, height = self._asset_service.normalized_png(canonical)
        return edit_canvas_for(width, height)

    def _view_is_inherited(
        self, view: str, approval: CharacterCanonicalApproval
    ) -> bool:
        """True when a view is a contract copy of an approved artifact.

        Kept separate from the render loop so evidence code can ask the same
        question the loop asks. A rule expressed twice drifts apart; the v6
        pack shipped with ``FRONT`` skipped and ``FACE_CLOSEUP`` measured, and
        the report flagged the approved face anchor against itself.
        """
        return (
            self._inherited_view(
                view=view,
                approval=approval,
                face=approval.face_anchor,
                fullbody=approval.fullbody_anchor,
            )
            is not None
        )

    def _inherited_view(
        self,
        *,
        view: str,
        approval: CharacterCanonicalApproval,
        face: CharacterAnchorArtifact,
        fullbody: CharacterAnchorArtifact,
    ) -> _InheritedView | None:
        if view == "FACE_CLOSEUP":
            return _InheritedView.from_anchor(face)
        if view != "FRONT":
            return None
        if not self._edit_dialect:
            return _InheritedView.from_anchor(fullbody)
        if not approval.canonical_content_hash:
            raise ValueError("Canonical approval has no content hash.")
        return _InheritedView(
            storage_key=approval.canonical_storage_key,
            content_hash=approval.canonical_content_hash,
            seed=approval.seed,
            provider_asset_id=approval.provider_asset_id,
            model_checkpoint=approval.provider,
            workflow_version=(
                approval.anchor_workflow_version or self._ANCHOR_WORKFLOW_VERSION
            ),
            human_approved=True,
        )

    def _view_conditioning_references(
        self,
        *,
        view: str,
        approval: CharacterCanonicalApproval,
        face_anchor: CharacterAnchorArtifact,
        fullbody_anchor: CharacterAnchorArtifact,
        produced: dict[str, CharacterReferenceDraft],
    ) -> tuple[ConditioningReference, ...]:
        if self._edit_dialect:
            return self._edit_conditioning_references(
                view=view, approval=approval, face_anchor=face_anchor, produced=produced
            )
        if view == "FACE_CLOSEUP":
            return (
                (
                    "FACE_CLOSEUP",
                    face_anchor.storage_key,
                    face_anchor.content_hash,
                    0.85,
                ),
            )
        return self._conditioning_references(
            view=view,
            face_anchor=face_anchor,
            fullbody_anchor=fullbody_anchor,
            produced=produced,
        )

    @staticmethod
    def _edit_reference(
        label: str, draft: CharacterReferenceDraft
    ) -> ConditioningReference:
        """FLUX.2 binds references through ReferenceLatent, so weight is nominal."""
        return (label, draft.storage_key, draft.content_hash, 1.0)

    def _edit_conditioning_references(
        self,
        *,
        view: str,
        approval: CharacterCanonicalApproval,
        face_anchor: CharacterAnchorArtifact,
        produced: dict[str, CharacterReferenceDraft],
    ) -> tuple[ConditioningReference, ...]:
        if view == "FACE_CLOSEUP":
            return (
                (
                    "FACE_CLOSEUP",
                    face_anchor.storage_key,
                    face_anchor.content_hash,
                    0.85,
                ),
            )
        if view == "FRONT":
            return (
                (
                    "FRONT",
                    approval.canonical_storage_key,
                    approval.canonical_content_hash,
                    1.0,
                ),
            )
        # FRONT is always the first reference slot, so keep it out of the tail.
        needs_source = tuple(
            name for name in edit_turnaround_dependencies(view) if name != "FRONT"
        )
        missing = [
            name for name in ("FRONT", *needs_source) if name not in produced
        ]
        if missing:
            raise ValueError(
                f"View {view} requires accepted reference views: {', '.join(missing)}."
            )
        return (
            self._edit_reference("FRONT", produced["FRONT"]),
            *(
                self._edit_reference(name, produced[name])
                for name in needs_source
            ),
        )

    def _conditioning_references(self, *, view: str, face_anchor: CharacterAnchorArtifact, fullbody_anchor: CharacterAnchorArtifact, produced: dict[str, CharacterReferenceDraft]) -> tuple[ConditioningReference, ...]:
        face = ("FACE_CLOSEUP", face_anchor.storage_key, face_anchor.content_hash, 0.80)
        def generated(reference_view: str, weight: float) -> ConditioningReference:
            draft = produced.get(reference_view)
            if draft is None:
                # A missing dependency must name itself: this view is skipped
                # and recorded instead of crashing the whole turnaround with a
                # bare KeyError.
                raise ValueError(
                    f"View {view} requires accepted reference view "
                    f"{reference_view}, which this run did not produce."
                )
            return (reference_view, draft.storage_key, draft.content_hash, weight)
        if view == "FRONT":
            return (face, ("FRONT", fullbody_anchor.storage_key, fullbody_anchor.content_hash, 0.50))
        if view in {"PROFILE_LEFT", "PROFILE_RIGHT"}:
            return (generated("FRONT", 0.55), (*face[:3], 0.35))
        if view in {"THREE_QUARTER_LEFT", "THREE_QUARTER_RIGHT"}:
            if self._legacy_reference_policy:
                return (generated("FRONT", 0.80),)
            if view == "THREE_QUARTER_RIGHT" and "PROFILE_RIGHT" in produced:
                return (generated("PROFILE_RIGHT", 0.70), generated("FRONT", 0.60))
            return (generated("FRONT", 0.80), (*face[:3], 0.35))
        if view == "BACK":
            if self._legacy_reference_policy:
                return (generated("FRONT", 0.55), generated("PROFILE_LEFT", 0.40))
            return (generated("PROFILE_LEFT", 0.70), generated("PROFILE_RIGHT", 0.70))
        raise ValueError(f"Unknown canonical view: {view}")

    @staticmethod
    def _portable_key(value: str) -> str:
        normalized = value.strip().replace("\\", "/").strip("/")
        from pathlib import PurePosixPath
        path = PurePosixPath(normalized)
        if not normalized or path.is_absolute() or ":" in normalized or any(part in {"", ".", ".."} for part in path.parts):
            raise ValueError("Character view-pack storage key must be portable.")
        return path.as_posix()


#: Reasons that mean "this render was displaced by a later one", as opposed to
#: "this render failed a check". Only these can be put back.
_SUPERSEDED_RENDER_REASONS = frozenset(
    {
        ("superseded_by_targeted_rerender",),
        ("superseded_by_restored_render",),
    }
)

ConditioningReference = tuple[str, str, str, float]
