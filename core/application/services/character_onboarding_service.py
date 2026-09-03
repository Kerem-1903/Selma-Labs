"""Automate repeatable character reference creation before animation."""

from __future__ import annotations

import hashlib
from pathlib import PurePosixPath

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
    _RECIPES = (
        (
            "face-closeup-neutral-01.png",
            "FACE_CLOSEUP",
            "train",
            "face close-up, neutral expression",
        ),
        (
            "face-closeup-determined-02.png",
            "FACE_CLOSEUP",
            "train",
            "face close-up, determined expression",
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
        if not identity:
            raise ValueError("Character Bible contains no usable prompt fragments.")
        seed_base = int(
            hashlib.sha256(character.character_id.encode("utf-8")).hexdigest()[:8], 16
        )
        anchor_prompt = (
            f"{cls._QUALITY}, solo, {identity}, full body front view, neutral standing "
            "pose, plain light background, entire head and both feet visible"
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
                )
            ),
            recipes=recipes,
        )

    async def generate_anchor(
        self,
        character: CharacterBible,
        *,
        output_prefix: str = "character-candidates",
    ) -> CharacterCandidateAsset:
        plan = self.plan(character)
        generated = await self._generator.generate_keyframe(
            self._request(
                character=character,
                prompt=plan.anchor_prompt,
                seed=plan.anchor_seed,
                negatives=plan.negative_prompts,
            )
        )
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
        candidates = []
        quarantined = []
        anchor_bytes = await self._storage.load(anchor_key)
        for recipe in plan.recipes:
            accepted = None
            for attempt in range(1, self._max_attempts + 1):
                generated = await self._generator.generate_keyframe(
                    self._request(
                        character=character,
                        prompt=recipe.prompt,
                        seed=recipe.seed + (attempt - 1) * 10_000,
                        negatives=plan.negative_prompts,
                        anchor_storage_key=anchor_key,
                    )
                )
                quality = None
                if self._evaluator is not None:
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
        return KeyframeGenerationRequest(
            shot_contract_id=f"character-onboarding-{character.character_id}-{seed}",
            camera_constraints={
                "angle": "full body",
                "lens": "50mm",
                "movement": "locked",
            },
            action_constraints={"primary_action": prompt, "secondary_actions": []},
            visual_constraints={
                "lighting": "neutral controlled studio light",
                "environment_style": "plain reference background",
                "weather": "clear",
                "identity_strength": 0.85,
                "identity_mode": "identity_only",
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
