"""Adapt any existing keyframe engine to the ten-case Golden Set contract."""

from __future__ import annotations

from pathlib import PurePosixPath

from core.domain.entities.character_bible import CharacterBible
from core.domain.entities.character_golden_set import GoldenTestCase
from core.domain.entities.direction_bible import VisualStyleBible
from core.domain.exceptions import GoldenSetValidationError
from core.domain.ports.golden_image_generator_port import GoldenImageGeneratorPort
from core.domain.ports.keyframe_generation_port import KeyframeGenerationPort
from core.domain.ports.storage_port import StoragePort
from core.domain.value_objects.keyframe_generation_request import (
    KeyframeGenerationRequest,
)


class GoldenSetKeyframeAdapter(GoldenImageGeneratorPort):
    def __init__(
        self,
        generator: KeyframeGenerationPort,
        storage: StoragePort,
        output_prefix: str = "golden",
    ) -> None:
        self._generator = generator
        self._storage = storage
        self._prefix = output_prefix.strip("/")

    async def generate(
        self,
        *,
        character: CharacterBible,
        style: VisualStyleBible,
        test_case: GoldenTestCase,
    ) -> str:
        references = [
            character.reference_pack[view]
            for view in test_case.required_views
            if view in character.reference_pack
        ]
        if not references:
            raise GoldenSetValidationError(
                f"No required reference is registered for {test_case.scenario.value}."
            )
        prompt = ", ".join(
            (
                *character.prompt_fragments(),
                test_case.prompt,
                style.line_language,
                style.shading_language,
                style.camera_language,
            )
        )
        request = KeyframeGenerationRequest(
            shot_contract_id=f"golden-{character.character_id}-{test_case.scenario.value.lower()}",
            camera_constraints={"scenario": test_case.scenario.value},
            action_constraints={"primary_action": test_case.prompt},
            visual_constraints={"prompt": prompt, "identity_strength": 0.85},
            reference_asset_ids=tuple(reference.asset_id for reference in references),
            reference_storage_keys=tuple(
                reference.storage_key for reference in references
            ),
            negative_prompts=tuple(
                dict.fromkeys(
                    (
                        *character.style_profile.negative_prompts,
                        *style.prohibited_traits,
                    )
                )
            ),
            width=1024,
            height=1024,
            seed=test_case.seed,
        )
        generated = await self._generator.generate_keyframe(request)
        suffix = {"image/jpeg": ".jpg", "image/webp": ".webp"}.get(
            generated.content_type, ".png"
        )
        key = (
            PurePosixPath(self._prefix)
            / character.character_id
            / f"{test_case.scenario.value.lower()}-{test_case.seed}{suffix}"
        ).as_posix()
        await self._storage.save(key, generated.image_bytes, generated.content_type)
        return key
