from __future__ import annotations

from core.application.services.character_identity_prompt_service import (
    CharacterIdentityPromptService,
)
from core.domain.value_objects.character_creation_brief import CharacterCreationBrief


def _brief() -> CharacterCreationBrief:
    return CharacterCreationBrief.from_dict(
        {
            "schema_version": 1,
            "name": "Kaito",
            "concept": "Disciplined courier",
            "gender_presentation": "masculine",
            "body_type": "athletic adult",
            "face": "angular anime face",
            "eyes": "steel blue eyes",
            "hair": "short black hair with one cobalt streak",
            "outfit": "charcoal courier jacket with blue trim",
            "props": ["messenger bag on character-right hip"],
            "palette": ["charcoal", "black", "cobalt blue"],
            "style_preset": "selma-anime-v1",
            "avoid": ["chibi proportions"],
        }
    )


def test_factory_carries_one_identity_hash_across_request_types():
    factory = CharacterIdentityPromptService()
    brief = _brief()

    design = factory.build_design_request(brief, seed=11, variant=1)
    anchor = factory.build_anchor_request(
        brief,
        canonical_source_key="characters/kaito/v1/canonical_source.png",
        canonical_source_hash="a" * 64,
        role="FULL_BODY",
        seed=12,
        width=768,
        height=1152,
    )
    reference = factory.build_reference_request(
        brief,
        view="PROFILE_RIGHT",
        direction="strict right profile",
        seed=13,
        references=(
            ("FRONT", "characters/kaito/v1/views/front.png", "b" * 64, 0.8),
        ),
    )
    pose = factory.build_pose_request(
        brief,
        style_key="series-style/selma/seed.png",
        style_hash="c" * 64,
        pose_id="FRONT_NEUTRAL",
        expected_view="FRONT",
        seed=14,
        face_anchor_key="characters/kaito/v1/face_anchor.png",
        face_anchor_hash="d" * 64,
        fullbody_anchor_key="characters/kaito/v1/fullbody_anchor.png",
        fullbody_anchor_hash="e" * 64,
        pose_template_key="characters/_pose_templates/pose_front.png",
    )

    identity_hashes = {
        request.visual_constraints["identity_contract_hash"]
        for request in (design, anchor, reference, pose)
    }
    assert len(identity_hashes) == 1
    assert "cobalt" in design.visual_constraints["prompt"]
    assert "chibi proportions" in pose.negative_prompts
    assert pose.visual_constraints["consistency_contract"]["costume"] == brief.outfit


def test_factory_keeps_view_direction_separate_from_identity():
    factory = CharacterIdentityPromptService()
    brief = _brief()

    left = factory.build_reference_request(
        brief,
        view="PROFILE_LEFT",
        direction="strict left profile",
        seed=1,
        references=(("FRONT", "front.png", "a" * 64, 0.8),),
    )
    right = factory.build_reference_request(
        brief,
        view="PROFILE_RIGHT",
        direction="strict right profile",
        seed=1,
        references=(("FRONT", "front.png", "a" * 64, 0.8),),
    )

    assert left.visual_constraints["identity_contract_hash"] == right.visual_constraints[
        "identity_contract_hash"
    ]
    assert "nose points to image left" in left.visual_constraints["prompt"]
    assert "nose points to image right" in right.visual_constraints["prompt"]
    assert left.visual_constraints["consistency_contract"] == right.visual_constraints[
        "consistency_contract"
    ]
    assert len(left.visual_constraints["prompt"]) < 400
    assert "additional_notes" not in left.visual_constraints["prompt"]
    assert left.visual_constraints["prompt_mode"] == "compact-turnaround"


def test_flux2_edit_prompt_is_source_led_and_task_focused():
    factory = CharacterIdentityPromptService()
    prompt = factory.build_flux2_edit_prompt(_brief(), view="PROFILE_LEFT")

    assert prompt.startswith("Edit Picture 1.")
    assert "strict left side profile" in prompt
    assert "turnaround, not a redesign" in prompt
    assert "accessory count, scale and placement" in prompt
    assert "Infer only surfaces hidden in Picture 1" in prompt
    assert len(prompt) < 1200
    assert "Benchmark-only text prompt" not in prompt
    assert "Do not add, remove, enlarge, simplify, recolor, restyle, or replace" in prompt


