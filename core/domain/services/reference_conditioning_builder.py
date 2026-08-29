from __future__ import annotations

from core.domain.entities.character_bible import CharacterBible
from core.domain.entities.shot_contract import ShotContract
from core.domain.exceptions import ReferenceConditioningError
from core.domain.value_objects.keyframe_generation_request import KeyframeGenerationRequest


class ReferenceConditioningBuilder:
    """Translate A3 identity assets and A4 continuity into typed conditioning."""

    def build(
        self,
        *,
        shot_contract: ShotContract,
        character_bibles: list[CharacterBible],
        width: int = 1024,
        height: int = 1024,
        seed: int | None = None,
    ) -> KeyframeGenerationRequest:
        bibles_by_id: dict[str, CharacterBible] = {}
        for bible in character_bibles:
            if bible.character_id in bibles_by_id:
                raise ReferenceConditioningError(
                    f"Duplicate character bible for '{bible.character_id}'."
                )
            bibles_by_id[bible.character_id] = bible

        conditioning: list[dict] = []
        reference_asset_ids: list[str] = []
        reference_storage_keys: list[str] = []
        negative_prompts: list[str] = []

        for state in shot_contract.required_character_states:
            bible = bibles_by_id.get(state.character_id)
            if bible is None:
                raise ReferenceConditioningError(
                    f"Character bible '{state.character_id}' is required by the shot."
                )
            references = sorted(
                bible.reference_pack.values(), key=lambda item: item.view.value
            )
            if not references:
                raise ReferenceConditioningError(
                    f"Character bible '{state.character_id}' has no reference assets."
                )
            if any(not reference.asset_id or not reference.storage_key for reference in references):
                raise ReferenceConditioningError(
                    f"Character bible '{state.character_id}' contains an invalid reference."
                )

            outfit = next(
                (
                    item
                    for item in bible.outfit_catalog
                    if item.id == state.active_outfit_id
                ),
                None,
            )
            conditioning.append(
                {
                    "character_id": state.character_id,
                    "identity_constraints": bible.identity_constraints.to_dict(),
                    "style_profile": bible.style_profile.to_dict(),
                    "continuity_state": state.to_dict(),
                    "active_outfit": None if outfit is None else outfit.to_dict(),
                    "references": [reference.to_dict() for reference in references],
                }
            )
            for reference in references:
                reference_asset_ids.append(reference.asset_id)
                reference_storage_keys.append(reference.storage_key)
            negative_prompts.extend(bible.style_profile.negative_prompts)

        return KeyframeGenerationRequest(
            shot_contract_id=shot_contract.id,
            camera_constraints=shot_contract.camera_constraints.to_dict(),
            action_constraints=shot_contract.action_constraints.to_dict(),
            visual_constraints=shot_contract.visual_constraints.to_dict(),
            character_conditioning=tuple(conditioning),
            reference_asset_ids=tuple(reference_asset_ids),
            reference_storage_keys=tuple(reference_storage_keys),
            negative_prompts=tuple(dict.fromkeys(negative_prompts)),
            width=width,
            height=height,
            seed=seed,
        )
