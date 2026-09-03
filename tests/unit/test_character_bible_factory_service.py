from __future__ import annotations

import json

import pytest

from cli.main import main
from core.application.services.character_bible_factory_service import (
    CharacterBibleFactoryService,
)


def _brief():
    return {
        "character_id": "nova",
        "display_name": "Nova",
        "visual": {
            "eye_color": "emerald green",
            "hair": "long silver braided hair",
            "facial_geometry": "round adult face",
            "body_proportions": "tall athletic adult",
            "silhouette": "long navy coat and energy bow",
            "outfit": "navy coat, black trousers, black boots",
            "base_style": "cinematic science-fantasy anime",
            "immutable_marks": ["silver braid", "emerald eyes"],
            "color_palette": ["navy", "silver", "emerald"],
            "negative_prompts": ["short hair", "blue eyes"],
        },
        "narrative": {
            "motivation": "Find a route home.",
            "backstory": "A navigator stranded in a floating city.",
            "voice_traits": ["precise", "quiet"],
            "allowed_abilities": ["Vector Sight"],
            "forbidden_behaviors": ["abandons her crew"],
        },
    }


def test_factory_turns_brief_into_unlocked_character_bible():
    bible = CharacterBibleFactoryService().create(_brief())

    assert bible.character_id == "nova"
    assert bible.trigger_prompt == "nova_character"
    assert bible.outfit_catalog[0].id == "nova-default"
    assert "long silver braided hair" in bible.prompt_fragments()
    assert bible.narrative_profile is not None
    assert bible.narrative_profile.locked is False


def test_factory_rejects_incomplete_visual_identity():
    brief = _brief()
    del brief["visual"]["hair"]

    with pytest.raises(ValueError, match="hair"):
        CharacterBibleFactoryService().create(brief)


def test_cli_initializes_bible_from_brief(tmp_path, capsys):
    source = tmp_path / "brief.json"
    output = tmp_path / "nova.json"
    source.write_text(json.dumps(_brief()), encoding="utf-8")

    assert (
        main(["character", "init", "--brief", str(source), "--output", str(output)])
        == 0
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["character_bible"]["character_id"] == "nova"
    assert payload["character_bible"]["narrative_profile"]["locked"] is False
    assert capsys.readouterr().out.strip() == str(output.resolve())
