from __future__ import annotations

import pytest

from core.domain.entities.character_bible import CharacterBible
from core.domain.entities.character_state import CharacterState
from core.domain.entities.shot_animation import ShotPlan
from core.domain.value_objects.render_config import RenderConfig


def _plan() -> ShotPlan:
    return ShotPlan(
        id="pilot-shot-001",
        script_id="pilot",
        scene_plan_id="pilot-scene-001",
        prompt="akira_girl turns toward camera",
        duration_seconds=3.0,
        character_state=CharacterState("akira", "akira-default", [], []),
    )


def test_akira_character_bible_has_canonical_identity_prompt_and_outfit():
    bible = CharacterBible.akira()

    assert bible.character_id == "akira"
    assert bible.trigger_prompt == "akira_girl"
    assert "amber eyes" in bible.prompt_fragments()
    assert bible.outfit_catalog[0].id == "akira-default"
    assert "extra sword" in bible.style_profile.negative_prompts
    assert bible.to_dict()["identity_constraints"]["trigger_prompt"] == "akira_girl"


def test_render_config_hash_is_stable_and_validates_two_pass_order():
    config = RenderConfig(512, 512, 8, 1903, "euler", 0.12, 0.06)

    first = config.compute_hash(" Akira   turns ", ["akira", "akira"])
    second = config.compute_hash("Akira turns", ["akira"])

    assert first == second
    assert len(first) == 64
    with pytest.raises(ValueError, match="pass2 <= pass1"):
        RenderConfig(512, 512, 8, 1903, "euler", 0.1, 0.2)


def test_animation_shot_starts_unapproved_and_approval_requires_portable_key():
    plan = _plan()

    assert plan.keyframe_approved is False
    approved = plan.approve_keyframe("storyboards/pilot-shot-001/approved.png")
    assert approved.keyframe_approved is True
    assert approved.source_image_storage_key.endswith("approved.png")

    with pytest.raises(ValueError, match="portable"):
        plan.approve_keyframe("C:/private/approved.png")


def test_animation_shot_round_trip_preserves_human_approval_state():
    approved = _plan().approve_keyframe("storyboards/pilot-shot-001/approved.png")

    restored = ShotPlan.from_dict(approved.to_dict())

    assert restored == approved
