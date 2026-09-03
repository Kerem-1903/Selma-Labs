from __future__ import annotations

import re
from typing import Any

from core.domain.entities.character_bible import CharacterBible
from core.domain.value_objects.character_identity import IdentityConstraints
from core.domain.value_objects.character_narrative_profile import (
    CharacterNarrativeProfile,
)
from core.domain.value_objects.outfit import Outfit
from core.domain.value_objects.style_profile import StyleProfile


class CharacterBibleFactoryService:
    """Turn a descriptive, provider-neutral brief into a Character Bible."""

    _VISUAL_FIELDS = (
        "eye_color",
        "hair",
        "facial_geometry",
        "body_proportions",
        "silhouette",
        "outfit",
        "base_style",
    )
    _NARRATIVE_FIELDS = ("motivation", "backstory")

    def create(self, brief: dict[str, Any]) -> CharacterBible:
        character_id = self._text(brief, "character_id")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", character_id):
            raise ValueError("Character brief requires a portable character_id.")
        display_name = self._text(brief, "display_name")
        visual = self._mapping(brief, "visual")
        narrative = self._mapping(brief, "narrative")
        missing = [
            field
            for field in self._VISUAL_FIELDS
            if not self._text(visual, field, required=False)
        ]
        missing.extend(
            f"narrative.{field}"
            for field in self._NARRATIVE_FIELDS
            if not self._text(narrative, field, required=False)
        )
        if missing:
            raise ValueError(
                f"Character brief is missing required fields: {', '.join(missing)}"
            )

        trigger_prompt = str(
            visual.get("trigger_prompt", f"{character_id.replace('-', '_')}_character")
        ).strip()
        immutable_marks = self._strings(visual.get("immutable_marks", []))
        palette = self._strings(visual.get("color_palette", []))
        negative_prompts = self._strings(visual.get("negative_prompts", []))
        voice_traits = self._strings(narrative.get("voice_traits", []))
        return CharacterBible(
            character_id=character_id,
            identity_constraints=IdentityConstraints(
                eye_color=self._text(visual, "eye_color"),
                hair=self._text(visual, "hair"),
                facial_geometry=self._text(visual, "facial_geometry"),
                body_proportions=self._text(visual, "body_proportions"),
                silhouette=self._text(visual, "silhouette"),
                trigger_prompt=trigger_prompt,
                immutable_marks=list(immutable_marks),
            ),
            style_profile=StyleProfile(
                base_style=self._text(visual, "base_style"),
                lighting_preferences=list(
                    self._strings(visual.get("lighting_preferences", []))
                ),
                color_palette=list(palette),
                negative_prompts=list(negative_prompts),
            ),
            outfit_catalog=[
                Outfit(
                    id=f"{character_id}-default",
                    character_id=character_id,
                    description=self._text(visual, "outfit"),
                    reference_image_keys=[],
                )
            ],
            narrative_profile=CharacterNarrativeProfile(
                canonical_names=(display_name,),
                motivation=self._text(narrative, "motivation"),
                backstory=self._text(narrative, "backstory"),
                voice_traits=voice_traits,
                allowed_abilities=self._strings(narrative.get("allowed_abilities", [])),
                forbidden_behaviors=self._strings(
                    narrative.get("forbidden_behaviors", [])
                ),
                forbidden_voice_phrases=self._strings(
                    narrative.get("forbidden_voice_phrases", [])
                ),
                locked=False,
            ),
        )

    @staticmethod
    def _mapping(payload: dict[str, Any], key: str) -> dict[str, Any]:
        value = payload.get(key)
        if not isinstance(value, dict):
            raise TypeError(f"Character brief '{key}' must be an object.")
        return value

    @staticmethod
    def _text(payload: dict[str, Any], key: str, *, required: bool = True) -> str:
        value = payload.get(key)
        text = value.strip() if isinstance(value, str) else ""
        if required and not text:
            raise ValueError(f"Character brief '{key}' must be non-empty text.")
        return text

    @staticmethod
    def _strings(value: Any) -> tuple[str, ...]:
        if not isinstance(value, list) or any(
            not isinstance(item, str) for item in value
        ):
            raise ValueError("Character brief list fields must contain text values.")
        return tuple(dict.fromkeys(item.strip() for item in value if item.strip()))
