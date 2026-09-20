from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime, timezone
from io import BytesIO
from typing import Any, ClassVar

from PIL import Image, ImageDraw, UnidentifiedImageError

from core.application.services.candidate.candidate_evaluation_service import (
    CandidateEvaluationService,
)
from core.application.services.keyframe_pair_quality_gate import (
    KeyframePairQualityGate,
)
from core.domain.entities.candidate.keyframe_candidate import CandidateStatus
from core.domain.entities.character_bible import CharacterBible
from core.domain.entities.character_state import CharacterState
from core.domain.entities.keyframe import KeyframePair
from core.domain.entities.shot_animation import ShotPlan
from core.domain.entities.shot_contract import ShotContract
from core.domain.entities.shot_storyboard import ShotStoryboard
from core.domain.exceptions import KeyframeGenerationError, StorageError
from core.domain.ports.character_bible_repository_port import (
    CharacterBibleRepositoryPort,
)
from core.domain.ports.keyframe_generation_port import KeyframeGenerationPort
from core.domain.ports.shot_storyboard_repository_port import (
    ShotStoryboardRepositoryPort,
)
from core.domain.ports.storage_port import StoragePort
from core.domain.services.reference_conditioning_builder import (
    ReferenceConditioningBuilder,
)
from core.domain.value_objects.character_design import CharacterReferenceDraftPack
from core.domain.value_objects.character_identity import ReferenceView
from core.domain.value_objects.character_reference import CharacterReference
from core.domain.value_objects.generated_keyframe import GeneratedKeyframe
from core.domain.value_objects.keyframe_generation_request import (
    KeyframeGenerationRequest,
)
from core.domain.value_objects.keyframe_pair_review import (
    PAIR_HUMAN_CHECKS,
    KeyframePairApproval,
    KeyframePairFrameEvidence,
    KeyframePairManifest,
)
from core.domain.value_objects.storyboard_frame import StoryboardFrame


