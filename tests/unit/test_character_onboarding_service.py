from __future__ import annotations

import asyncio

import pytest

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
from core.domain.value_objects.preproduction_image_quality import (
    PreproductionImageQuality,
)
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


def _all_pilot_checks() -> dict[str, bool]:
    return {
        "face_match": True,
        "hair_match": True,
        "immutable_marks_match": True,
        "outfit_match": True,
        "framing_match": True,
        "anatomy_pass": True,
    }


def _generate_and_approve_pilot(service, character, anchor_key):
    pilot_pack = asyncio.run(
        service.generate_reference_pack(
            character,
            anchor_storage_key=anchor_key,
            recipe_limit=1,
            automatic_review=False,
        )
    )
    return asyncio.run(
        service.approve_pilot(
            character,
            anchor_storage_key=anchor_key,
            pilot_storage_key=pilot_pack.candidates[0].storage_key,
            approved_by="Kerem",
            checks=_all_pilot_checks(),
        )
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


def test_generate_anchor_supports_deterministic_candidate_variations(tmp_path):
    provider = FakeKeyframeGenerationProvider()
    service = CharacterOnboardingService(provider, LocalFsStorage(str(tmp_path)))

    asyncio.run(service.generate_anchor(_nova(), seed_offset=20_000))

    plan = CharacterOnboardingService.plan(_nova())
    assert provider.requests[0].seed == plan.anchor_seed + 20_000
    assert "immutable identity marks exactly once" in plan.anchor_prompt
    assert "duplicated signature marks" in plan.negative_prompts


def test_generate_anchor_can_bootstrap_from_source_reference(tmp_path):
    provider = FakeKeyframeGenerationProvider()
    storage = LocalFsStorage(str(tmp_path))
    source_key = "bootstrap/nova.png"
    asyncio.run(storage.save(source_key, b"source", "image/png"))
    service = CharacterOnboardingService(provider, storage)

    asyncio.run(
        service.generate_anchor(_nova(), source_reference_storage_key=source_key)
    )

    request = provider.requests[0]
    assert request.reference_storage_keys == (source_key,)
    assert request.visual_constraints["identity_strength"] == 0.95
    assert request.visual_constraints["identity_end_at"] == 0.90


def test_generate_reference_pack_uses_anchor_for_all_23_candidates(tmp_path):
    provider = FakeKeyframeGenerationProvider()
    storage = LocalFsStorage(str(tmp_path))
    service = CharacterOnboardingService(provider, storage)
    anchor_key = "approved/nova-anchor.png"
    asyncio.run(storage.save(anchor_key, provider._PNG, "image/png"))
    approval = _generate_and_approve_pilot(service, _nova(), anchor_key)

    pack = asyncio.run(
        service.generate_reference_pack(
            _nova(), anchor_storage_key=anchor_key, pilot_approval=approval
        )
    )

    assert pack.human_approved is False
    assert len(pack.candidates) == 23
    assert pack.source_prefix.startswith("character-candidates/nova/runs/")
    assert pack.source_prefix.endswith("/source")
    assert len(provider.requests) == 23
    assert provider.requests[0].reference_storage_keys[0].endswith(
        "/conditioning/face-closeup-anchor.png"
    )
    assert provider.requests[1].reference_storage_keys[0].endswith(
        "/conditioning/face-closeup-anchor.png"
    )
    assert all(
        request.reference_storage_keys == (anchor_key,)
        for request in provider.requests[2:]
    )
    assert all(
        (tmp_path / candidate.storage_key).is_file() for candidate in pack.candidates
    )
    first_request = provider.requests[0]
    assert "tight face close-up" in first_request.camera_constraints["angle"]
    assert first_request.camera_constraints["lens"] == "85mm portrait lens"
    assert first_request.visual_constraints["identity_strength"] == 1.0
    assert first_request.visual_constraints["identity_end_at"] == 0.9
    assert "full body" in first_request.negative_prompts


class _RetryOnceEvaluator:
    def __init__(self) -> None:
        self.calls = 0

    async def evaluate(self, **_kwargs):
        self.calls += 1
        passed = self.calls != 1
        issues = () if passed else ("identity_drift",)
        return PreproductionImageQuality(
            score=0.9 if passed else 0.4,
            threshold=0.72,
            passed=passed,
            identity_or_geometry_score=0.9 if passed else 0.3,
            composition_score=0.9,
            subject_policy_score=1.0,
            confidence=0.9,
            issues=issues,
            provider="fake:vision",
        )


def test_generate_reference_pack_retries_and_quarantines_failed_candidate(tmp_path):
    provider = FakeKeyframeGenerationProvider()
    storage = LocalFsStorage(str(tmp_path))
    service = CharacterOnboardingService(
        provider, storage, _RetryOnceEvaluator(), max_attempts=3
    )
    anchor_key = "approved/nova-anchor.png"
    asyncio.run(storage.save(anchor_key, provider._PNG, "image/png"))

    pack = asyncio.run(
        service.generate_reference_pack(
            _nova(), anchor_storage_key=anchor_key, recipe_limit=1
        )
    )

    assert len(pack.candidates) == 1
    assert len(pack.quarantined) == 1
    assert len(provider.requests) == 2
    assert "/quarantine/attempt-1-" in pack.quarantined[0].storage_key
    assert pack.candidates[0].attempt == 2
    assert provider.requests[1].seed == provider.requests[0].seed + 10_000


def test_bulk_reference_generation_requires_approved_pilot(tmp_path):
    provider = FakeKeyframeGenerationProvider()
    storage = LocalFsStorage(str(tmp_path))
    service = CharacterOnboardingService(provider, storage)
    anchor_key = "approved/nova-anchor.png"
    asyncio.run(storage.save(anchor_key, provider._PNG, "image/png"))

    with pytest.raises(ValueError, match="approved face-closeup pilot"):
        asyncio.run(
            service.generate_reference_pack(_nova(), anchor_storage_key=anchor_key)
        )

    assert provider.requests == []


def test_bulk_gate_detects_pilot_tampering(tmp_path):
    provider = FakeKeyframeGenerationProvider()
    storage = LocalFsStorage(str(tmp_path))
    service = CharacterOnboardingService(provider, storage)
    anchor_key = "approved/nova-anchor.png"
    asyncio.run(storage.save(anchor_key, provider._PNG, "image/png"))
    approval = _generate_and_approve_pilot(service, _nova(), anchor_key)
    asyncio.run(storage.save(approval.pilot_storage_key, b"changed", "image/png"))

    with pytest.raises(ValueError, match="changed after human review"):
        asyncio.run(
            service.generate_reference_pack(
                _nova(), anchor_storage_key=anchor_key, pilot_approval=approval
            )
        )


def test_pilot_approval_requires_every_visual_check(tmp_path):
    provider = FakeKeyframeGenerationProvider()
    storage = LocalFsStorage(str(tmp_path))
    service = CharacterOnboardingService(provider, storage)
    anchor_key = "approved/nova-anchor.png"
    asyncio.run(storage.save(anchor_key, provider._PNG, "image/png"))
    pilot = asyncio.run(
        service.generate_reference_pack(
            _nova(), anchor_storage_key=anchor_key, recipe_limit=1
        )
    ).candidates[0]

    with pytest.raises(ValueError, match="framing_match"):
        asyncio.run(
            service.approve_pilot(
                _nova(),
                anchor_storage_key=anchor_key,
                pilot_storage_key=pilot.storage_key,
                approved_by="Kerem",
                checks={**_all_pilot_checks(), "framing_match": False},
            )
        )


def test_reference_pack_can_run_one_pending_pilot_without_automatic_review(tmp_path):
    provider = FakeKeyframeGenerationProvider()
    storage = LocalFsStorage(str(tmp_path))
    evaluator = _RetryOnceEvaluator()
    service = CharacterOnboardingService(provider, storage, evaluator)
    anchor_key = "approved/nova-anchor.png"
    asyncio.run(storage.save(anchor_key, provider._PNG, "image/png"))

    pack = asyncio.run(
        service.generate_reference_pack(
            _nova(),
            anchor_storage_key=anchor_key,
            recipe_limit=1,
            automatic_review=False,
        )
    )

    assert len(pack.candidates) == 1
    assert pack.candidates[0].quality is None
    assert evaluator.calls == 0


def test_approve_reference_pack_registers_selected_required_views(tmp_path):
    provider = FakeKeyframeGenerationProvider()
    storage = LocalFsStorage(str(tmp_path))
    service = CharacterOnboardingService(provider, storage)
    anchor_key = "approved/nova-anchor.png"
    asyncio.run(storage.save(anchor_key, provider._PNG, "image/png"))
    approval = _generate_and_approve_pilot(service, _nova(), anchor_key)
    pack = asyncio.run(
        service.generate_reference_pack(
            _nova(), anchor_storage_key=anchor_key, pilot_approval=approval
        )
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
