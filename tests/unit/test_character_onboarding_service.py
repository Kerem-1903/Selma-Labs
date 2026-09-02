from __future__ import annotations

import asyncio

from core.application.services.character_onboarding_service import (
    CharacterOnboardingService,
)
from core.domain.entities.character_bible import CharacterBible
from core.domain.entities.character_golden_set import default_character_golden_cases
from core.domain.value_objects.character_identity import (
    IdentityConstraints,
    ReferenceView,
)
from core.domain.value_objects.outfit import Outfit
from core.domain.value_objects.style_profile import StyleProfile
from infrastructure.providers.keyframe.fake_keyframe_generation_provider import (
    FakeKeyframeGenerationProvider,
)
from infrastructure.storage.local_fs_storage import LocalFsStorage


def _nova() -> CharacterBible:
    return CharacterBible(
        character_id="nova",
        identity_constraints=IdentityConstraints(
            eye_color="emerald green",
            hair="long silver braided hair",
            facial_geometry="round adult anime face with high cheekbones",
            body_proportions="tall athletic adult",
            silhouette="long navy coat and compact energy bow",
            trigger_prompt="selma_nova_v1",
            immutable_marks=["silver braid", "emerald eyes"],
        ),
        style_profile=StyleProfile(
            base_style="cinematic science-fantasy anime",
            lighting_preferences=["cool rim light"],
            color_palette=["navy", "silver", "emerald"],
            negative_prompts=["short hair", "blue eyes"],
        ),
        outfit_catalog=[
            Outfit(
                id="nova-default",
                character_id="nova",
                description="long navy coat, silver armor panels, black boots",
                reference_image_keys=[],
            )
        ],
    )


def test_plan_is_generic_complete_and_deterministic():
    first = CharacterOnboardingService.plan(_nova())
    second = CharacterOnboardingService.plan(_nova())

    assert first == second
    assert first.training_count == 20
    assert first.holdout_count == 3
    assert "long silver braided hair" in first.anchor_prompt
    assert "emerald green eyes" in first.anchor_prompt
    assert "Akira" not in first.anchor_prompt
    assert {recipe.filename for recipe in first.recipes} >= {
        "front-neutral-01.png",
        "action-running-01.png",
        "profile-right-neutral-01.png",
    }


def test_golden_set_scenarios_use_supplied_character_identity():
    cases = default_character_golden_cases("Nova", "firing one energy bow")
    prompts = " ".join(case.prompt for case in cases)

    assert "Nova" in prompts
    assert "firing one energy bow" in prompts
    assert "Akira" not in prompts


def test_generate_anchor_creates_unconditioned_review_candidate(tmp_path):
    provider = FakeKeyframeGenerationProvider()
    storage = LocalFsStorage(str(tmp_path))
    service = CharacterOnboardingService(provider, storage)

    candidate = asyncio.run(service.generate_anchor(_nova()))

    assert candidate.storage_key.startswith("character-candidates/nova/anchors/anchor-")
    assert candidate.storage_key.endswith(".png")
    assert (tmp_path / candidate.storage_key).is_file()
    assert provider.requests[0].reference_storage_keys == ()
    assert (
        provider.requests[0].seed
        == CharacterOnboardingService.plan(_nova()).anchor_seed
    )


def test_generate_reference_pack_uses_anchor_for_all_23_candidates(tmp_path):
    provider = FakeKeyframeGenerationProvider()
    storage = LocalFsStorage(str(tmp_path))
    service = CharacterOnboardingService(provider, storage)
    anchor_key = "approved/nova-anchor.png"
    asyncio.run(storage.save(anchor_key, b"approved-anchor", "image/png"))

    pack = asyncio.run(
        service.generate_reference_pack(_nova(), anchor_storage_key=anchor_key)
    )

    assert pack.human_approved is False
    assert len(pack.candidates) == 23
    assert pack.source_prefix.startswith("character-candidates/nova/runs/")
    assert pack.source_prefix.endswith("/source")
    assert len(provider.requests) == 23
    assert all(
        request.reference_storage_keys == (anchor_key,) for request in provider.requests
    )
    assert all(
        (tmp_path / candidate.storage_key).is_file() for candidate in pack.candidates
    )


def test_approve_reference_pack_registers_selected_required_views(tmp_path):
    provider = FakeKeyframeGenerationProvider()
    storage = LocalFsStorage(str(tmp_path))
    service = CharacterOnboardingService(provider, storage)
    anchor_key = "approved/nova-anchor.png"
    asyncio.run(storage.save(anchor_key, b"approved-anchor", "image/png"))
    pack = asyncio.run(
        service.generate_reference_pack(_nova(), anchor_storage_key=anchor_key)
    )
    by_name = {
        candidate.filename: candidate.storage_key for candidate in pack.candidates
    }
    character = _nova()
    selections = {
        ReferenceView.FRONT: by_name["front-neutral-01.png"],
        ReferenceView.THREE_QUARTER_LEFT: by_name["three-quarter-neutral-01.png"],
        ReferenceView.PROFILE_LEFT: by_name["profile-left-neutral-01.png"],
        ReferenceView.BACK: by_name["back-neutral-01.png"],
        ReferenceView.FACE_CLOSEUP: by_name["face-closeup-neutral-01.png"],
    }

    approved = asyncio.run(service.approve_reference_pack(character, selections))

    assert set(approved.reference_pack) == set(selections)
    assert all(
        reference.revision == 1 for reference in approved.reference_pack.values()
    )
    assert all(
        asyncio.run(storage.exists(reference.storage_key))
        for reference in approved.reference_pack.values()
    )
