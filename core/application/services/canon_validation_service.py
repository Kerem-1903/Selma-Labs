"""Deterministic validation of structured scripts against locked canon."""

from __future__ import annotations

from core.domain.entities.character_bible import CharacterBible
from core.domain.entities.direction_bible import (
    BibleStatus,
    CreativeDirectionBible,
    WorldBible,
)
from core.domain.entities.episode_script import EpisodeScript
from core.domain.exceptions import PreProductionValidationError
from core.domain.value_objects.canon_validation import (
    CanonValidationReport,
    CanonViolation,
    CanonViolationCode,
)


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


class CanonValidationService:
    def validate(
        self,
        script: EpisodeScript,
        creative_direction: CreativeDirectionBible,
        world_bible: WorldBible,
        character_bibles: tuple[CharacterBible, ...],
    ) -> CanonValidationReport:
        self._require_locked_canon(creative_direction, world_bible, character_bibles)
        violations: list[CanonViolation] = []
        characters = {
            _normalized(name): bible
            for bible in character_bibles
            if bible.narrative_profile
            for name in bible.narrative_profile.canonical_names
        }
        locations = {
            _normalized(value)
            for location in world_bible.locations
            for value in (location.id, location.name, *location.aliases)
        }

        for scene in script.scenes:
            if _normalized(scene.location) not in locations:
                violations.append(
                    CanonViolation(
                        CanonViolationCode.UNKNOWN_LOCATION,
                        f"Scene uses unknown location '{scene.location}'.",
                        scene.id,
                        scene.location,
                    )
                )
            scene_characters: list[CharacterBible] = []
            for name in scene.characters:
                bible = characters.get(_normalized(name))
                if bible is None:
                    violations.append(
                        CanonViolation(
                            CanonViolationCode.UNKNOWN_CHARACTER,
                            f"Scene uses unknown character '{name}'.",
                            scene.id,
                            name,
                        )
                    )
                else:
                    scene_characters.append(bible)

            scene_text = _normalized(scene.full_text)
            for rule in world_bible.rules:
                for phrase in rule.forbidden_phrases:
                    if _normalized(phrase) in scene_text:
                        violations.append(
                            CanonViolation(
                                CanonViolationCode.WORLD_RULE_VIOLATION,
                                f"Scene violates world rule '{rule.id}'.",
                                scene.id,
                                phrase,
                            )
                        )
            for bible in scene_characters:
                profile = bible.narrative_profile
                assert profile is not None
                for behavior in profile.forbidden_behaviors:
                    if _normalized(behavior) in scene_text:
                        violations.append(
                            CanonViolation(
                                CanonViolationCode.CHARACTER_MOTIVATION_CONFLICT,
                                f"{profile.canonical_names[0]} performs canon-forbidden behavior.",
                                scene.id,
                                behavior,
                            )
                        )

            for line in scene.dialogue:
                speaker = characters.get(_normalized(line.speaker))
                if speaker is None:
                    violations.append(
                        CanonViolation(
                            CanonViolationCode.UNKNOWN_CHARACTER,
                            f"Dialogue uses unknown speaker '{line.speaker}'.",
                            scene.id,
                            line.speaker,
                        )
                    )
                    continue
                profile = speaker.narrative_profile
                assert profile is not None
                for phrase in profile.forbidden_voice_phrases:
                    if _normalized(phrase) in _normalized(line.text):
                        violations.append(
                            CanonViolation(
                                CanonViolationCode.CHARACTER_VOICE_MISMATCH,
                                f"Dialogue conflicts with {profile.canonical_names[0]}'s voice profile.",
                                scene.id,
                                phrase,
                            )
                        )

            for use in scene.ability_uses:
                character = characters.get(_normalized(use.character))
                allowed = (
                    {
                        _normalized(value)
                        for value in character.narrative_profile.allowed_abilities
                    }
                    if character and character.narrative_profile
                    else set()
                )
                if character is None or _normalized(use.ability) not in allowed:
                    violations.append(
                        CanonViolation(
                            CanonViolationCode.UNAUTHORIZED_POWER,
                            f"'{use.ability}' is not authorized for '{use.character}'.",
                            scene.id,
                            use.ability,
                        )
                    )

        script_text = _normalized(script.full_text)
        for marker in creative_direction.originality_guardrails:
            if _normalized(marker) in script_text:
                violations.append(
                    CanonViolation(
                        CanonViolationCode.STYLE_IMITATION_RISK,
                        "Script contains a prohibited imitation marker.",
                        evidence=marker,
                    )
                )
        return CanonValidationReport(tuple(violations))

    @staticmethod
    def _require_locked_canon(
        direction: CreativeDirectionBible,
        world: WorldBible,
        characters: tuple[CharacterBible, ...],
    ) -> None:
        if (
            direction.status is not BibleStatus.LOCKED
            or world.status is not BibleStatus.LOCKED
        ):
            raise PreProductionValidationError(
                "Creative direction and world bible must be locked."
            )
        if not characters:
            raise PreProductionValidationError(
                "At least one CharacterBible is required."
            )
        if any(
            not bible.narrative_profile or not bible.narrative_profile.locked
            for bible in characters
        ):
            raise PreProductionValidationError(
                "Every CharacterBible requires a locked narrative profile."
            )