class KeyframeGenerationService:
    """Orchestrate reference loading, image generation, and durable metadata."""

    _CONTENT_TYPES: ClassVar[dict[str, str]] = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
    }
    _SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
    _PAIR_MIN_DIMENSION = 256

    def __init__(
        self,
        *,
        generator: KeyframeGenerationPort,
        storage: StoragePort,
        character_bibles: CharacterBibleRepositoryPort,
        storyboards: ShotStoryboardRepositoryPort,
        candidate_evaluation: CandidateEvaluationService | None = None,
        human_review_required: bool = True,
        conditioning_builder: ReferenceConditioningBuilder | None = None,
        character_lora_active: bool = False,
        view_pack_approval_guard: Callable[[str, int], Awaitable[object]] | None = None,
        pair_quality_gate: KeyframePairQualityGate | None = None,
        pair_max_attempts: int = 1,
        pose_dimensions: tuple[int, int] | None = None,
    ) -> None:
        self._generator = generator
        self._storage = storage
        self._character_bibles = character_bibles
        self._storyboards = storyboards
        self._candidate_evaluation = candidate_evaluation
        self._human_review_required = human_review_required
        if human_review_required and candidate_evaluation is None:
            raise ValueError(
                "Candidate evaluation service is required when human review is enabled."
            )
        self._conditioning_builder = conditioning_builder or ReferenceConditioningBuilder()
        self._character_lora_active = character_lora_active
        self._view_pack_approval_guard = view_pack_approval_guard
        if pair_max_attempts < 1 or pair_max_attempts > 10:
            raise ValueError("pair_max_attempts must be between 1 and 10.")
        self._pair_quality_gate = pair_quality_gate
        self._pair_max_attempts = pair_max_attempts
        self._pose_dimensions = pose_dimensions

    async def _require_approved_characters(
        self, states: Sequence[CharacterState]
    ) -> dict[tuple[str, int], object]:
        """Fail closed before production frames use a canonical character."""
        if not states:
            return {}
        if self._view_pack_approval_guard is None:
            raise KeyframeGenerationError(
                "Character keyframe production requires a view-pack approval guard."
            )
        checked: set[tuple[str, int]] = set()
        approved: dict[tuple[str, int], object] = {}
        for state in states:
            character_id = state.character_id
            character_version = state.character_version
            identity = (character_id, character_version)
            if identity in checked:
                continue
            checked.add(identity)
            try:
                approved[identity] = await self._view_pack_approval_guard(
                    character_id, character_version
                )
            except (FileNotFoundError, TypeError, ValueError) as error:
                raise KeyframeGenerationError(
                    f"Character '{character_id}' v{character_version} has no valid "
                    "approved seven-view pack."
                ) from error
        return approved

    @staticmethod
    def _apply_approved_references(
        bible: CharacterBible, approved_pack: object
    ) -> CharacterBible:
        if not isinstance(approved_pack, CharacterReferenceDraftPack):
            return bible
        bible.reference_pack = {
            ReferenceView(draft.view): CharacterReference(
                id=(
                    f"{approved_pack.character_id}-v{approved_pack.character_version}-"
                    f"{draft.view.casefold()}"
                ),
                character_id=approved_pack.character_id,
                view=ReferenceView(draft.view),
                asset_id=draft.content_hash,
                storage_key=draft.storage_key,
                content_type="image/png",
                content_hash=draft.content_hash,
                revision=approved_pack.character_version,
            )
            for draft in approved_pack.drafts
        }
        return bible

    async def generate(
        self,
        *,
        shot_contract: ShotContract,
        sequence_index: int = 0,
        storyboard: ShotStoryboard | None = None,
        width: int = 1024,
        height: int = 1024,
        seed: int | None = None,
    ) -> ShotStoryboard:
        approved_packs = await self._require_approved_characters(
            shot_contract.required_character_states
        )
        if sequence_index < 0:
            raise KeyframeGenerationError("sequence_index cannot be negative.")
        if not self._SAFE_ID.fullmatch(shot_contract.id):
            raise KeyframeGenerationError("Shot contract ID is not storage-key safe.")
        if storyboard is not None and storyboard.shot_contract_id != shot_contract.id:
            raise KeyframeGenerationError("Storyboard belongs to another shot contract.")
        if storyboard is not None and any(
            frame.sequence_index == sequence_index for frame in storyboard.frames
        ):
            raise KeyframeGenerationError(
                f"Storyboard already contains sequence index {sequence_index}."
            )

        bibles: list[CharacterBible] = []
        seen_character_ids: set[str] = set()
        for state in shot_contract.required_character_states:
            if state.character_id in seen_character_ids:
                continue
            seen_character_ids.add(state.character_id)
            bible = await self._character_bibles.load(state.character_id)
            bibles.append(
                self._apply_approved_references(
                    bible,
                    approved_packs[(state.character_id, state.character_version)],
                )
            )

        request = self._conditioning_builder.build(
            shot_contract=shot_contract,
            character_bibles=bibles,
            width=width,
            height=height,
            seed=seed,
        )
        for reference_key in request.reference_storage_keys:
            if not await self._storage.exists(reference_key):
                raise StorageError(
                    f"Character reference asset '{reference_key}' was not found."
                )
        generated = await self._generator.generate_keyframe(request)
        self._validate_generated_image(generated.image_bytes, generated.content_type)
        if generated.width <= 0 or generated.height <= 0:
            raise KeyframeGenerationError("Generator returned invalid image dimensions.")

        media_asset_id = str(uuid.uuid4())
        extension = self._CONTENT_TYPES[generated.content_type]
        storage_key = (
            f"storyboards/{shot_contract.id}/frames/"
            f"{sequence_index:04d}-{media_asset_id}{extension}"
        )
        stored = await self._storage.save(
            storage_key, generated.image_bytes, generated.content_type
        )
        if stored.key != storage_key:
            raise StorageError("Storage adapter returned a different key for the keyframe.")

        used_reference_asset_ids = generated.metadata.get("reference_asset_ids")
        if used_reference_asset_ids is None:
            frame_reference_asset_ids = request.reference_asset_ids
        elif isinstance(used_reference_asset_ids, list) and all(
            isinstance(asset_id, str) and asset_id in request.reference_asset_ids
            for asset_id in used_reference_asset_ids
        ):
            frame_reference_asset_ids = tuple(dict.fromkeys(used_reference_asset_ids))
        else:
            raise KeyframeGenerationError(
                "Generator reported reference asset IDs outside the request."
            )

        frame = StoryboardFrame(
            id=str(uuid.uuid4()),
            shot_contract_id=shot_contract.id,
            sequence_index=sequence_index,
            media_asset_id=media_asset_id,
            storage_key=storage_key,
            content_type=generated.content_type,
            provider=self._generator.name,
            provider_asset_id=generated.provider_asset_id,
            width=generated.width,
            height=generated.height,
            reference_asset_ids=frame_reference_asset_ids,
            created_at=datetime.now(timezone.utc),
        )
        # Explicit compatibility path for callers that intentionally retain A5 behavior.
        if not self._human_review_required:
            result = (storyboard or ShotStoryboard.create(shot_contract.id)).with_frame(frame)
            await self._storyboards.save(result)
            return result

        # A7 Candidate Generation Flow (single candidate)
        assert self._candidate_evaluation is not None
        await self._candidate_evaluation.register_candidate(
            shot_contract_id=shot_contract.id,
            storage_key=storage_key,
            generation_metadata={
                "sequence_index": sequence_index,
                "media_asset_id": media_asset_id,
                "content_type": generated.content_type,
                "provider": self._generator.name,
                "provider_asset_id": generated.provider_asset_id,
                "width": generated.width,
                "height": generated.height,
                "reference_asset_ids": list(frame_reference_asset_ids),
            }
        )
        return storyboard or ShotStoryboard.create(shot_contract.id)

    async def generate_candidates(
        self,
        *,
        shot_contract: ShotContract,
        sequence_index: int = 0,
        count: int = 3,
        width: int = 1024,
        height: int = 1024,
    ) -> None:
        """Generates multiple candidates for human review (A7 workflow)."""
        if not self._human_review_required or not self._candidate_evaluation:
            raise KeyframeGenerationError("Candidate evaluation service is required to generate candidates.")
        if not 1 <= count <= 10:
            raise KeyframeGenerationError("Candidate count must be between 1 and 10.")

        for _ in range(count):
            await self.generate(
                shot_contract=shot_contract,
                sequence_index=sequence_index,
                width=width,
                height=height,
            )

    async def commit_approved_candidate(self, shot_contract_id: str, storyboard: ShotStoryboard | None = None) -> ShotStoryboard:
        """
        Quality Gate: Commits the approved candidate into the ShotStoryboard.
        Fails if no approved candidate exists.
        """
        if not self._candidate_evaluation:
            raise KeyframeGenerationError("Candidate evaluation service is required to commit candidates.")

        candidate = await self._candidate_evaluation.get_approved_candidate_for_shot(shot_contract_id)
        if not candidate:
            raise KeyframeGenerationError(f"No approved candidate found for shot contract {shot_contract_id}")
        if candidate.status == CandidateStatus.COMMITTED:
            raise KeyframeGenerationError(
                f"Approved candidate for shot contract {shot_contract_id} was already committed."
            )
        if not await self._storage.exists(candidate.storage_key):
            raise StorageError(
                f"Approved candidate asset '{candidate.storage_key}' was not found."
            )

        meta = candidate.generation_metadata
        frame = StoryboardFrame(
            id=str(uuid.uuid4()),
            shot_contract_id=shot_contract_id,
            sequence_index=meta["sequence_index"],
            media_asset_id=meta["media_asset_id"],
            storage_key=candidate.storage_key,
            content_type=meta.get("content_type", "image/png"),
            provider=meta["provider"],
            provider_asset_id=meta["provider_asset_id"],
            width=meta["width"],
            height=meta["height"],
            reference_asset_ids=tuple(meta["reference_asset_ids"]),
            created_at=datetime.now(timezone.utc),
        )

        result = (storyboard or ShotStoryboard.create(shot_contract_id)).with_frame(frame)
        await self._storyboards.save(result)
        await self._candidate_evaluation.mark_candidate_committed(candidate.id)
        return result

    def _validate_generated_image(self, data: bytes, content_type: str) -> None:
        if not data:
            raise KeyframeGenerationError("Generator returned empty image bytes.")
        if content_type not in self._CONTENT_TYPES:
            raise KeyframeGenerationError(
                f"Generator returned unsupported content type: {content_type}"
            )
        signatures = {
            "image/png": data.startswith(b"\x89PNG\r\n\x1a\n"),
            "image/jpeg": data.startswith(b"\xff\xd8\xff"),
            "image/webp": data.startswith(b"RIFF") and data[8:12] == b"WEBP",
        }
        if not signatures[content_type]:
            raise KeyframeGenerationError(
                "Generator bytes do not match the declared image content type."
            )

    def _validate_pair_image_dimensions(
        self, data: bytes, *, reported_width: int, reported_height: int
    ) -> None:
        try:
            with Image.open(BytesIO(data)) as image:
                actual_width, actual_height = image.size
                image.verify()
        except (OSError, UnidentifiedImageError) as error:
            raise KeyframeGenerationError(
                "Generator returned an unreadable keyframe image."
            ) from error
        if (actual_width, actual_height) != (reported_width, reported_height):
            raise KeyframeGenerationError(
                "Generator image dimensions do not match its reported dimensions."
            )
        if min(actual_width, actual_height) < self._PAIR_MIN_DIMENSION:
            raise KeyframeGenerationError(
                f"Keyframe pair images must be at least {self._PAIR_MIN_DIMENSION}px "
                "on each side."
            )

    async def generate_keyframe_pair(
        self,
        shot_plan: ShotPlan,
        *,
        width: int = 1024,
        height: int = 1024,
    ) -> KeyframePair:
        """Generate and persist an unapproved start/end candidate pair."""
        return await self._generate_reviewed_keyframe_pair(
            shot_plan, width=width, height=height
        )

    async def _generate_reviewed_keyframe_pair(
        self, shot_plan: ShotPlan, *, width: int, height: int
    ) -> KeyframePair:
        """Generate an atomic pair, preserving only a fully passing pair as source."""
        if not self._SAFE_ID.fullmatch(shot_plan.id):
            raise KeyframeGenerationError("Shot ID is not storage-key safe.")
        if not shot_plan.prompt_end or not shot_plan.prompt_end.strip():
            raise KeyframeGenerationError("A distinct end-frame prompt is required.")
        pose_keys = (shot_plan.start_pose_reference_key, shot_plan.end_pose_reference_key)
        if not all(pose_keys) or pose_keys[0] == pose_keys[1]:
            raise KeyframeGenerationError(
                "Start and end OpenPose references must be distinct and complete."
            )
        start_pose_key = pose_keys[0]
        end_pose_key = pose_keys[1]
        assert start_pose_key is not None and end_pose_key is not None
        pose_keys = (start_pose_key, end_pose_key)
        pose_hashes = []
        for pose_key in pose_keys:
            assert pose_key is not None
            pose_hashes.append(
                await self._validate_pair_pose_asset(pose_key)
            )

        approved_packs = await self._require_approved_characters((shot_plan.character_state,))
        bible = await self._character_bibles.load(shot_plan.character_state.character_id)
        bible = self._apply_approved_references(
            bible,
            approved_packs[(shot_plan.character_state.character_id, shot_plan.character_state.character_version)],
        )

        from core.domain.value_objects.shot_constraints import (
            ActionConstraints,
            CameraConstraints,
            VisualConstraints,
        )

        def make_request(identifier: str, action: str, pose_key: str, seed: int):
            contract = ShotContract(
                id=identifier,
                camera_constraints=CameraConstraints(
                    angle="full body", lens="35mm", movement="locked"
                ),
                action_constraints=ActionConstraints(
                    primary_action=action, secondary_actions=[]
                ),
                visual_constraints=VisualConstraints(
                    lighting="controlled cinematic light",
                    environment_style="cinematic anime",
                    weather="clear",
                ),
                required_character_states=[shot_plan.character_state],
            )
            request = self._conditioning_builder.build(
                shot_contract=contract,
                character_bibles=[bible],
                width=width,
                height=height,
                seed=seed,
            )
            payload = request.to_dict()
            payload["visual_constraints"] = {
                **request.visual_constraints,
                "pose_storage_key": pose_key,
                "controlnet_type": shot_plan.controlnet_type or "openpose",
                "pose_strength": 0.95,
                "identity_strength": 0.5 if self._character_lora_active else 0.75,
                "identity_mode": "identity_only",
                "identity_end_at": 0.72,
                "latent_mode": "empty",
                **(
                    {"reference_views": ["FRONT", "FACE_CLOSEUP"]}
                    if request.reference_asset_ids
                    else {}
                ),
                "extra_tags": "solo, full body, entire head and feet visible",
                "composition_contract": "single complete character; full silhouette inside frame",
            }
            if not self._character_lora_active:
                payload["negative_prompts"] = list(
                    dict.fromkeys(
                        (*payload.get("negative_prompts", []), "face mask", "visor", "sunglasses", "firearm", "gun")
                    )
                )
            return KeyframeGenerationRequest.from_dict(payload)

        quarantined: list[dict[str, object]] = []
        for attempt in range(1, self._pair_max_attempts + 1):
            generated_items: list[
                tuple[str, KeyframeGenerationRequest, GeneratedKeyframe, str]
            ] = []
            for label, action, pose_key, pose_hash in (
                ("start", shot_plan.prompt, pose_keys[0], pose_hashes[0]),
                ("end", shot_plan.prompt_end, pose_keys[1], pose_hashes[1]),
            ):
                assert pose_key is not None
                seed = int.from_bytes(
                    hashlib.sha256(f"{shot_plan.id}:{label}:{attempt}".encode()).digest()[:4],
                    "big",
                )
                request = make_request(f"{shot_plan.id}_{label}", action, pose_key, seed)
                generated = await self._generator.generate_keyframe(request)
                try:
                    self._validate_generated_image(generated.image_bytes, generated.content_type)
                    self._validate_pair_image_dimensions(
                        generated.image_bytes,
                        reported_width=generated.width,
                        reported_height=generated.height,
                    )
                except KeyframeGenerationError as error:
                    quarantined.append({"label": label, "attempt": attempt, "reason": str(error)})
                    generated_items.append((label, request, generated, pose_hash))
                    continue
                generated_items.append((label, request, generated, pose_hash))

            reports: list[
                tuple[
                    str,
                    KeyframeGenerationRequest,
                    GeneratedKeyframe,
                    str,
                    dict[str, Any],
                ]
            ] = []
            for label, request, generated, pose_hash in generated_items:
                if self._pair_quality_gate is None:
                    report: dict[str, Any] = {
                        "label": label,
                        "expected_view": "FRONT",
                        "seed": request.seed or 0,
                        "passed": True,
                        "reasons": [],
                        "checks": {
                            "readable_image": True,
                            "minimum_dimensions": True,
                            "visual_content": True,
                            "pose_binding": True,
                        },
                    }
                else:
                    evaluated = await self._pair_quality_gate.evaluate(
                        image_bytes=generated.image_bytes,
                        label=label,
                        expected_view="FRONT",
                        seed=request.seed or 0,
                        reported_width=generated.width,
                        reported_height=generated.height,
                        pose_storage_key=request.visual_constraints["pose_storage_key"],
                        pose_content_hash=pose_hash,
                        signature_marks=tuple(
                            getattr(bible.identity_constraints, "signature_marks", ())
                        ),
                    )
                    report = evaluated.to_dict()
                reports.append((label, request, generated, pose_hash, report))

            if len(reports) == 2 and all(bool(item[4]["passed"]) for item in reports):
                frame_evidence = []
                source_keys = []
                for label, request, generated, pose_hash, report in reports:
                    source_key = f"keyframe-pairs/{shot_plan.id}/source/{label}.png"
                    await self._storage.save(source_key, generated.image_bytes, generated.content_type)
                    source_keys.append(source_key)
                    metadata = generated.metadata
                    frame_evidence.append(
                        KeyframePairFrameEvidence(
                            label=label,
                            storage_key=source_key,
                            content_hash=hashlib.sha256(generated.image_bytes).hexdigest(),
                            pose_storage_key=request.visual_constraints["pose_storage_key"],
                            pose_content_hash=pose_hash,
                            seed=request.seed or 0,
                            width=generated.width,
                            height=generated.height,
                            reference_asset_ids=tuple(metadata.get("reference_asset_ids", request.reference_asset_ids)),
                            reference_hashes=tuple(metadata.get("reference_content_hashes", ())),
                            qc_report=report,
                            prompt_hash=str(metadata.get("prompt_hash", "")),
                            workflow_hash=str(metadata.get("workflow_hash", "")),
                            model_hashes=metadata.get("model_hashes", {}),
                        )
                    )
                contact_key = f"keyframe-pairs/{shot_plan.id}/contact-sheet.png"
                contact_bytes = await self._pair_contact_sheet(source_keys, ("start", "end"))
                contact_hash = hashlib.sha256(contact_bytes).hexdigest()
                await self._storage.save(contact_key, contact_bytes, "image/png")
                manifest = KeyframePairManifest(
                    schema_version=1,
                    shot_id=shot_plan.id,
                    character_id=shot_plan.character_state.character_id,
                    character_version=shot_plan.character_state.character_version,
                    prompt_start=shot_plan.prompt,
                    prompt_end=shot_plan.prompt_end,
                    start_pose_reference_key=start_pose_key,
                    end_pose_reference_key=end_pose_key,
                    frames=tuple(frame_evidence),
                    contact_sheet_storage_key=contact_key,
                    contact_sheet_content_hash=contact_hash,
                    quarantined=tuple(quarantined),
                )
                manifest_key = f"keyframe-pairs/{shot_plan.id}/pair-manifest.json"
                manifest_bytes = (json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\\n").encode()
                await self._storage.save(manifest_key, manifest_bytes, "application/json")
                return KeyframePair(
                    start_keyframe=reports[0][2],
                    end_keyframe=reports[1][2],
                    start_storage_key=source_keys[0],
                    end_storage_key=source_keys[1],
                    manifest_storage_key=manifest_key,
                    contact_sheet_storage_key=contact_key,
                )
            for label, _request, generated, _pose_hash, report in reports:
                quarantined.append(
                    {
                        "label": label,
                        "attempt": attempt,
                        "reason": "; ".join(
                            str(reason) for reason in report.get("reasons", [])
                        )
                        or "pair_quality_failed",
                    }
                )
                await self._storage.save(
                    f"keyframe-pairs/{shot_plan.id}/quarantine/attempt-{attempt}-{label}.png",
                    generated.image_bytes,
                    generated.content_type,
                )
        manifest_key = f"keyframe-pairs/{shot_plan.id}/pair-manifest.json"
        blocked = {
            "schema_version": 1,
            "shot_id": shot_plan.id,
            "character_id": shot_plan.character_state.character_id,
            "character_version": shot_plan.character_state.character_version,
            "prompt_start": shot_plan.prompt,
            "prompt_end": shot_plan.prompt_end,
            "start_pose_reference_key": pose_keys[0],
            "end_pose_reference_key": pose_keys[1],
            "frames": [],
            "status": "BLOCKED",
            "next_gate": "PAIR_REGENERATION",
            "quarantined": quarantined,
        }
        await self._storage.save(
            manifest_key,
            (json.dumps(blocked, ensure_ascii=False, indent=2, sort_keys=True) + "\\n").encode(),
            "application/json",
        )
        raise KeyframeGenerationError(
            f"Start/end pair failed automatic QC after {self._pair_max_attempts} attempts; see {manifest_key}."
        )

    async def _validate_pair_pose_asset(self, storage_key: str) -> str:
        data = await self._storage.load(storage_key)
        try:
            with Image.open(BytesIO(data)) as source:
                source.verify()
            with Image.open(BytesIO(data)) as source:
                width, height = source.size
        except (OSError, UnidentifiedImageError) as error:
            raise KeyframeGenerationError(
                f"OpenPose asset '{storage_key}' is not a readable image."
            ) from error
        if self._pose_dimensions is not None and (width, height) != self._pose_dimensions:
            raise KeyframeGenerationError(
                f"OpenPose asset '{storage_key}' must be {self._pose_dimensions[0]}x{self._pose_dimensions[1]}."
            )
        return hashlib.sha256(data).hexdigest()

    async def _pair_contact_sheet(
        self, storage_keys: Sequence[str], labels: Sequence[str]
    ) -> bytes:
        tile_width, tile_height, label_height = 512, 576, 40
        sheet = Image.new("RGB", (tile_width * len(storage_keys), tile_height + label_height), "white")
        draw = ImageDraw.Draw(sheet)
        for index, (key, label) in enumerate(zip(storage_keys, labels)):
            with Image.open(BytesIO(await self._storage.load(key))) as source:
                tile = source.convert("RGB")
                tile.thumbnail((tile_width, tile_height), Image.Resampling.LANCZOS)
            left = index * tile_width + (tile_width - tile.width) // 2
            sheet.paste(tile, (left, 0))
            draw.text((index * tile_width + 12, tile_height + 10), label.upper(), fill="black")
        output = BytesIO()
        sheet.save(output, format="PNG", optimize=True)
        return output.getvalue()

    async def approve_keyframe_pair(
        self,
        *,
        shot_id: str,
        manifest_storage_key: str,
        approved_by: str,
        confirmed_checks: Sequence[str],
    ) -> KeyframePairApproval:
        """Hash-verify a pending pair and write its human approval receipt."""
        if not self._SAFE_ID.fullmatch(shot_id):
            raise KeyframeGenerationError("Shot ID is not storage-key safe.")
        if not manifest_storage_key:
            raise KeyframeGenerationError("Pair manifest storage key is required.")
        raw = json.loads((await self._storage.load(manifest_storage_key)).decode("utf-8"))
        if not isinstance(raw, dict):
            raise KeyframeGenerationError("Pair manifest must contain an object.")
        manifest = KeyframePairManifest.from_dict(raw)
        if manifest.shot_id != shot_id:
            raise KeyframeGenerationError("Pair manifest belongs to another shot.")
        if manifest.status != "PENDING_HUMAN_REVIEW":
            raise KeyframeGenerationError("Only a pending pair can be approved.")
        for frame in manifest.frames:
            data = await self._storage.load(frame.storage_key)
            if hashlib.sha256(data).hexdigest() != frame.content_hash:
                raise KeyframeGenerationError(
                    f"Pair frame '{frame.label}' changed before approval."
                )
            pose = await self._storage.load(frame.pose_storage_key)
            if hashlib.sha256(pose).hexdigest() != frame.pose_content_hash:
                raise KeyframeGenerationError(
                    f"Pair pose '{frame.label}' changed before approval."
                )
        contact = await self._storage.load(manifest.contact_sheet_storage_key)
        if hashlib.sha256(contact).hexdigest() != manifest.contact_sheet_content_hash:
            raise KeyframeGenerationError("Pair contact sheet changed before approval.")
        for frame in manifest.frames:
            if not frame.prompt_hash or not frame.workflow_hash or not frame.model_hashes:
                raise KeyframeGenerationError(
                    f"Pair frame '{frame.label}' is missing provider provenance evidence."
                )
        checks = tuple(dict.fromkeys(str(check) for check in confirmed_checks))
        if set(checks) != set(PAIR_HUMAN_CHECKS):
            missing = sorted(set(PAIR_HUMAN_CHECKS) - set(checks))
            raise KeyframeGenerationError(
                "Pair approval requires every human check: " + ", ".join(missing)
            )
        approval_key = f"keyframe-pairs/{shot_id}/pair-approval.json"
        approval = KeyframePairApproval(
            schema_version=1,
            shot_id=shot_id,
            character_id=manifest.character_id,
            character_version=manifest.character_version,
            approved_by=approved_by,
            approved_at=datetime.now(timezone.utc),
            manifest_storage_key=manifest_storage_key,
            manifest_content_hash=hashlib.sha256(
                (
                    json.dumps(
                        manifest.to_dict(),
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n"
                ).encode("utf-8")
            ).hexdigest(),
            contact_sheet_content_hash=manifest.contact_sheet_content_hash,
            frame_hashes={frame.label: frame.content_hash for frame in manifest.frames},
            confirmed_checks=checks,
        )
        if await self._storage.exists(approval_key):
            existing = KeyframePairApproval.from_dict(
                json.loads((await self._storage.load(approval_key)).decode("utf-8"))
            )
            if existing.to_dict() != approval.to_dict():
                raise KeyframeGenerationError("Pair approval is already locked to different evidence.")
            return existing
        payload = (json.dumps(approval.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
        await self._storage.save(approval_key, payload, "application/json")
        return approval

    async def require_approved_pair(self, shot_plan: ShotPlan) -> KeyframePairApproval:
        """Fail closed when downstream animation consumes a pair-backed shot."""
        manifest_key = shot_plan.keyframe_pair_manifest_key
        approval_key = shot_plan.keyframe_pair_approval_key
        if not manifest_key or not approval_key:
            raise KeyframeGenerationError("Pair-backed animation requires manifest and approval keys.")
        raw = json.loads((await self._storage.load(approval_key)).decode("utf-8"))
        if not isinstance(raw, dict):
            raise KeyframeGenerationError("Pair approval must contain an object.")
        approval = KeyframePairApproval.from_dict(raw)
        if approval.manifest_storage_key != manifest_key or approval.shot_id != shot_plan.id:
            raise KeyframeGenerationError("Pair approval does not match the animation shot.")
        manifest_bytes = await self._storage.load(manifest_key)
        if hashlib.sha256(manifest_bytes).hexdigest() != approval.manifest_content_hash:
            raise KeyframeGenerationError("Pair manifest changed after approval.")
        manifest = KeyframePairManifest.from_dict(
            json.loads(manifest_bytes.decode("utf-8"))
        )
        if manifest.shot_id != shot_plan.id or manifest.status != "PENDING_HUMAN_REVIEW":
            raise KeyframeGenerationError("Approved pair manifest is not reviewable for this shot.")
        if manifest.contact_sheet_content_hash != approval.contact_sheet_content_hash:
            raise KeyframeGenerationError("Pair contact-sheet evidence changed after approval.")
        for frame in manifest.frames:
            data = await self._storage.load(frame.storage_key)
            if hashlib.sha256(data).hexdigest() != approval.frame_hashes.get(frame.label):
                raise KeyframeGenerationError(
                    f"Approved pair frame '{frame.label}' changed after approval."
                )
            pose = await self._storage.load(frame.pose_storage_key)
            if hashlib.sha256(pose).hexdigest() != frame.pose_content_hash:
                raise KeyframeGenerationError(
                    f"Approved pair pose '{frame.label}' changed after approval."
                )
        contact = await self._storage.load(manifest.contact_sheet_storage_key)
        if hashlib.sha256(contact).hexdigest() != approval.contact_sheet_content_hash:
            raise KeyframeGenerationError("Approved pair contact sheet changed after approval.")
        return approval
