"""Generate consistent, character-free location coverage before animation."""

from __future__ import annotations

import hashlib
from pathlib import PurePosixPath

from core.domain.entities.location_bible import LocationBible
from core.domain.exceptions import KeyframeGenerationError
from core.domain.ports.depth_map_generator_port import DepthMapGeneratorPort
from core.domain.ports.keyframe_generation_port import KeyframeGenerationPort
from core.domain.ports.preproduction_image_evaluator_port import (
    PreproductionImageEvaluatorPort,
)
from core.domain.ports.storage_port import StoragePort
from core.domain.value_objects.background_production import (
    BackgroundCandidate,
    BackgroundCandidatePack,
    BackgroundProductionPlan,
    BackgroundRecipe,
)
from core.domain.value_objects.keyframe_generation_request import (
    KeyframeGenerationRequest,
)


class BackgroundFactoryService:
    _NEGATIVES = (
        "person",
        "people",
        "character",
        "human",
        "silhouette",
        "crowd",
        "text",
        "logo",
        "watermark",
        "warped architecture",
        "inconsistent perspective",
    )
    _COVERAGE = tuple(
        (scale, angle)
        for scale in ("wide establishing", "medium", "close detail")
        for angle in ("front", "left three-quarter", "right three-quarter", "reverse")
    )

    def __init__(
        self,
        generator: KeyframeGenerationPort,
        storage: StoragePort,
        evaluator: PreproductionImageEvaluatorPort | None = None,
        depth_mapper: DepthMapGeneratorPort | None = None,
        *,
        max_attempts: int = 3,
    ) -> None:
        if max_attempts <= 0:
            raise ValueError("Background generation attempts must be positive.")
        self._generator = generator
        self._storage = storage
        self._evaluator = evaluator
        self._depth_mapper = depth_mapper
        self._max_attempts = max_attempts

    @classmethod
    def plan(cls, location: LocationBible) -> BackgroundProductionPlan:
        identity = ", ".join(location.prompt_fragments())
        weather = location.weather_options[0]
        seed_base = int(
            hashlib.sha256(location.location_id.encode("utf-8")).hexdigest()[:8], 16
        )
        recipes = tuple(
            BackgroundRecipe(
                recipe_id=f"{scale.split()[0]}-{index:02d}",
                shot_scale=scale,
                camera_angle=angle,
                weather=weather,
                prompt=(
                    f"masterpiece anime background plate, {identity}, {scale}, "
                    f"{angle} camera, {weather} weather, environment only, empty scene, "
                    "stable architectural geometry, clean foreground midground and "
                    "background separation"
                ),
                seed=seed_base + index,
            )
            for index, (scale, angle) in enumerate(cls._COVERAGE, 1)
        )
        return BackgroundProductionPlan(
            schema_version=1,
            location_id=location.location_id,
            negative_prompts=tuple(
                dict.fromkeys((*cls._NEGATIVES, *location.forbidden_elements))
            ),
            recipes=recipes,
        )

    async def generate(
        self,
        location: LocationBible,
        *,
        output_prefix: str = "background-candidates",
    ) -> BackgroundCandidatePack:
        plan = self.plan(location)
        safe_prefix = self._portable_key(output_prefix)
        accepted: list[BackgroundCandidate] = []
        quarantined: list[BackgroundCandidate] = []
        for recipe in plan.recipes:
            selected = None
            for attempt in range(1, self._max_attempts + 1):
                generated = await self._generator.generate_keyframe(
                    KeyframeGenerationRequest(
                        shot_contract_id=(
                            f"background-{location.location_id}-{recipe.recipe_id}-{attempt}"
                        ),
                        camera_constraints={
                            "angle": recipe.camera_angle,
                            "shot_scale": recipe.shot_scale,
                            "movement": "locked",
                        },
                        action_constraints={"primary_action": "empty environment"},
                        visual_constraints={
                            "environment_style": recipe.prompt,
                            "weather": recipe.weather,
                            "layer_separation": [
                                "background",
                                "midground",
                                "foreground",
                            ],
                            "depth_map_required": True,
                        },
                        negative_prompts=plan.negative_prompts,
                        width=1344,
                        height=768,
                        seed=recipe.seed + (attempt - 1) * 10_000,
                    )
                )
                quality = None
                if self._evaluator is not None:
                    quality = await self._evaluator.evaluate(
                        image_bytes=generated.image_bytes,
                        reference_bytes=None,
                        context=(
                            f"Location {location.name}. Canonical geometry: "
                            f"{', '.join(location.immutable_geometry)}. Required shot: "
                            f"{recipe.shot_scale}, {recipe.camera_angle}. The plate must "
                            "contain no people or characters."
                        ),
                        subject_policy="character_forbidden",
                    )
                passed = quality is None or quality.passed
                if (
                    not generated.image_bytes.startswith(b"\x89PNG\r\n\x1a\n")
                    or generated.content_type != "image/png"
                    or generated.width <= 0
                    or generated.height <= 0
                ):
                    raise KeyframeGenerationError(
                        "Background generator returned an invalid PNG candidate."
                    )
                filename = f"{recipe.recipe_id}.png"
                if not passed:
                    filename = f"attempt-{attempt}-{filename}"
                storage_key = (
                    f"{safe_prefix}/{location.location_id}/"
                    f"{'source' if passed else 'quarantine'}/{filename}"
                )
                stored = await self._storage.save(
                    storage_key, generated.image_bytes, generated.content_type
                )
                depth_key = None
                if passed and self._depth_mapper is not None:
                    depth = await self._depth_mapper.generate_depth_map(
                        generated.image_bytes
                    )
                    if (
                        not depth.image_bytes.startswith(b"\x89PNG\r\n\x1a\n")
                        or depth.content_type != "image/png"
                        or depth.width != generated.width
                        or depth.height != generated.height
                    ):
                        raise KeyframeGenerationError(
                            "Depth provider returned an invalid or misaligned PNG."
                        )
                    depth_stored = await self._storage.save(
                        f"{safe_prefix}/{location.location_id}/depth/"
                        f"{recipe.recipe_id}.png",
                        depth.image_bytes,
                        depth.content_type,
                    )
                    depth_key = depth_stored.key
                candidate = BackgroundCandidate(
                    recipe_id=recipe.recipe_id,
                    storage_key=stored.key,
                    width=generated.width,
                    height=generated.height,
                    attempt=attempt,
                    quality=quality,
                    depth_map_storage_key=depth_key,
                )
                if passed:
                    selected = candidate
                    break
                quarantined.append(candidate)
            if selected is None:
                raise KeyframeGenerationError(
                    f"Background '{recipe.recipe_id}' failed automatic quality review "
                    f"after {self._max_attempts} attempts."
                )
            accepted.append(selected)
        return BackgroundCandidatePack(
            location_id=location.location_id,
            candidates=tuple(accepted),
            quarantined=tuple(quarantined),
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
            raise ValueError("Background storage prefix must be portable.")
        return path.as_posix()
