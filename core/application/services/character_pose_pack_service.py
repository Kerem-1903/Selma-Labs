"""Pre-animation character pose-pack factory.

This service turns one approved canonical character and one approved series
style reference into five reusable pose images. It deliberately stops at a
human approval receipt; animation code may consume only a verified receipt.
"""

from __future__ import annotations

import hashlib
import io
import json
from collections.abc import Collection, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, ClassVar

from PIL import Image, ImageDraw, UnidentifiedImageError

from core.application.services.asset_approval_service import AssetApprovalService
from core.application.services.character_design_service import CharacterDesignService
from core.application.services.character_view_quality_gate import (
    CharacterViewQualityGate,
)
from core.application.services.series_style_lock_service import SeriesStyleLockService
from core.domain.exceptions import KeyframeGenerationError, StorageError
from core.domain.ports.keyframe_generation_port import KeyframeGenerationPort
from core.domain.ports.storage_port import StoragePort
from core.domain.value_objects.character_creation_brief import CharacterCreationBrief
from core.domain.value_objects.character_design import CharacterCanonicalApproval
from core.domain.value_objects.character_pose_pack import (
    POSE_PACK_HUMAN_CHECKS,
    CharacterPoseEvidence,
    CharacterPosePackApproval,
    CharacterPosePackManifest,
)
from core.domain.value_objects.character_view_qc import (
    CharacterViewObservation,
    CharacterViewQcReport,
)
from core.domain.value_objects.keyframe_generation_request import (
    KeyframeGenerationRequest,
)
from core.domain.value_objects.style_lock import StyleLockSnapshot


async def _single_chunk(data: bytes):
    yield data


class _OfflinePoseQualityGate:
    """Structural evidence for explicit offline/fake generation only."""

    async def evaluate(self, *, image_bytes: bytes, view: str, seed: int, signature_marks=()):
        del image_bytes, signature_marks
        orientation = {
            "FRONT": "front",
            "THREE_QUARTER_LEFT": "three_quarter_left",
            "PROFILE_LEFT": "profile_left",
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
                provider="fake:character-pose-qc",
            ),
            framing_metrics={},
            checks={
                "exactly_one_person": True,
                "head_inside_frame": True,
                "feet_inside_frame": True,
                "expected_orientation": True,
                "back_view_no_face": view != "BACK",
                "framing": True,
            },
        )