def test_flux2_edit_prompt_locks_props_marks_and_hidden_surfaces():
    prompt = CharacterIdentityPromptService().build_flux2_edit_prompt(
        _brief(), view="BACK"
    )

    assert (
        "Every depicted prop keeps the same count, the same side of the body, "
        "the same scale and the same colour." in prompt
    )
    assert "never mirrors onto the visible side" in prompt
    assert "no new strap, pocket, seam, panel, accessory or colour field" in prompt
    assert "continues over the same shoulder and hip" in prompt


def test_flux2_edit_prompt_hidden_surface_clause_is_view_scoped():
    factory = CharacterIdentityPromptService()

    front = factory.build_flux2_edit_prompt(_brief(), view="FRONT")
    back = factory.build_flux2_edit_prompt(_brief(), view="BACK")

    assert "continues over the same shoulder and hip" not in front
    assert "continues over the same shoulder and hip" in back


def test_flux2_edit_prompt_keeps_side_bound_marks_honest_per_view():
    brief = CharacterCreationBrief.from_dict(
        {
            "schema_version": 1,
            "name": "Kaito",
            "concept": "Disciplined courier",
            "gender_presentation": "masculine",
            "hair": "short black hair with one cobalt streak",
            "signature_marks": [
                {
                    "label": "single cobalt front hair streak",
                    "count": 1,
                    "character_side": "left",
                    "colour": "#0047AB",
                }
            ],
            "outfit": "charcoal courier jacket with blue trim",
            "palette": ["charcoal", "cobalt blue"],
            "style_preset": "selma-anime-v1",
        }
    )
    factory = CharacterIdentityPromptService()

    same_side = factory.build_flux2_edit_prompt(brief, view="PROFILE_LEFT")
    far_side = factory.build_flux2_edit_prompt(brief, view="PROFILE_RIGHT")
    back = factory.build_flux2_edit_prompt(brief, view="BACK")

    assert "faces the camera in this view and must stay visible" in same_side
    assert "do not mirror it onto the visible side" in far_side
    assert "stays on the image left in this view" in back
    assert "single cobalt front hair streak" not in same_side
    assert "#0047AB" not in same_side
    assert "far side" not in same_side


def test_flux2_edit_prompt_uses_the_image_without_dumping_brief_identity():
    brief = CharacterCreationBrief.from_dict(
        {
            "schema_version": 1,
            "name": "Mira",
            "concept": "Botanist",
            "age_band": "elderly adult",
            "gender_presentation": "feminine woman",
            "body_type": "short and sturdy",
            "face": "round face",
            "eyes": "brown eyes",
            "hair": "long silver braid",
            "outfit": "green field coat and brown boots",
            "props": ["pressed-flower satchel"],
            "palette": ["green", "brown"],
            "style_preset": "selma-anime-v1",
            "avoid": [],
        }
    )

    prompt = CharacterIdentityPromptService().build_flux2_edit_prompt(
        brief, view="PROFILE_LEFT"
    )

    assert "exact same character" in prompt
    assert "color boundary" in prompt
    assert "recolor" in prompt
    assert "feminine woman" not in prompt
    assert "long silver braid" not in prompt
    assert "pressed-flower satchel" not in prompt
    assert "adult male" not in prompt
    assert "charcoal courier jacket" not in prompt


def test_image_edit_negatives_are_view_specific_without_full_brief_dump():
    factory = CharacterIdentityPromptService()
    negatives = factory.image_edit_negative_prompts("PROFILE_RIGHT")

    assert "front view" in negatives
    assert "left profile" in negatives
    assert "character redesign" in negatives
    assert "Disciplined courier" not in negatives
    assert "" not in negatives


def test_legacy_qwen_edit_alias_matches_flux2_prompt():
    factory = CharacterIdentityPromptService()
    assert factory.build_qwen_edit_prompt(
        _brief(), view="BACK"
    ) == factory.build_flux2_edit_prompt(_brief(), view="BACK")


def test_flux2_three_quarter_prompt_disambiguates_profile():
    prompt = CharacterIdentityPromptService().build_flux2_edit_prompt(
        _brief(), view="THREE_QUARTER_RIGHT"
    )

    assert "about 45 degrees" in prompt
    assert "both eyes" in prompt
    assert "do not make a side profile" in prompt
