"""Automate repeatable character reference creation before animation."""

from __future__ import annotations

import hashlib
import io
from collections.abc import Mapping
from dataclasses import replace
from dataclasses import replace as _dataclass_replace
from datetime import datetime, timezone
from pathlib import PurePosixPath

from PIL import Image, UnidentifiedImageError

from core.application.services.streak_pre_gate import StreakPreGate
from core.application.services.view_framing_gate import ViewFramingGate
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
        streak_pre_gate: StreakPreGate | None = None,
        framing_gate: ViewFramingGate | None = None,
        style_refine: bool = False,
    ) -> None:
        if max_attempts <= 0:
            raise ValueError("Character generation attempts must be greater than zero.")
        self._generator = generator
        self._storage = storage
        self._evaluator = evaluator
        self._max_attempts = max_attempts
        self._streak_pre_gate = streak_pre_gate
        self._framing_gate = framing_gate
        self._style_refine = style_refine

    @classmethod
    def plan(cls, character: CharacterBible) -> CharacterOnboardingPlan:
        anchor_identity = ", ".join(
            character.prompt_fragments_for_view("FULL_BODY")
        )
        immutable_marks = "; ".join(character.identity_constraints.immutable_marks)
        if not anchor_identity:
            raise ValueError("Character Bible contains no usable prompt fragments.")
        seed_base = int(
            hashlib.sha256(character.character_id.encode("utf-8")).hexdigest()[:8], 16
        )
        anchor_prompt = (
            f"{cls._QUALITY}, solo, {anchor_identity}, full body front view, neutral standing "
            "pose, plain light background, entire head and both feet visible, "
            f"immutable identity marks exactly once with no duplicates: {immutable_marks}"
        )
        recipes = tuple(
            CharacterReferenceRecipe(
                filename=filename,
                view=view,
                split=split,
                prompt=(
                    f"{cls._QUALITY}, solo, "
                    f"{', '.join(character.prompt_fragments_for_view(view))}, "
                    f"{direction}, plain light background"
                ),
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
                    "identity_strength": 0.6,
                    "identity_weight_type": "weak input",
                    "identity_combine_embeds": "average",
                    "identity_end_at": 0.65,
                    "identity_embeds_scaling": "K+V w/ C penalty",
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
        recipe_offset: int = 0,
        automatic_review: bool = True,
        pilot_approval: CharacterPilotApproval | None = None,
        seed_offset: int = 0,
        pose_references: Mapping[str, str] | None = None,
    ) -> CharacterCandidatePack:
        if seed_offset < 0 or seed_offset % 10_000 != 0:
            raise ValueError(
                "Character reference seed offset must be a non-negative multiple of 10000."
            )
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
        if recipe_offset < 0 or recipe_offset >= len(plan.recipes):
            raise ValueError(
                f"Character recipe offset must be between 0 and {len(plan.recipes) - 1}."
            )
        remaining = len(plan.recipes) - recipe_offset
        if recipe_limit is not None and not 1 <= recipe_limit <= remaining:
            raise ValueError(
                f"Character recipe limit must be between 1 and {remaining} "
                "for the given recipe offset."
            )
        recipes = plan.recipes[
            recipe_offset : (
                recipe_offset + recipe_limit if recipe_limit is not None else None
            )
        ]
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
            if recipe_offset == 0:
                # The first recipe is the approved face pilot itself; it was
                # never generated by this pack and is now a verified candidate.
                recipes = recipes[1:]
        pose_references = await self._verified_pose_references(
            recipes=recipes, pose_references=pose_references
        )
        streak_mark = (
            self._streak_pre_gate.calibrated_mark(character)
            if self._streak_pre_gate is not None
            else None
        )
        for recipe in recipes:
            accepted = None
            gate_applicable = (
                self._streak_pre_gate is not None
                and streak_mark is not None
                and self._streak_pre_gate.applicable_for(recipe.view)
            )
            conditioning_key = await self._conditioning_reference_for_view(
                anchor_bytes=anchor_bytes,
                anchor_key=anchor_key,
                run_root=run_root,
                view=recipe.view,
            )
            framing_applicable = (
                self._framing_gate is not None
                and self._framing_gate.applicable_for(recipe.view)
            )
            attempts = (
                self._max_attempts
                if automatic_review
                and (
                    self._evaluator is not None
                    or gate_applicable
                    or framing_applicable
                )
                else 1
            )
            for attempt in range(1, attempts + 1):
                seed = recipe.seed + seed_offset + (attempt - 1) * 10_000
                generated = await self._generator.generate_keyframe(
                    self._request(
                        character=character,
                        prompt=recipe.prompt,
                        seed=seed,
                        negatives=self._negatives_for_view(
                            plan.negative_prompts, recipe.view
                        ),
                        anchor_storage_key=conditioning_key,
                        view=recipe.view,
                        pose_storage_key=(
                            pose_references.get(recipe.view)
                            if pose_references is not None
                            else None
                        ),
                    )
                )
                pre_gate_note = None
                if automatic_review and gate_applicable and streak_mark is not None:
                    gate = self._streak_pre_gate.evaluate(
                        image_bytes=generated.image_bytes,
                        mark=streak_mark,
                    )
                    if not gate.passed:
                        candidate = await self._save_candidate(
                            storage_prefix=f"{run_root}/quarantine",
                            filename=f"attempt-{attempt}-{recipe.filename}",
                            generated=generated,
                            attempt=attempt,
                            quality=None,
                            gate_note=f"streak pre-gate reject: {gate.reason}",
                        )
                        quarantined.append(candidate)
                        continue
                    pre_gate_note = gate.reason
                framing_note = None
                if automatic_review and framing_applicable:
                    framing = self._framing_gate.evaluate(
                        image_bytes=generated.image_bytes,
                        view=recipe.view,
                    )
                    if not framing.passed:
                        candidate = await self._save_candidate(
                            storage_prefix=f"{run_root}/quarantine",
                            filename=f"attempt-{attempt}-{recipe.filename}",
                            generated=generated,
                            attempt=attempt,
                            quality=None,
                            gate_note=f"framing gate reject: {framing.reason}",
                        )
                        quarantined.append(candidate)
                        continue
                    framing_note = framing.reason
                active_generated = generated
                refine_note = None
                if (
                    automatic_review
                    and self._style_refine
                    and CharacterOnboardingService._composition_mode(recipe.view)
                    == "empty"
                ):
                    refined = await self._style_refine_pass(
                        character=character,
                        recipe=recipe,
                        plan_negatives=plan.negative_prompts,
                        seed=seed,
                        run_root=run_root,
                        image_bytes=generated.image_bytes,
                        view=recipe.view,
                    )
                    if refined is None:
                        refine_note = "style refine unavailable; kept base"
                    elif framing_applicable and not self._framing_gate.evaluate(
                        image_bytes=refined.image_bytes, view=recipe.view
                    ).passed:
                        refine_note = "style refine framing regressed; kept base"
                    else:
                        active_generated = refined
                        refine_note = "style refine applied"
                quality = None
                if automatic_review and self._evaluator is not None:
                    quality = await self._evaluator.evaluate(
                        image_bytes=active_generated.image_bytes,
                        reference_bytes=anchor_bytes,
                        context=(
                            f"Character: {character.character_id}. Required recipe: "
                            f"{recipe.prompt}. Preserve face, hair, outfit, marks, "
                            "anatomy and requested framing."
                        ),
                        subject_policy="character_required",
                    )
                passed = quality is not None and quality.passed
                candidate = await self._save_candidate(
                    storage_prefix=f"{run_root}/{'source' if passed else 'quarantine'}",
                    filename=(
                        recipe.filename
                        if passed
                        else f"attempt-{attempt}-{recipe.filename}"
                    ),
                    generated=active_generated,
                    attempt=attempt,
                    quality=quality,
                    gate_note="; ".join(
                        note
                        for note in (pre_gate_note, framing_note, refine_note)
                        if note
                    )
                    or None,
                )
                if passed:
                    accepted = candidate
                    break
                quarantined.append(candidate)
            if accepted is None:
                continue
            candidates.append(accepted)
        return CharacterCandidatePack(
            schema_version=1,
            character_id=character.character_id,
            anchor_storage_key=anchor_key,
            candidates=tuple(candidates),
            quarantined=tuple(quarantined),
        )

    async def _style_refine_pass(
        self,
        *,
        character: CharacterBible,
        recipe,
        plan_negatives: tuple[str, ...],
        seed: int,
        run_root: str,
        image_bytes: bytes,
        view: str,
    ):
        """Anchor-style self-refinement.

        The txt2img composition pass frees framing but renders flatter than
        the approved anchor (which was refined through img2img passes). A
        low-denoise img2img pass on the frame's OWN output adds the anchor's
        finished shading and detail while the source image already carries
        the correct full-body / three-quarter composition.
        """
        refine_key = f"{run_root}/refine/{recipe.filename}.{seed}.png"
        stored = await self._storage.save(refine_key, image_bytes, "image/png")
        refine_key = self._portable_key(stored.key)
        request = self._request(
            character=character,
            prompt=recipe.prompt,
            seed=seed + 7_777,
            negatives=self._negatives_for_view(plan_negatives, view),
            anchor_storage_key=refine_key,
            view=view,
        )
        request = _dataclass_replace(
            request,
            visual_constraints={
                **request.visual_constraints,
                "latent_mode": "reference",
                "reference_denoise": 0.45,
                "identity_strength": 0.7,
                "extra_tags": "highly detailed, sharp focus, crisp lineart",
            },
        )
        try:
            return await self._generator.generate_keyframe(request)
        except Exception as error:  # noqa: BLE001 - keep the composition-pass frame
            print(f"style refine failed for {recipe.filename}: {error}")
            return None

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
        if "quarantine" in {
            part.casefold() for part in PurePosixPath(pilot_key).parts
        }:
            raise ValueError("quarantined pilot candidates cannot be approved.")
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
            parts = tuple(part.casefold() for part in PurePosixPath(storage_key).parts)
            if "quarantine" in parts or "source" not in parts:
                raise ValueError(
                    "Reference approval accepts only automatically reviewed source assets."
                )
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
        pose_storage_key: str | None = None,
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
        composition_mode = CharacterOnboardingService._composition_mode(view)
        if composition_mode == "empty":
            # Validated: full-body / three-quarter views need free composition
            # (empty latent, denoise 1.0). Identity then comes from the
            # IP-Adapter at 0.85; below ~0.75 identity drifts, above ~1.0 the
            # framing locks back to the face-closeup anchor.
            identity_strength = 0.85
        identity = character.identity_constraints
        face_only = character.is_face_only_view(view)
        action_view = view.startswith("ACTION_")
        visible_costume = (
            ()
            if face_only
            else (
                character.upper_body_costume_fragments()
                if "UPPER_BODY" in view or view == "FRONT"
                else character.costume_fragments()
            )
        )
        identity_marks = tuple(
            mark
            for mark in identity.immutable_marks
            if not character.is_prop_fragment(mark)
        )
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
                    "body_proportions": identity.body_proportions,
                    "silhouette": ", ".join(visible_costume),
                    "immutable_marks": (
                        (*identity_marks, *character.prop_fragments())
                        if action_view
                        else identity_marks
                    ),
                    "outfit": ", ".join(visible_costume),
                },
                "identity_strength": identity_strength,
                "identity_mode": "identity_only",
                "identity_weight_type": "weak input",
                "identity_combine_embeds": "average",
                "identity_start_at": 0.0,
                "identity_end_at": 0.65,
                "identity_embeds_scaling": "K+V w/ C penalty",
                "reference_denoise": CharacterOnboardingService._denoise_for_view(
                    view
                ),
                "latent_mode": composition_mode,
                "extra_tags": CharacterOnboardingService._extra_tags_for_view(
                    view, composition_mode
                ),
                **(
                    {
                        "pose_storage_key": pose_storage_key,
                        "controlnet_type": "openpose",
                        "pose_strength": 0.8,
                    }
                    if pose_storage_key
                    else {}
                ),
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
                0.6,
            )
        if view.startswith("PROFILE"):
            return (
                {"angle": "strict profile portrait", "lens": "70mm", "movement": "locked"},
                "single character profile; head and torso readable; no front-facing pose",
                0.58,
            )
        if view.startswith("ACTION"):
            return (
                {"angle": "full body action", "lens": "50mm", "movement": "locked"},
                "single complete body; head, hands and feet visible; action silhouette clear",
                0.55,
            )
        if view in {"FULL_BODY", "BACK"}:
            return (
                {"angle": "full body", "lens": "50mm", "movement": "locked"},
                "single complete body; entire head and both feet visible",
                0.58,
            )
        return (
            {"angle": "upper-body portrait", "lens": "65mm", "movement": "locked"},
            "single character upper-body portrait; face, hair and outfit construction readable",
            0.6,
        )

    @staticmethod
    def _composition_mode(view: str) -> str:
        """Text-to-image composition (empty latent, denoise 1.0) frees framing
        and body pose from the face-closeup anchor. Face/chest-up views keep
        reference-img2img so identity stays tightly locked."""
        if view in {"FULL_BODY", "THREE_QUARTER_LEFT", "THREE_QUARTER_RIGHT"}:
            return "empty"
        return "reference"

    @staticmethod
    def _extra_tags_for_view(view: str, composition_mode: str) -> str:
        if composition_mode != "empty":
            return ""
        # Anchor-consistent presentation: the approved anchor carries a
        # softly shaded gradient background and clean cinematic shading.
        # Empty-latent generation defaults to a flat uniform background,
        # which reads as plainer than the anchor (measured bg texture std
        # ~3-32 vs ~59 for the anchor); these tokens close that gap.
        style = "clean cinematic anime shading, soft gradient studio background"
        if view == "FULL_BODY":
            return f"1girl, solo, standing, {style}"
        return f"1girl, solo, {style}"

    @staticmethod
    def _denoise_for_view(view: str) -> float:
        if view == "FACE_CLOSEUP":
            return 0.38
        if view.startswith("ACTION"):
            return 0.72
        if view in {"FULL_BODY", "BACK"} or "FULL_BODY" in view:
            return 0.62
        return 0.52

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
        # Large square anchors are already portrait crops. Cropping their top
        # quarter again removes the face and makes FaceID conditioning fail.
        if image.width == image.height and image.width >= 512:
            crop = image.resize((1024, 1024), Image.Resampling.LANCZOS)
        else:
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
        gate_note: str | None = None,
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
            gate_note=gate_note,
        )

    async def _verified_pose_references(
        self,
        *,
        recipes: tuple[CharacterReferenceRecipe, ...],
        pose_references: Mapping[str, str] | None,
    ) -> Mapping[str, str] | None:
        """Resolve ACTION_* pose maps against the storage, fail-closed."""
        action_views = {
            recipe.view
            for recipe in recipes
            if recipe.view.startswith("ACTION_")
        }
        if pose_references is None:
            if action_views:
                raise ValueError(
                    "Guarded action generation requires an OpenPose reference for "
                    "every action view in the batch; missing: "
                    + ", ".join(sorted(action_views))
                )
            return None
        unknown = sorted(
            view for view in pose_references if not view.startswith("ACTION_")
        )
        if unknown:
            raise ValueError(
                "Pose references may only target ACTION_* views: "
                + ", ".join(unknown)
            )
        missing = sorted(action_views - set(pose_references))
        if missing:
            raise ValueError(
                "Guarded action generation requires an OpenPose reference for "
                "every action view in the batch; missing: " + ", ".join(missing)
            )
        png_magic = bytes((0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A))
        resolved: dict[str, str] = {}
        for view, raw_key in pose_references.items():
            storage_key = self._portable_key(raw_key)
            if not await self._storage.exists(storage_key):
                raise StorageError(f"Pose reference '{storage_key}' was not found.")
            data = await self._storage.load(storage_key)
            if not data.startswith(png_magic):
                raise StorageError(
                    f"Pose reference '{storage_key}' must be a PNG image."
                )
            resolved[view] = storage_key
        return resolved

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