class CharacterPosePackService:
    """Generate and approve one character's reusable five-pose library."""

    _POSE_TEMPLATE_SOURCE_DIR = (
        Path(__file__).resolve().parents[3] / "assets" / "pose_templates"
    )
    _POSES: tuple[tuple[str, str, str], ...] = (
        (
            "FRONT_NEUTRAL",
            "FRONT",
            "pose_front.png",
        ),
        (
            "THREE_QUARTER_LEFT",
            "THREE_QUARTER_LEFT",
            "pose_three_quarter_left.png",
        ),
        (
            "PROFILE_LEFT",
            "PROFILE_LEFT",
            "pose_profile_left.png",
        ),
        (
            "THREE_QUARTER_RIGHT",
            "THREE_QUARTER_RIGHT",
            "pose_three_quarter_right.png",
        ),
        (
            "BACK_FULL_BODY",
            "BACK",
            "pose_back.png",
        ),
    )
    _POSE_STORAGE_KEYS: ClassVar[dict[str, str]] = {
        pose[0]: f"characters/_pose_templates/{pose[2]}"
        for pose in _POSES
    }
    _WORKFLOW_VERSION = "character-pose-pack-v1"
    _POSE_PROMPTS: ClassVar[dict[str, str]] = {
        "FRONT_NEUTRAL": "front-facing neutral standing pose, full body, relaxed arms",
        "THREE_QUARTER_LEFT": "left three-quarter standing pose, full body, neutral posture",
        "PROFILE_LEFT": "strict left side profile standing pose, full body, neutral posture",
        "THREE_QUARTER_RIGHT": "right three-quarter standing pose, full body, neutral posture",
        "BACK_FULL_BODY": "strict back-facing standing pose, full body, complete back silhouette",
    }
    _POSE_NEGATIVES = (
        "multiple characters",
        "duplicate person",
        "character sheet",
        "collage",
        "split panel",
        "text",
        "watermark",
        "cropped head",
        "cropped feet",
        "extra limbs",
        "bad hands",
    )

    def __init__(
        self,
        generator: KeyframeGenerationPort,
        storage: StoragePort,
        *,
        quality_gate: CharacterViewQualityGate | None = None,
        max_attempts: int = 2,
        pose_width: int = 768,
        pose_height: int = 1152,
        require_real_provenance: bool = True,
        style_lock_resolver: SeriesStyleLockService | None = None,
        active_series_path: str | Path | None = None,
        production_workflow_path: str | Path | None = None,
        default_mode: str = "DISCOVERY",
    ) -> None:
        if not 1 <= max_attempts <= 10:
            raise ValueError("Pose-pack attempts must be between 1 and 10.")
        if pose_width <= 0 or pose_height <= 0:
            raise ValueError("Pose-pack dimensions must be positive.")
        self._generator = generator
        self._storage = storage
        self._quality_gate = quality_gate
        if quality_gate is None and generator.name.startswith("fake:"):
            self._quality_gate = _OfflinePoseQualityGate()
        self._max_attempts = max_attempts
        self._pose_width = pose_width
        self._pose_height = pose_height
        self._require_real_provenance = require_real_provenance
        if default_mode not in {"DISCOVERY", "PRODUCTION"}:
            raise ValueError("Pose-pack mode must be DISCOVERY or PRODUCTION.")
        if default_mode == "PRODUCTION" and (
            style_lock_resolver is None
            or active_series_path is None
            or production_workflow_path is None
        ):
            raise ValueError("Production pose-packs require an active style-lock resolver.")
        self._style_lock_resolver = style_lock_resolver
        self._active_series_path = active_series_path
        self._production_workflow_path = production_workflow_path
        self._default_mode = default_mode

    async def generate_pack(
        self,
        brief: CharacterCreationBrief,
        approval: CharacterCanonicalApproval,
        *,
        style_id: str | None = None,
        style_reference_path: str | Path | None = None,
        active_series_path: str | Path | None = None,
        mode: str | None = None,
        production_snapshot: StyleLockSnapshot | None = None,
        output_prefix: str = "characters",
        run_id: str | None = None,
    ) -> CharacterPosePackManifest:
        """Generate a resumable pack from an approved character and style lock."""
        self._validate_approval(brief, approval)
        selected_mode = mode or self._default_mode
        if selected_mode not in {"DISCOVERY", "PRODUCTION"}:
            raise ValueError("Pose-pack mode must be DISCOVERY or PRODUCTION.")
        if selected_mode == "PRODUCTION":
            if style_id is not None or style_reference_path is not None:
                raise ValueError(
                    "Production pose-packs cannot accept --style-id or --style-reference."
                )
            if active_series_path is not None and active_series_path != self._active_series_path:
                raise ValueError("Production pose-packs must use the configured active series.")
            if production_snapshot is not None:
                if (
                    self._style_lock_resolver is None
                    or self._active_series_path is None
                    or self._production_workflow_path is None
                ):
                    raise ValueError(
                        "A production snapshot requires the configured style-lock resolver."
                    )
                resolved_snapshot = self._style_lock_resolver.resolve_production(
                    self._active_series_path,
                    workflow_path=self._production_workflow_path,
                )
                if resolved_snapshot != production_snapshot:
                    raise ValueError(
                        "Production snapshot does not match the verified active style lock."
                    )
                snapshot = production_snapshot
            else:
                if self._style_lock_resolver is None or self._active_series_path is None:
                    raise ValueError("Production pose-packs require an active series style lock.")
                snapshot = self._style_lock_resolver.resolve_production(
                    self._active_series_path,
                    workflow_path=self._production_workflow_path,
                )
            style_id = snapshot.style_id
            style_reference_path = snapshot.reference_asset
            style_lock_snapshot = snapshot.to_dict()
        else:
            if style_id is None or style_reference_path is None:
                raise ValueError("Discovery pose-packs require an explicit style candidate.")
            style_lock_snapshot = {}
        style_key, style_hash = await self._install_style_reference(
            style_id=style_id,
            style_reference_path=style_reference_path,
        )
        prefix = self._portable_key(output_prefix)
        root = f"{prefix}/{brief.character_id}/v{approval.character_version}/pose-pack"
        manifest_key = f"{root}/manifest.json"
        existing = await self._load_manifest_if_present(manifest_key)
        if existing is not None:
            if (
                existing.brief_hash != brief.content_hash
                or existing.style_id != style_id
                or existing.style_reference_hash != style_hash
            ):
                raise ValueError("Existing pose-pack manifest is bound to different inputs.")
            if selected_mode == "PRODUCTION" and existing.style_lock_snapshot != style_lock_snapshot:
                raise ValueError("Existing pose-pack is bound to a different production style lock.")
            if existing.status == "PENDING_HUMAN_REVIEW":
                await self._verify_manifest_assets(existing)
                return existing
            poses = list(existing.poses)
            quarantined = list(existing.quarantined)
        else:
            poses = []
            quarantined = []
            await self._write_manifest(
                CharacterPosePackManifest(
                    schema_version=1,
                    character_id=brief.character_id,
                    character_version=approval.character_version,
                    brief_hash=brief.content_hash,
                    style_id=style_id,
                    style_reference_storage_key=style_key,
                    style_reference_hash=style_hash,
                    poses=(),
                    status="IN_PROGRESS",
                    manifest_storage_key=manifest_key,
                    artifact_mode=selected_mode,
                    production_eligible=selected_mode == "PRODUCTION",
                    style_lock_snapshot=style_lock_snapshot,
                ),
                manifest_key,
            )

        await self._ensure_pose_templates()
        existing_ids = {pose.pose_id for pose in poses}
        for index, (pose_id, expected_view, _filename) in enumerate(self._POSES):
            if pose_id in existing_ids:
                continue
            accepted: CharacterPoseEvidence | None = None
            for attempt in range(1, self._max_attempts + 1):
                seed = self._seed(brief.content_hash, pose_id, attempt, run_id or "default")
                request = self._build_request(
                    brief,
                    approval,
                    style_key=style_key,
                    style_hash=style_hash,
                    pose_id=pose_id,
                    expected_view=expected_view,
                    seed=seed,
                    style_lock_snapshot=style_lock_snapshot,
                )
                generated = await self._generator.generate_keyframe(request)
                try:
                    image_bytes, width, height = self._normalize_image(generated.image_bytes)
                    if (width, height) != (self._pose_width, self._pose_height):
                        raise KeyframeGenerationError(
                            f"Pose '{pose_id}' must be {self._pose_width}x{self._pose_height}; "
                            f"got {width}x{height}."
                        )
                    report = await self._evaluate(
                        image_bytes=image_bytes,
                        view=expected_view,
                        seed=seed,
                        marks=brief.signature_marks,
                    )
                    self._validate_provenance(generated.metadata, pose_id)
                except (KeyframeGenerationError, ValueError) as error:
                    quarantined.append(
                        {
                            "pose_id": pose_id,
                            "attempt": attempt,
                            "seed": seed,
                            "reason": str(error),
                        }
                    )
                    await self._save_quarantine(root, pose_id, attempt, generated.image_bytes, str(error))
                    continue
                content_hash = hashlib.sha256(image_bytes).hexdigest()
                pose_key = f"{root}/poses/{pose_id.casefold().replace('_', '-')}.png"
                await self._save_locked(pose_key, image_bytes, content_hash, "image/png")
                metadata = generated.metadata
                accepted = CharacterPoseEvidence(
                    pose_id=pose_id,
                    storage_key=pose_key,
                    content_hash=content_hash,
                    pose_template_storage_key=self._POSE_STORAGE_KEYS[pose_id],
                    pose_template_hash=await self._hash_storage(self._POSE_STORAGE_KEYS[pose_id]),
                    seed=seed,
                    width=width,
                    height=height,
                    reference_storage_keys=tuple(
                        str(item) for item in request.reference_storage_keys
                    ),
                    reference_hashes=tuple(
                        str(item)
                        for item in (
                            metadata.get("reference_content_hashes")
                            or tuple(
                                approval.face_anchor.content_hash,
                                approval.fullbody_anchor.content_hash,
                                style_hash,
                            )
                        )
                    ),
                    style_reference_hash=style_hash,
                    prompt_hash=str(metadata.get("prompt_hash") or self._request_hash(request)),
                    workflow_hash=str(metadata.get("workflow_hash", "")),
                    model_hashes={
                        str(key): str(value)
                        for key, value in metadata.get("model_hashes", {}).items()
                    }
                    if isinstance(metadata.get("model_hashes"), Mapping)
                    else {},
                    qc_report=report.to_dict(),
                )
                poses.append(accepted)
                existing_ids.add(pose_id)
                await self._write_manifest(
                    CharacterPosePackManifest(
                        schema_version=1,
                        character_id=brief.character_id,
                        character_version=approval.character_version,
                        brief_hash=brief.content_hash,
                        style_id=style_id,
                        style_reference_storage_key=style_key,
                        style_reference_hash=style_hash,
                        poses=tuple(poses),
                        status="IN_PROGRESS",
                        manifest_storage_key=manifest_key,
                        quarantined=tuple(quarantined),
                        artifact_mode=selected_mode,
                        production_eligible=selected_mode == "PRODUCTION",
                        style_lock_snapshot=style_lock_snapshot,
                    ),
                    manifest_key,
                )
                break
            if accepted is None:
                blocked = CharacterPosePackManifest(
                    schema_version=1,
                    character_id=brief.character_id,
                    character_version=approval.character_version,
                    brief_hash=brief.content_hash,
                    style_id=style_id,
                    style_reference_storage_key=style_key,
                    style_reference_hash=style_hash,
                    poses=tuple(poses),
                    status="BLOCKED",
                    manifest_storage_key=manifest_key,
                    quarantined=tuple(quarantined),
                    artifact_mode=selected_mode,
                    production_eligible=selected_mode == "PRODUCTION",
                    style_lock_snapshot=style_lock_snapshot,
                )
                await self._write_manifest(blocked, manifest_key)
                raise KeyframeGenerationError(
                    f"Pose '{pose_id}' failed QC after {self._max_attempts} attempts."
                )

        contact_key = f"{root}/contact-sheet.png"
        contact_bytes = await self._contact_sheet(poses)
        contact_hash = hashlib.sha256(contact_bytes).hexdigest()
        await self._save_locked(contact_key, contact_bytes, contact_hash, "image/png")
        manifest = CharacterPosePackManifest(
            schema_version=1,
            character_id=brief.character_id,
            character_version=approval.character_version,
            brief_hash=brief.content_hash,
            style_id=style_id,
            style_reference_storage_key=style_key,
            style_reference_hash=style_hash,
            poses=tuple(poses),
            status="PENDING_HUMAN_REVIEW",
            contact_sheet_storage_key=contact_key,
            contact_sheet_content_hash=contact_hash,
            manifest_storage_key=manifest_key,
            quarantined=tuple(quarantined),
            artifact_mode=selected_mode,
            production_eligible=selected_mode == "PRODUCTION",
            style_lock_snapshot=style_lock_snapshot,
        )
        await self._write_manifest(manifest, manifest_key)
        return manifest

    async def approve_pack(
        self,
        *,
        manifest_storage_key: str,
        approved_by: str,
        confirmed_checks: Collection[str],
    ) -> CharacterPosePackApproval:
        raw = json.loads((await self._storage.load(manifest_storage_key)).decode("utf-8"))
        if not isinstance(raw, dict):
            raise TypeError("Pose-pack manifest must contain an object.")
        manifest = CharacterPosePackManifest.from_dict(raw)
        if manifest.status != "PENDING_HUMAN_REVIEW" or not manifest.complete:
            raise ValueError("Only a complete pose pack can be approved.")
        await self._verify_manifest_assets(manifest)
        checks = tuple(dict.fromkeys(str(check) for check in confirmed_checks))
        if set(checks) != set(POSE_PACK_HUMAN_CHECKS):
            missing = sorted(set(POSE_PACK_HUMAN_CHECKS) - set(checks))
            raise ValueError("Pose-pack approval requires every human check: " + ", ".join(missing))
        manifest_bytes = await self._storage.load(manifest_storage_key)
        approval = CharacterPosePackApproval(
            schema_version=1,
            character_id=manifest.character_id,
            character_version=manifest.character_version,
            brief_hash=manifest.brief_hash,
            style_id=manifest.style_id,
            manifest_storage_key=manifest_storage_key,
            manifest_content_hash=hashlib.sha256(manifest_bytes).hexdigest(),
            contact_sheet_content_hash=manifest.contact_sheet_content_hash,
            pose_hashes={pose.pose_id: pose.content_hash for pose in manifest.poses},
            approved_by=approved_by,
            approved_at=datetime.now(timezone.utc),
            confirmed_checks=checks,
        )
        approval_key = f"{PurePosixPath(manifest_storage_key).parent}/approval.json"
        approval_payload = approval.to_dict()
        approval_payload["asset_approval_receipt"] = AssetApprovalService.receipt(
            asset_id=manifest.character_id,
            asset_hash=AssetApprovalService.asset_set_digest(
                [pose.content_hash for pose in manifest.poses]
            ),
            manifest_payload=manifest.to_dict(),
            approved_by=approved_by,
        ).to_dict()
        if await self._storage.exists(approval_key):
            existing_payload = json.loads((await self._storage.load(approval_key)).decode("utf-8"))
            if existing_payload != approval_payload:
                raise ValueError("Pose-pack approval is already locked to different evidence.")
            return CharacterPosePackApproval.from_dict(existing_payload)

        await self._storage.save(
            approval_key,
            (json.dumps(approval_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"),
            "application/json",
        )
        return CharacterPosePackApproval.from_dict(approval_payload)

    async def require_approved_pack(
        self,
        *,
        manifest_storage_key: str,
        approval_storage_key: str | None = None,
    ) -> CharacterPosePackApproval:
        approval_key = approval_storage_key or f"{PurePosixPath(manifest_storage_key).parent}/approval.json"
        approval_payload = json.loads((await self._storage.load(approval_key)).decode("utf-8"))
        approval = CharacterPosePackApproval.from_dict(approval_payload)
        shared_receipt = approval_payload.get("asset_approval_receipt")
        if not isinstance(shared_receipt, Mapping):
            raise ValueError("Pose-pack shared asset approval receipt is missing.")
        manifest_bytes = await self._storage.load(manifest_storage_key)
        if hashlib.sha256(manifest_bytes).hexdigest() != approval.manifest_content_hash:
            raise ValueError("Pose-pack manifest changed after approval.")
        from core.domain.value_objects.asset_approval import AssetApprovalReceipt
        shared_receipt_value = AssetApprovalReceipt.from_dict(shared_receipt)
        manifest = CharacterPosePackManifest.from_dict(json.loads(manifest_bytes.decode("utf-8")))
        if not AssetApprovalService.verify(
            shared_receipt_value,
            asset_hash=AssetApprovalService.asset_set_digest(
                [pose.content_hash for pose in manifest.poses]
            ),
            manifest_payload=manifest.to_dict(),
        ):
            raise ValueError("Pose-pack shared approval receipt is stale.")
        if manifest.status != "PENDING_HUMAN_REVIEW" or not manifest.complete:
            raise ValueError("Approved pose-pack manifest is not reviewable.")
        if (
            approval.character_id != manifest.character_id
            or approval.character_version != manifest.character_version
            or approval.style_id != manifest.style_id
            or approval.contact_sheet_content_hash != manifest.contact_sheet_content_hash
            or dict(approval.pose_hashes)
            != {pose.pose_id: pose.content_hash for pose in manifest.poses}
        ):
            raise ValueError("Pose-pack approval does not match the manifest evidence.")
        await self._verify_manifest_assets(manifest)
        return approval

    async def _evaluate(self, *, image_bytes: bytes, view: str, seed: int, marks):
        if self._quality_gate is None:
            raise RuntimeError("Pose-pack QC is not configured; refusing to persist output.")
        return await self._quality_gate.evaluate(
            image_bytes=image_bytes,
            view=view,
            seed=seed,
            signature_marks=marks,
        )

    def _build_request(
        self,
        brief: CharacterCreationBrief,
        approval: CharacterCanonicalApproval,
        *,
        style_key: str,
        style_hash: str,
        pose_id: str,
        expected_view: str,
        seed: int,
        style_lock_snapshot: Mapping[str, Any] | None = None,
    ) -> KeyframeGenerationRequest:
        assert approval.face_anchor is not None
        assert approval.fullbody_anchor is not None
        identity = CharacterDesignService._identity_description(brief)
        style_prompt = CharacterDesignService._style_prompt(brief.style_preset)
        prompt = ", ".join(
            value
            for value in (
                "masterpiece, best quality, solo, one person only",
                brief.concept,
                identity,
                self._POSE_PROMPTS[pose_id],
                style_prompt,
                f"series style lock {style_hash[:12]}",
                "neutral studio background, complete silhouette, head and both feet visible",
            )
            if value
        )
        refs = (
            ("FACE", approval.face_anchor.storage_key, approval.face_anchor.content_hash, 0.75),
            ("FULL_BODY", approval.fullbody_anchor.storage_key, approval.fullbody_anchor.content_hash, 0.50),
            ("STYLE_SEED", style_key, style_hash, 0.20),
        )
        return KeyframeGenerationRequest(
            shot_contract_id=f"character-pose-pack-{brief.character_id}-{pose_id.casefold()}",
            camera_constraints={"angle": self._POSE_PROMPTS[pose_id], "lens": "50mm", "movement": "locked"},
            action_constraints={"primary_action": f"character pose pack {pose_id}"},
            visual_constraints={
                "prompt": prompt,
                "composition_contract": "one complete centered character; full silhouette inside frame",
                "environment_style": "plain softly graded studio background",
                "latent_mode": "empty",
                "identity_mode": "identity_only_with_style_seed",
                "identity_strength": 0.75,
                "identity_reference_weights": [0.75, 0.50, 0.20],
                "style_seed_weight": 0.20,
                "style_reference_hash": style_hash,
                "pose_storage_key": self._POSE_STORAGE_KEYS[pose_id],
                "pose_strength": 0.88,
                "workflow_version": self._WORKFLOW_VERSION,
                "expected_view": expected_view,
                "style_lock_digest": (
                    style_lock_snapshot.get("production_lock_digest", "")
                    if style_lock_snapshot
                    else ""
                ),
                "series_id": (
                    style_lock_snapshot.get("series_id", "")
                    if style_lock_snapshot
                    else ""
                ),
                "style_id": (
                    style_lock_snapshot.get("style_id", "")
                    if style_lock_snapshot
                    else ""
                ),
                "style_version": (
                    style_lock_snapshot.get("style_version", 0)
                    if style_lock_snapshot
                    else 0
                ),
            },
            character_conditioning=(
                {
                    "character_id": brief.character_id,
                    "identity_constraints": {
                        "description": identity,
                        "immutable_marks": [mark.label for mark in brief.signature_marks],
                    },
                    "active_outfit": {"description": brief.outfit},
                    "references": [
                        {"view": view, "asset_id": content_hash, "storage_key": storage_key}
                        for view, storage_key, content_hash, _weight in refs
                    ],
                },
            ),
            reference_asset_ids=tuple(f"{view.casefold()}:{content_hash}" for view, _key, content_hash, _weight in refs),
            reference_storage_keys=tuple(storage_key for _view, storage_key, _hash_value, _weight in refs),
            negative_prompts=tuple(dict.fromkeys((*brief.avoid, *self._POSE_NEGATIVES))),
            width=self._pose_width,
            height=self._pose_height,
            seed=seed,
        )

    async def _install_style_reference(self, *, style_id: str, style_reference_path: str | Path) -> tuple[str, str]:
        style_id = self._portable_segment(style_id)
        data = Path(style_reference_path).read_bytes()
        _normalized, width, height = self._normalize_image(data)
        if width <= 0 or height <= 0:
            raise ValueError("Style reference dimensions must be positive.")
        digest = hashlib.sha256(data).hexdigest()
        key = f"series-style/{style_id}/{digest[:12]}.png"
        await self._save_locked(key, data, digest, "image/png")
        return key, digest

    async def _ensure_pose_templates(self) -> None:
        catalog_path = self._POSE_TEMPLATE_SOURCE_DIR / "catalog.json"
        raw = json.loads(catalog_path.read_text(encoding="utf-8"))
        entries = {str(item.get("view")): item for item in raw.get("templates", []) if isinstance(item, dict)}
        for pose_id, view, filename in self._POSES:
            entry = entries.get(view)
            if entry is None:
                raise StorageError(f"Pose template catalog is missing {view}.")
            source = self._POSE_TEMPLATE_SOURCE_DIR / filename
            source_bytes = source.read_bytes()
            expected_hash = str(entry.get("sha256", ""))
            if hashlib.sha256(source_bytes).hexdigest() != expected_hash:
                raise StorageError(f"Pose template source hash mismatch: {filename}")
            key = self._POSE_STORAGE_KEYS[pose_id]
            if await self._storage.exists(key):
                if hashlib.sha256(await self._storage.load(key)).hexdigest() != expected_hash:
                    raise StorageError(f"Pose template changed: {key}")
            else:
                await self._storage.save(key, source_bytes, "image/png")

    async def _verify_manifest_assets(self, manifest: CharacterPosePackManifest) -> None:
        for pose in manifest.poses:
            data = await self._storage.load(pose.storage_key)
            if hashlib.sha256(data).hexdigest() != pose.content_hash:
                raise ValueError(f"Pose '{pose.pose_id}' changed after generation.")
            template = await self._storage.load(pose.pose_template_storage_key)
            if hashlib.sha256(template).hexdigest() != pose.pose_template_hash:
                raise ValueError(f"Pose template '{pose.pose_id}' changed.")
        if manifest.contact_sheet_storage_key:
            contact = await self._storage.load(manifest.contact_sheet_storage_key)
            if hashlib.sha256(contact).hexdigest() != manifest.contact_sheet_content_hash:
                raise ValueError("Pose-pack contact sheet changed.")

    async def _load_manifest_if_present(self, key: str) -> CharacterPosePackManifest | None:
        if not await self._storage.exists(key):
            return None
        raw = json.loads((await self._storage.load(key)).decode("utf-8"))
        if not isinstance(raw, dict):
            raise TypeError("Pose-pack manifest must contain an object.")
        return CharacterPosePackManifest.from_dict(raw)

    async def _write_manifest(self, manifest: CharacterPosePackManifest, key: str) -> None:
        payload = (json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
        await self._storage.save(key, payload, "application/json")

    async def _save_quarantine(self, root: str, pose_id: str, attempt: int, data: bytes, reason: str) -> None:
        digest = hashlib.sha256(data).hexdigest()[:12]
        await self._storage.save(
            f"{root}/quarantine/{pose_id.casefold()}-attempt-{attempt}-{digest}.bin",
            data,
            "application/octet-stream",
        )
        report = json.dumps({"pose_id": pose_id, "attempt": attempt, "reason": reason}, indent=2).encode()
        await self._storage.save(
            f"{root}/quarantine/{pose_id.casefold()}-attempt-{attempt}-{digest}.json",
            report,
            "application/json",
        )

    async def _contact_sheet(self, poses: Sequence[CharacterPoseEvidence]) -> bytes:
        tile_width, tile_height, label_height = 300, 450, 32
        sheet = Image.new("RGB", (tile_width * 3, (tile_height + label_height) * 2), "white")
        draw = ImageDraw.Draw(sheet)
        for index, pose in enumerate(poses):
            image_bytes = await self._storage.load(pose.storage_key)
            with Image.open(io.BytesIO(image_bytes)) as source:
                tile = source.convert("RGB")
                tile.thumbnail((tile_width, tile_height), Image.Resampling.LANCZOS)
            left = index % 3 * tile_width + (tile_width - tile.width) // 2
            top = index // 3 * (tile_height + label_height)
            sheet.paste(tile, (left, top))
            draw.text((index % 3 * tile_width + 8, top + tile_height + 8), pose.pose_id.replace("_", " "), fill="black")
        output = io.BytesIO()
        sheet.save(output, format="PNG", optimize=True)
        return output.getvalue()

    async def _save_locked(self, key: str, data: bytes, digest: str, content_type: str) -> None:
        if await self._storage.exists(key):
            if hashlib.sha256(await self._storage.load(key)).hexdigest() != digest:
                raise ValueError(f"Asset '{key}' is already locked to different bytes.")
            return
        await self._storage.save(key, data, content_type)

    async def _hash_storage(self, key: str) -> str:
        return hashlib.sha256(await self._storage.load(key)).hexdigest()

    def _validate_approval(self, brief: CharacterCreationBrief, approval: CharacterCanonicalApproval) -> None:
        if approval.character_id != brief.character_id or approval.brief_hash != brief.content_hash:
            raise ValueError("Canonical approval belongs to another character brief.")
        if not approval.anchors_locked or approval.face_anchor is None or approval.fullbody_anchor is None:
            raise ValueError("Pose-pack generation requires locked face and full-body anchors.")

    def _validate_provenance(self, metadata: Mapping[str, Any], pose_id: str) -> None:
        if not self._require_real_provenance:
            return
        missing = [
            name
            for name in ("workflow_hash", "model_hashes")
            if not metadata.get(name)
        ]
        if not metadata.get("prompt_hash"):
            missing.append("prompt_hash")
        if missing:
            raise ValueError(f"Pose '{pose_id}' is missing real provider provenance: {', '.join(missing)}")

    @staticmethod
    def _normalize_image(data: bytes) -> tuple[bytes, int, int]:
        try:
            with Image.open(io.BytesIO(data)) as image:
                converted = image.convert("RGB")
                width, height = converted.size
                output = io.BytesIO()
                converted.save(output, format="PNG", optimize=True)
        except (UnidentifiedImageError, OSError, ValueError) as error:
            raise KeyframeGenerationError("Pose-pack provider returned an unreadable image.") from error
        return output.getvalue(), width, height

    @staticmethod
    def _request_hash(request: KeyframeGenerationRequest) -> str:
        payload = json.dumps(request.to_dict(), sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
        return hashlib.sha256(payload).hexdigest()

    @staticmethod
    def _seed(brief_hash: str, pose_id: str, attempt: int, run_id: str) -> int:
        return int.from_bytes(hashlib.sha256(f"{brief_hash}:{pose_id}:{attempt}:{run_id}".encode()).digest()[:4], "big")

    @staticmethod
    def _portable_key(value: str) -> str:
        normalized = value.strip().replace("\\", "/").strip("/")
        path = PurePosixPath(normalized)
        if not normalized or path.is_absolute() or ":" in normalized or ".." in path.parts:
            raise ValueError("Storage key must be a portable relative key.")
        return path.as_posix()

    @classmethod
    def _portable_segment(cls, value: str) -> str:
        normalized = cls._portable_key(value)
        if "/" in normalized:
            raise ValueError("Identifier must be one portable path segment.")
        return normalized
