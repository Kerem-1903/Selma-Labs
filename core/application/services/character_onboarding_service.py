"""Automate repeatable character reference creation before animation."""

from __future__ import annotations

import hashlib
import io
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import PurePosixPath

from PIL import Image, UnidentifiedImageError

from core.domain.entities.character_bible import CharacterBible
from core.domain.exceptions import KeyframeGenerationError, StorageError
from core.domain.ports.keyframe_generation_port import KeyframeGenerationPort
from core.domain.ports.preproduction_image_evaluator_port import (
    PreproductionImageEvaluatorPort,
)
from core.domain.ports.storage_port import StoragePort
from core.domain.value_objects.character_identity import ReferenceView
from core.domain.value_objects.character_onboarding import (
    CharacterCandidateAsset,
    CharacterCandidatePack,
    CharacterOnboardingPlan,
    CharacterPilotApproval,
    CharacterReferenceRecipe,
)
from core.domain.value_objects.keyframe_generation_request import (
    KeyframeGenerationRequest,
)


class CharacterOnboardingService:
    """Plan and generate a character pack from one approved anchor image."""

    _QUALITY = "masterpiece, high score, great score, absurdres, anime character design"
    _BASE_NEGATIVES = (
        "identity drift",
        "different face",
        "different outfit",
        "multiple characters",
        "duplicate body",
        "extra limbs",
        "bad hands",
        "cropped head",
        "cropped feet",
        "text",
        "watermark",
    )
    _FACE_CLOSEUP_NEGATIVES = (
        "full body",
        "long shot",
        "wide shot",
        "distant subject",
        "tiny face",
        "feet visible",
        "upper body",
        "medium shot",
    )
    _RECIPES = (
        (
            "face-closeup-neutral-01.png",
            "FACE_CLOSEUP",
            "train",
            "portrait, close-up, headshot, face focus, neutral expression",
        ),
        (
            "face-closeup-determined-02.png",
            "FACE_CLOSEUP",
            "train",
            "portrait, close-up, headshot, face focus, determined expression",
        ),
        (
            "front-neutral-01.png",
            "FRONT",
            "train",
            "front view, upper body, neutral pose",
        ),
        (
            "front-expression-02.png",
            "FRONT",
            "train",
            "front view, upper body, restrained confident expression",
        ),
        (
            "three-quarter-neutral-01.png",
            "THREE_QUARTER_LEFT",
            "train",
            "left three-quarter view, neutral pose",
        ),
        (
            "three-quarter-expression-02.png",
            "THREE_QUARTER_LEFT",
            "train",
            "left three-quarter view, focused expression",
        ),
        (
            "three-quarter-right-neutral-01.png",
            "THREE_QUARTER_RIGHT",
            "train",
            "right three-quarter view, neutral pose",
        ),
        (
            "three-quarter-right-expression-02.png",
            "THREE_QUARTER_RIGHT",
            "train",
            "right three-quarter view, focused expression",
        ),
        (
            "profile-left-neutral-01.png",
            "PROFILE_LEFT",
            "train",
            "strict left profile, neutral expression",
        ),
        (
            "profile-left-expression-02.png",
            "PROFILE_LEFT",
            "train",
            "strict left profile, determined expression",
        ),
        (
            "back-neutral-01.png",
            "BACK",
            "train",
            "full body back view, complete silhouette",
        ),
        (
            "full-body-neutral-01.png",
            "FULL_BODY",
            "train",
            "full body front view, neutral standing pose, head and feet visible",
        ),
        (
            "full-body-relaxed-02.png",
            "FULL_BODY",
            "train",
            "full body relaxed standing pose, head and feet visible",
        ),
        (
            "upper-body-neutral-01.png",
            "UPPER_BODY",
            "train",
            "upper body, complete outfit construction",
        ),
        (
            "action-walking-01.png",
            "ACTION_WALKING",
            "train",
            "full body natural walk, clear silhouette",
        ),
        (
            "action-running-01.png",
            "ACTION_RUNNING",
            "train",
            "full body dynamic sprint, separated arms and legs",
        ),
        (
            "action-wind-01.png",
            "ACTION_WIND",
            "train",
            "full body standing in strong wind, hair and clothing reacting",
        ),
        (
            "action-crouched-guard-01.png",
            "ACTION_CROUCHED_GUARD",
            "train",
            "full body low defensive guard, balanced stance",
        ),
        (
            "action-landing-01.png",
            "ACTION_LANDING",
            "train",
            "full body controlled landing, readable anatomy",
        ),
        (
            "action-signature-01.png",
            "ACTION_SIGNATURE",
            "train",
            "full body signature action, canonical props only",
        ),
        (
            "profile-right-neutral-01.png",
            "PROFILE_RIGHT",
            "holdout",
            "strict right profile, neutral expression",
        ),
        (
            "profile-right-expression-02.png",
            "PROFILE_RIGHT",
            "holdout",
            "strict right profile, determined expression",
        ),
        (
            "profile-right-soft-light-03.png",
            "PROFILE_RIGHT",
            "holdout",
            "strict right profile, soft studio light",
        ),
    )

    def __init__(
        self,
        generator: KeyframeGenerationPort,
        storage: StoragePort,
        evaluator: PreproductionImageEvaluatorPort | None = None,
        *,
        max_attempts: int = 3,
    ) -> None:
        if max_attempts <= 0:
            raise ValueError("Character generation attempts must be greater than zero.")
        self._generator = generator
        self._storage = storage
        self._evaluator = evaluator
        self._max_attempts = max_attempts

    @classmethod
    def plan(cls, character: CharacterBible) -> CharacterOnboardingPlan:
        identity = ", ".join(character.prompt_fragments())
        immutable_marks = "; ".join(character.identity_constraints.immutable_marks)
        if not identity:
            raise ValueError("Character Bible contains no usable prompt fragments.")
        seed_base = int(
            hashlib.sha256(character.character_id.encode("utf-8")).hexdigest()[:8], 16
        )
        anchor_prompt = (
            f"{cls._QUALITY}, solo, {identity}, full body front view, neutral standing "
            "pose, plain light background, entire head and both feet visible, "
            f"immutable identity marks exactly once with no duplicates: {immutable_marks}"
        )
        recipes = tuple(
            CharacterReferenceRecipe(
                filename=filename,
                view=view,
                split=split,
                prompt=f"{cls._QUALITY}, solo, {identity}, {direction}, plain light background",
                seed=seed_base + index,
            )
            for index, (filename, view, split, direction) in enumerate(cls._RECIPES, 1)
        )
        return CharacterOnboardingPlan(
            schema_version=1,
            character_id=character.character_id,
            trigger_token=(
                "selma_"
                f"{character.character_id.casefold().replace('-', '_').replace('.', '_')}_v1"
            ),
            anchor_prompt=anchor_prompt,
            anchor_seed=seed_base,
            negative_prompts=tuple(
                dict.fromkeys(
                    (*character.style_profile.negative_prompts, *cls._BASE_NEGATIVES)
                    + (
                        "duplicated signature marks",
                        "mirrored signature marks",
                        "extra colored hair streak",
                    )
                )
            ),
            recipes=recipes,
        )

    async def generate_anchor(
        self,
        character: CharacterBible,
        *,
        output_prefix: str = "character-candidates",
        seed_offset: int = 0,
        source_reference_storage_key: str | None = None,
    ) -> CharacterCandidateAsset:
        if seed_offset < 0:
            raise ValueError("Anchor seed offset must not be negative.")
        plan = self.plan(character)
        source_key = (
            self._portable_key(source_reference_storage_key)
            if source_reference_storage_key
            else None
        )
        if source_key and not await self._storage.exists(source_key):
            raise StorageError(f"Anchor source reference '{source_key}' was not found.")
        request = self._request(
            character=character,
            prompt=plan.anchor_prompt,
            seed=plan.anchor_seed + seed_offset,
            negatives=plan.negative_prompts,
            anchor_storage_key=source_key,
        )
        if source_key:
            request = replace(
                request,
                visual_constraints={
                    **request.visual_constraints,
                    "identity_strength": 0.95,
                    "identity_weight_type": "linear",
                    "identity_end_at": 0.90,
                },
            )
        generated = await self._generator.generate_keyframe(request)
        digest = hashlib.sha256(generated.image_bytes).hexdigest()[:12]
        return await self._save_candidate(
            storage_prefix=(
                f"{self._portable_key(output_prefix)}/{character.character_id}/anchors"
            ),
            filename=f"anchor-{digest}.png",
            generated=generated,
        )

    async def generate_reference_pack(
        self,
        character: CharacterBible,
        *,
        anchor_storage_key: str,
        output_prefix: str = "character-candidates",
        recipe_limit: int | None = None,
        automatic_review: bool = True,
        pilot_approval: CharacterPilotApproval | None = None,
    ) -> CharacterCandidatePack:
        anchor_key = self._portable_key(anchor_storage_key)
        if not await self._storage.exists(anchor_key):
            raise StorageError(f"Approved anchor '{anchor_key}' was not found.")
        anchor_digest = hashlib.sha256(
            await self._storage.load(anchor_key)
        ).hexdigest()[:12]
        run_root = (
            f"{self._portable_key(output_prefix)}/{character.character_id}/"
            f"runs/{anchor_digest}"
        )
        plan = self.plan(character)
        if recipe_limit is not None and not 1 <= recipe_limit <= len(plan.recipes):
            raise ValueError(
                f"Character recipe limit must be between 1 and {len(plan.recipes)}."
            )
        recipes = plan.recipes[:recipe_limit]
        candidates = []
        quarantined = []
        anchor_bytes = await self._storage.load(anchor_key)
        if len(recipes) > 1:
            if pilot_approval is None:
                raise ValueError(
                    "Bulk character generation requires an approved face-closeup pilot."
                )
            pilot = await self._verified_pilot_candidate(
                character=character,
                anchor_key=anchor_key,
                anchor_bytes=anchor_bytes,
                approval=pilot_approval,
                expected_filename=plan.recipes[0].filename,
            )
            candidates.append(pilot)
            recipes = recipes[1:]
        for recipe in recipes:
            accepted = None
            conditioning_key = await self._conditioning_reference_for_view(
                anchor_bytes=anchor_bytes,
                anchor_key=anchor_key,
                run_root=run_root,
                view=recipe.view,
            )
            for attempt in range(1, self._max_attempts + 1):
                generated = await self._generator.generate_keyframe(
                    self._request(
                        character=character,
                        prompt=recipe.prompt,
                        seed=recipe.seed + (attempt - 1) * 10_000,
                        negatives=self._negatives_for_view(
                            plan.negative_prompts, recipe.view
                        ),
                        anchor_storage_key=conditioning_key,
                        view=recipe.view,
                    )
                )
                quality = None
                if automatic_review and self._evaluator is not None:
                    quality = await self._evaluator.evaluate(
                        image_bytes=generated.image_bytes,
                        reference_bytes=anchor_bytes,
                        context=(
                            f"Character: {character.character_id}. Required recipe: "
                            f"{recipe.prompt}. Preserve face, hair, outfit, marks, "
                            "anatomy and requested framing."
                        ),
                        subject_policy="character_required",
                    )
                passed = quality is None or quality.passed
                candidate = await self._save_candidate(
                    storage_prefix=f"{run_root}/{'source' if passed else 'quarantine'}",
                    filename=(
                        recipe.filename
                        if passed
                        else f"attempt-{attempt}-{recipe.filename}"
                    ),
                    generated=generated,
                    attempt=attempt,
                    quality=quality,
                )
                if passed:
                    accepted = candidate
                    break
                quarantined.append(candidate)
            if accepted is None:
                raise KeyframeGenerationError(
                    f"Character candidate '{recipe.filename}' failed automatic "
                    f"quality review after {self._max_attempts} attempts."
                )
            candidates.append(accepted)
        return CharacterCandidatePack(
            schema_version=1,
            character_id=character.character_id,
            anchor_storage_key=anchor_key,
            candidates=tuple(candidates),
            quarantined=tuple(quarantined),
        )

    async def approve_pilot(
        self,
        character: CharacterBible,
        *,
        anchor_storage_key: str,
        pilot_storage_key: str,
        approved_by: str,
        checks: dict[str, bool],
    ) -> CharacterPilotApproval:
        """Record explicit human evidence before expensive pack generation."""
        anchor_key = self._portable_key(anchor_storage_key)
        pilot_key = self._portable_key(pilot_storage_key)
        if not approved_by.strip():
            raise ValueError("Pilot approval requires a named approver.")
        failed = [
            name
            for name in CharacterPilotApproval.REQUIRED_CHECKS
            if checks.get(name) is not True
        ]
        if failed:
            raise ValueError(
                "Pilot approval failed required checks: " + ", ".join(failed)
            )
        if not await self._storage.exists(anchor_key):
            raise StorageError(f"Approved anchor '{anchor_key}' was not found.")
        if not await self._storage.exists(pilot_key):
            raise StorageError(f"Pilot candidate '{pilot_key}' was not found.")
        anchor_bytes = await self._storage.load(anchor_key)
        anchor_digest = hashlib.sha256(anchor_bytes).hexdigest()
        expected_suffix = (
            f"/runs/{anchor_digest[:12]}/source/"
            f"{self.plan(character).recipes[0].filename}"
        )
        if not pilot_key.endswith(expected_suffix):
            raise ValueError(
                "Pilot candidate does not belong to this anchor's reference run."
            )
        pilot_bytes = await self._storage.load(pilot_key)
        self._validate_png_bytes(pilot_bytes)
        return CharacterPilotApproval(
            schema_version=1,
            character_id=character.character_id,
            anchor_storage_key=anchor_key,
            anchor_sha256=anchor_digest,
            pilot_storage_key=pilot_key,
            pilot_sha256=hashlib.sha256(pilot_bytes).hexdigest(),
            approved_by=approved_by.strip(),
            approved_at=datetime.now(timezone.utc).isoformat(),
            checks=CharacterPilotApproval.REQUIRED_CHECKS,
        )

    async def approve_reference_pack(
        self,
        character: CharacterBible,
        selections: dict[ReferenceView, str],
    ) -> CharacterBible:
        from core.application.services.character_reference_asset_service import (
            CharacterReferenceAssetService,
        )
        from core.domain.services.character_bible_validation_service import (
            CharacterBibleValidationService,
        )

        missing = set(CharacterBibleValidationService.DEFAULT_REQUIRED_VIEWS) - set(
            selections
        )
        if missing:
            names = ", ".join(sorted(view.value for view in missing))
            raise ValueError(f"Reference approval is missing required views: {names}")
        reference_service = CharacterReferenceAssetService(self._storage)
        for view, raw_key in selections.items():
            storage_key = self._portable_key(raw_key)
            data = await self._storage.load(storage_key)
            await reference_service.save_reference(character, view, data, "image/png")
        report = CharacterBibleValidationService().validate(character)
        if not report.is_complete:
            raise ValueError(
                "Approved reference pack did not pass Character Bible validation."
            )
        return character

    @staticmethod
    def _request(
        *,
        character: CharacterBible,
        prompt: str,
        seed: int,
        negatives: tuple[str, ...],
        anchor_storage_key: str | None = None,
        view: str = "FULL_BODY",
    ) -> KeyframeGenerationRequest:
        references = []
        asset_ids: tuple[str, ...] = ()
        storage_keys: tuple[str, ...] = ()
        if anchor_storage_key:
            references = [
                {
                    "asset_id": "approved-anchor",
                    "storage_key": anchor_storage_key,
                    "view": "FRONT",
                }
            ]
            asset_ids = ("approved-anchor",)
            storage_keys = (anchor_storage_key,)
        camera, composition, identity_strength = CharacterOnboardingService._view_contract(
            view
        )
        identity = character.identity_constraints
        return KeyframeGenerationRequest(
            shot_contract_id=f"character-onboarding-{character.character_id}-{seed}",
            camera_constraints=camera,
            action_constraints={"primary_action": prompt, "secondary_actions": []},
            visual_constraints={
                "prompt": prompt,
                "lighting": "neutral controlled studio light",
                "environment_style": "plain reference background",
                "weather": "clear",
                "composition_contract": composition,
                "identity_contract": {
                    "face": identity.facial_geometry,
                    "hair": identity.hair,
                    "eyes": identity.eye_color,
                    "silhouette": identity.silhouette,
                    "immutable_marks": tuple(identity.immutable_marks),
                    "outfit": (
                        character.outfit_catalog[0].description
                        if character.outfit_catalog
                        else ""
                    ),
                },
                "identity_strength": identity_strength,
                "identity_mode": "identity_only",
                "identity_weight_type": "linear",
                "identity_combine_embeds": "concat",
                "identity_start_at": 0.0,
                "identity_end_at": 0.9,
                "identity_embeds_scaling": "V only",
            },
            character_conditioning=(
                {
                    "character_id": character.character_id,
                    "identity_constraints": character.identity_constraints.to_dict(),
                    "style_profile": character.style_profile.to_dict(),
                    "references": references,
                },
            ),
            reference_asset_ids=asset_ids,
            reference_storage_keys=storage_keys,
            negative_prompts=negatives,
            width=1024,
            height=1024,
            seed=seed,
        )

    @staticmethod
    def _view_contract(view: str) -> tuple[dict[str, str], str, float]:
        if view == "FACE_CLOSEUP":
            return (
                {
                    "angle": "tight face close-up, head and shoulders only",
                    "lens": "85mm portrait lens",
                    "movement": "locked",
                },
                (
                    "single centered headshot; face occupies 70-85% of frame; complete "
                    "hair silhouette and top of shoulders visible; torso and arms excluded"
                ),
                1.0,
            )
        if view.startswith("PROFILE"):
            return (
                {"angle": "strict profile portrait", "lens": "70mm", "movement": "locked"},
                "single character profile; head and torso readable; no front-facing pose",
                0.95,
            )
        if view.startswith("ACTION"):
            return (
                {"angle": "full body action", "lens": "50mm", "movement": "locked"},
                "single complete body; head, hands and feet visible; action silhouette clear",
                0.82,
            )
        if view in {"FULL_BODY", "BACK"}:
            return (
                {"angle": "full body", "lens": "50mm", "movement": "locked"},
                "single complete body; entire head and both feet visible",
                0.9,
            )
        return (
            {"angle": "upper-body portrait", "lens": "65mm", "movement": "locked"},
            "single character upper-body portrait; face, hair and outfit construction readable",
            0.95,
        )

    @classmethod
    def _negatives_for_view(
        cls, negatives: tuple[str, ...], view: str
    ) -> tuple[str, ...]:
        extra = cls._FACE_CLOSEUP_NEGATIVES if view == "FACE_CLOSEUP" else ()
        return tuple(dict.fromkeys((*negatives, *extra)))

    async def _conditioning_reference_for_view(
        self,
        *,
        anchor_bytes: bytes,
        anchor_key: str,
        run_root: str,
        view: str,
    ) -> str:
        if view != "FACE_CLOSEUP":
            return anchor_key
        try:
            with Image.open(io.BytesIO(anchor_bytes)) as source:
                image = source.convert("RGB")
        except (UnidentifiedImageError, OSError) as error:
            raise ValueError("Approved character anchor is not a readable image.") from error
        crop_size = max(1, min(image.width, round(image.height * 0.24)))
        left = max(0, (image.width - crop_size) // 2)
        crop = image.crop((left, 0, left + crop_size, crop_size))
        crop = crop.resize((1024, 1024), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        crop.save(output, format="PNG")
        storage_key = f"{run_root}/conditioning/face-closeup-anchor.png"
        stored = await self._storage.save(storage_key, output.getvalue(), "image/png")
        if stored.key != storage_key:
            raise StorageError(
                "Storage adapter returned a different face-conditioning key."
            )
        return storage_key

    async def _verified_pilot_candidate(
        self,
        *,
        character: CharacterBible,
        anchor_key: str,
        anchor_bytes: bytes,
        approval: CharacterPilotApproval,
        expected_filename: str,
    ) -> CharacterCandidateAsset:
        if approval.character_id != character.character_id:
            raise ValueError("Pilot approval belongs to another character.")
        if approval.anchor_storage_key != anchor_key:
            raise ValueError("Pilot approval belongs to another anchor.")
        if hashlib.sha256(anchor_bytes).hexdigest() != approval.anchor_sha256:
            raise ValueError("Approved anchor changed after pilot review.")
        pilot_key = self._portable_key(approval.pilot_storage_key)
        if not await self._storage.exists(pilot_key):
            raise StorageError(f"Approved pilot '{pilot_key}' was not found.")
        pilot_bytes = await self._storage.load(pilot_key)
        if hashlib.sha256(pilot_bytes).hexdigest() != approval.pilot_sha256:
            raise ValueError("Approved pilot changed after human review.")
        if PurePosixPath(pilot_key).name != expected_filename:
            raise ValueError("Pilot approval does not reference the required first recipe.")
        width, height = self._validate_png_bytes(pilot_bytes)
        return CharacterCandidateAsset(
            filename=expected_filename,
            storage_key=pilot_key,
            provider_asset_id="human-approved-pilot",
            width=width,
            height=height,
            quality=None,
        )

    @staticmethod
    def _validate_png_bytes(data: bytes) -> tuple[int, int]:
        if not data.startswith(b"\x89PNG\r\n\x1a\n") or len(data) < 24:
            raise ValueError("Character pilot must be a valid PNG image.")
        width = int.from_bytes(data[16:20], "big")
        height = int.from_bytes(data[20:24], "big")
        if width <= 0 or height <= 0:
            raise ValueError("Character pilot has invalid image dimensions.")
        return width, height

    async def _save_candidate(
        self,
        *,
        storage_prefix: str,
        filename: str,
        generated: object,
        attempt: int = 1,
        quality=None,
    ) -> CharacterCandidateAsset:
        image_bytes = getattr(generated, "image_bytes", b"")
        content_type = str(getattr(generated, "content_type", ""))
        width = int(getattr(generated, "width", 0))
        height = int(getattr(generated, "height", 0))
        if (
            not image_bytes.startswith(b"\x89PNG\r\n\x1a\n")
            or content_type != "image/png"
            or width <= 0
            or height <= 0
        ):
            raise KeyframeGenerationError(
                "Character generator returned an invalid PNG candidate."
            )
        prefix = self._portable_key(storage_prefix)
        storage_key = f"{prefix}/{filename}"
        stored = await self._storage.save(storage_key, image_bytes, content_type)
        if stored.key != storage_key:
            raise StorageError(
                "Storage adapter returned a different character candidate key."
            )
        return CharacterCandidateAsset(
            filename=filename,
            storage_key=storage_key,
            provider_asset_id=str(getattr(generated, "provider_asset_id", "")),
            width=width,
            height=height,
            attempt=attempt,
            quality=quality,
        )

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
            raise ValueError("Character onboarding storage key must be portable.")
        return path.as_posix()
