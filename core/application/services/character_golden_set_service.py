from __future__ import annotations

from core.domain.entities.character_bible import CharacterBible
from core.domain.entities.character_golden_set import (
    CharacterGoldenSet,
    default_akira_golden_cases,
)
from core.domain.entities.direction_bible import BibleStatus, VisualStyleBible
from core.domain.exceptions import GoldenSetValidationError
from core.domain.ports.golden_image_generator_port import GoldenImageGeneratorPort
from core.domain.ports.golden_set_evaluator_port import GoldenSetEvaluatorPort
from core.domain.services.character_bible_validation_service import (
    CharacterBibleValidationService,
)


class CharacterGoldenSetService:
    def __init__(
        self, generator: GoldenImageGeneratorPort, evaluator: GoldenSetEvaluatorPort
    ) -> None:
        self._generator = generator
        self._evaluator = evaluator

    async def run(
        self,
        *,
        character: CharacterBible,
        style: VisualStyleBible,
        model_id: str,
        model_revision: str,
    ) -> CharacterGoldenSet:
        if style.status is not BibleStatus.LOCKED:
            raise GoldenSetValidationError("VisualStyleBible must be locked.")
        if not character.narrative_profile or not character.narrative_profile.locked:
            raise GoldenSetValidationError(
                "Character narrative profile must be locked."
            )
        reference_report = CharacterBibleValidationService().validate(character)
        if not reference_report.is_complete:
            raise GoldenSetValidationError("Character reference pack is incomplete.")
        results = []
        for test_case in default_akira_golden_cases():
            storage_key = await self._generator.generate(
                character=character, style=style, test_case=test_case
            )
            results.append(
                await self._evaluator.evaluate(
                    character=character,
                    style=style,
                    test_case=test_case,
                    storage_key=storage_key,
                )
            )
        return CharacterGoldenSet.create(
            character_id=character.character_id,
            model_id=model_id,
            model_revision=model_revision,
            results=tuple(results),
        )
