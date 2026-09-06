from __future__ import annotations

import asyncio
import json

import pytest

from core.application.services.character_design_service import CharacterDesignService
from core.domain.value_objects.character_creation_brief import CharacterCreationBrief
from core.domain.value_objects.character_view_qc import (
    CharacterViewObservation,
    CharacterViewQcReport,
)
from infrastructure.providers.keyframe.fake_keyframe_generation_provider import (
    FakeKeyframeGenerationProvider,
)
from infrastructure.storage.local_fs_storage import LocalFsStorage


def _brief(name: str = "Mira") -> CharacterCreationBrief:
    return CharacterCreationBrief.from_dict(
        {
            "schema_version": 1,
            "name": name,
            "concept": "Underground courier who manipulates sound",
            "gender_presentation": "feminine",
            "hair": "black bob with one red lock",
            "eyes": "amber",
            "outfit": "cropped courier jacket and black boots",
            "props": ["folding baton"],
            "palette": ["charcoal", "burgundy"],
            "avoid": ["cape", "tattoos"],
        }
    )


def test_generates_five_deterministic_unapproved_design_choices(tmp_path):
    provider = FakeKeyframeGenerationProvider()
    storage = LocalFsStorage(str(tmp_path))
    service = CharacterDesignService(provider, storage)

    pack = asyncio.run(service.generate_candidates(_brief()))

    assert len(pack.candidates) == 5
    assert pack.to_dict()["next_gate"] == "HUMAN_CANONICAL_DESIGN_SELECTION"
    assert pack.to_dict()["human_approved"] is False
    assert len(provider.requests) == 5
    assert provider.requests[1].seed == provider.requests[0].seed + 10_000
    assert all(
        candidate.storage_key.startswith(
            f"characters/mira/designs/{_brief().content_hash}/runs/{pack.run_id}/candidates/design-"
        )
        for candidate in pack.candidates
    )
    assert all(
        (tmp_path / candidate.storage_key).is_file() for candidate in pack.candidates
    )
    request = provider.requests[0]
    assert request.visual_constraints["latent_mode"] == "empty"
    assert "Underground courier" in request.visual_constraints["prompt"]
    assert "cape" in request.negative_prompts
    assert (
        tmp_path
        / "characters/mira/designs"
        / _brief().content_hash
        / "runs"
        / pack.run_id
        / "run-manifest.json"
    ).is_file()


def test_design_run_id_is_unique_and_cannot_be_reused(tmp_path):
    provider = FakeKeyframeGenerationProvider()
    storage = LocalFsStorage(str(tmp_path))
    service = CharacterDesignService(provider, storage)

    pack = asyncio.run(
        service.generate_candidates(_brief(), count=1, run_id="kaito-review-001")
    )

    assert pack.run_id == "kaito-review-001"
    with pytest.raises(ValueError, match="already exists"):
        asyncio.run(
            service.generate_candidates(_brief(), count=1, run_id="kaito-review-001")
        )


def test_approval_locks_selected_bytes_and_persists_hash_bound_receipt(tmp_path):
    provider = FakeKeyframeGenerationProvider()
    storage = LocalFsStorage(str(tmp_path))
    service = CharacterDesignService(provider, storage)
    brief = _brief()
    pack = asyncio.run(service.generate_candidates(brief, count=2))

    approval = asyncio.run(
        service.approve_candidate(brief, pack.candidates[1], approved_by="Kerem")
    )

    assert approval.canonical_storage_key == "characters/mira/v1/canonical_source.png"
    assert approval.canonical_content_hash == pack.candidates[1].content_hash
    assert asyncio.run(storage.load(approval.canonical_storage_key)) == asyncio.run(
        storage.load(pack.candidates[1].storage_key)
    )
    receipt = json.loads(
        asyncio.run(storage.load("characters/mira/v1/canonical-approval.json"))
    )
    assert receipt["brief_hash"] == brief.content_hash
    assert receipt["approved_by"] == "Kerem"
    assert receipt["anchors_locked"] is True
    assert receipt["face_anchor"]["content_hash"] == (
        approval.face_anchor.content_hash
    )
    assert receipt["fullbody_anchor"]["content_hash"] == (
        approval.fullbody_anchor.content_hash
    )
    assert (tmp_path / receipt["face_anchor"]["storage_key"]).is_file()
    assert (tmp_path / receipt["fullbody_anchor"]["storage_key"]).is_file()


def test_approval_rejects_tampered_candidate(tmp_path):
    provider = FakeKeyframeGenerationProvider()
    storage = LocalFsStorage(str(tmp_path))
    service = CharacterDesignService(provider, storage)
    brief = _brief()
    candidate = asyncio.run(service.generate_candidates(brief, count=1)).candidates[0]
    asyncio.run(storage.save(candidate.storage_key, b"changed", "image/png"))

    with pytest.raises(ValueError, match="changed after generation"):
        asyncio.run(service.approve_candidate(brief, candidate, approved_by="Kerem"))


def test_approval_rejects_candidate_from_another_brief(tmp_path):
    provider = FakeKeyframeGenerationProvider()
    storage = LocalFsStorage(str(tmp_path))
    service = CharacterDesignService(provider, storage)
    candidate = asyncio.run(
        service.generate_candidates(_brief("Mira"), count=1)
    ).candidates[0]

    with pytest.raises(ValueError, match="does not belong"):
        asyncio.run(
            service.approve_candidate(_brief("Nova"), candidate, approved_by="Kerem")
        )


def test_existing_canonical_version_cannot_be_silently_replaced(tmp_path):
    provider = FakeKeyframeGenerationProvider()
    storage = LocalFsStorage(str(tmp_path))
    service = CharacterDesignService(provider, storage)
    brief = _brief()
    candidate = asyncio.run(service.generate_candidates(brief, count=1)).candidates[0]
    asyncio.run(
        storage.save("characters/mira/v1/canonical_source.png", b"other", "image/png")
    )

    with pytest.raises(ValueError, match="already locked"):
        asyncio.run(service.approve_candidate(brief, candidate, approved_by="Kerem"))


def test_approved_design_generates_only_seven_neutral_reference_drafts(tmp_path):
    provider = FakeKeyframeGenerationProvider()
    storage = LocalFsStorage(str(tmp_path))
    service = CharacterDesignService(provider, storage)
    brief = _brief()
    candidate = asyncio.run(service.generate_candidates(brief, count=1)).candidates[0]
    approval = asyncio.run(
        service.approve_candidate(brief, candidate, approved_by="Kerem")
    )
    provider.requests.clear()

    pack = asyncio.run(service.generate_reference_drafts(brief, approval))

    assert [draft.view for draft in pack.drafts] == [
        "FACE_CLOSEUP",
        "FRONT",
        "PROFILE_LEFT",
        "PROFILE_RIGHT",
        "THREE_QUARTER_LEFT",
        "THREE_QUARTER_RIGHT",
        "BACK",
    ]
    assert pack.to_dict()["human_approved"] is False
    assert pack.to_dict()["next_gate"] == "PENDING_HUMAN_REVIEW"
    assert pack.contact_sheet_storage_key.endswith("contact-sheets/views.png")
    assert asyncio.run(storage.exists(pack.contact_sheet_storage_key))
    assert len(provider.requests) == 6
    assert all(
        request.action_constraints["primary_action"] == "neutral reference pose"
        for request in provider.requests
    )
    assert approval.face_anchor is not None
    assert approval.fullbody_anchor is not None
    front, profile_left, profile_right, quarter_left, quarter_right, back = (
        provider.requests
    )
    assert front.reference_storage_keys == (
        approval.face_anchor.storage_key,
        approval.fullbody_anchor.storage_key,
    )
    assert len(set(front.reference_asset_ids)) == 2
    assert tuple(
        item["references"][0]["asset_id"] for item in front.character_conditioning
    ) == front.reference_asset_ids
    assert front.visual_constraints["identity_reference_weights"] == [0.8, 0.5]
    generated_front = pack.drafts[1]
    assert profile_left.reference_storage_keys == (
        generated_front.storage_key,
        approval.face_anchor.storage_key,
    )
    assert profile_right.reference_storage_keys == profile_left.reference_storage_keys
    assert quarter_left.reference_storage_keys == (generated_front.storage_key,)
    assert quarter_right.reference_storage_keys == (generated_front.storage_key,)
    generated_profile_left = pack.drafts[2]
    assert back.reference_storage_keys == (
        generated_front.storage_key,
        generated_profile_left.storage_key,
    )
    assert back.visual_constraints["identity_reference_weights"] == [0.55, 0.4]
    assert not any(
        "ACTION_" in request.shot_contract_id for request in provider.requests
    )
    assert all(
        "1girl, solo, one person only" in request.visual_constraints["prompt"]
        for request in provider.requests
    )
    assert all("lineup" in request.negative_prompts for request in provider.requests)
    assert "front view" in profile_left.negative_prompts
    assert "front view" in profile_right.negative_prompts
    assert "right three-quarter view" in quarter_left.negative_prompts
    assert "left three-quarter view" in quarter_right.negative_prompts
    assert "face" in back.negative_prompts
    assert "eyes" in back.negative_prompts
    assert "looking back" in back.negative_prompts


def test_reference_prompt_uses_gender_presentation_instead_of_hardcoded_1girl(
    tmp_path,
):
    provider = FakeKeyframeGenerationProvider()
    storage = LocalFsStorage(str(tmp_path))
    service = CharacterDesignService(provider, storage)
    masculine = CharacterCreationBrief.from_dict(
        {
            **_brief().to_dict(),
            "name": "Kaito",
            "gender_presentation": "masculine",
        }
    )
    candidate = asyncio.run(service.generate_candidates(masculine, count=1)).candidates[0]
    approval = asyncio.run(
        service.approve_candidate(masculine, candidate, approved_by="Kerem")
    )
    provider.requests.clear()

    asyncio.run(service.generate_reference_drafts(masculine, approval))

    prompts = [request.visual_constraints["prompt"] for request in provider.requests]
    assert all("1boy, solo" in prompt for prompt in prompts)
    assert all("1girl" not in prompt for prompt in prompts)


def test_dual_anchors_are_derived_from_the_same_canonical_source(tmp_path):
    provider = FakeKeyframeGenerationProvider()
    storage = LocalFsStorage(str(tmp_path))
    service = CharacterDesignService(provider, storage)
    brief = _brief()
    candidate = asyncio.run(service.generate_candidates(brief, count=1)).candidates[0]
    provider.requests.clear()

    approval = asyncio.run(
        service.approve_candidate(brief, candidate, approved_by="Kerem")
    )

    assert approval.anchors_locked
    assert approval.face_anchor is not None
    assert approval.fullbody_anchor is not None
    assert len(provider.requests) == 2
    face_request, fullbody_request = provider.requests
    assert face_request.reference_storage_keys == (approval.canonical_storage_key,)
    assert fullbody_request.reference_storage_keys == (approval.canonical_storage_key,)
    assert face_request.width == 1024
    assert face_request.height == 1024
    assert fullbody_request.width == 768
    assert fullbody_request.height == 1152
    assert approval.face_anchor.workflow_version == "dual-anchor-v1"
    assert approval.fullbody_anchor.workflow_version == "dual-anchor-v1"


def test_repeated_design_approval_reuses_locked_anchors_without_regeneration(tmp_path):
    provider = FakeKeyframeGenerationProvider()
    storage = LocalFsStorage(str(tmp_path))
    service = CharacterDesignService(provider, storage)
    brief = _brief()
    candidate = asyncio.run(service.generate_candidates(brief, count=1)).candidates[0]
    first = asyncio.run(
        service.approve_candidate(brief, candidate, approved_by="Kerem")
    )
    provider.requests.clear()

    second = asyncio.run(
        service.approve_candidate(brief, candidate, approved_by="Another approver")
    )

    assert second == first
    assert provider.requests == []


def test_reference_generation_rejects_tampered_face_anchor(tmp_path):
    provider = FakeKeyframeGenerationProvider()
    storage = LocalFsStorage(str(tmp_path))
    service = CharacterDesignService(provider, storage)
    brief = _brief()
    candidate = asyncio.run(service.generate_candidates(brief, count=1)).candidates[0]
    approval = asyncio.run(
        service.approve_candidate(brief, candidate, approved_by="Kerem")
    )
    assert approval.face_anchor is not None
    asyncio.run(storage.save(approval.face_anchor.storage_key, b"changed", "image/png"))

    with pytest.raises(ValueError, match="FACE anchor changed"):
        asyncio.run(service.generate_canonical_views(brief, approval))


def test_reference_drafts_reject_tampered_canonical_design(tmp_path):
    provider = FakeKeyframeGenerationProvider()
    storage = LocalFsStorage(str(tmp_path))
    service = CharacterDesignService(provider, storage)
    brief = _brief()
    candidate = asyncio.run(service.generate_candidates(brief, count=1)).candidates[0]
    approval = asyncio.run(
        service.approve_candidate(brief, candidate, approved_by="Kerem")
    )
    asyncio.run(storage.save(approval.canonical_storage_key, b"changed", "image/png"))

    with pytest.raises(ValueError, match="changed after human approval"):
        asyncio.run(service.generate_reference_drafts(brief, approval))


class ScriptedViewGate:
    def __init__(
        self,
        failures: dict[str, int] | None = None,
        *,
        design_failures: int = 0,
    ) -> None:
        self.failures = dict(failures or {})
        self.design_failures = design_failures
        self.calls: list[tuple[str, int]] = []
        self.design_calls: list[int] = []

    async def evaluate(self, *, image_bytes: bytes, view: str, seed: int):
        del image_bytes
        self.calls.append((view, seed))
        should_fail = self.failures.get(view, 0) > 0
        if should_fail:
            self.failures[view] -= 1
        orientation = {
            "FACE_CLOSEUP": "front",
            "FRONT": "front",
            "PROFILE_LEFT": "profile_left",
            "PROFILE_RIGHT": "profile_right",
            "THREE_QUARTER_LEFT": "three_quarter_left",
            "THREE_QUARTER_RIGHT": "three_quarter_right",
            "BACK": "back",
        }[view]
        return CharacterViewQcReport(
            view=view,
            seed=seed,
            passed=not should_fail,
            reasons=("person_count_2",) if should_fail else (),
            observation=CharacterViewObservation(
                person_count=2 if should_fail else 1,
                face_count=0 if view == "BACK" else 1,
                head_inside_frame=True,
                feet_inside_frame=True,
                orientation=orientation,
                confidence=1.0,
                provider="test",
            ),
            framing_metrics={},
        )

    async def evaluate_design_candidate(
        self, *, image_bytes: bytes, seed: int, signature_marks=()
    ):
        del signature_marks
        self.design_calls.append(seed)
        report = await _OfflineDesignGate().evaluate_design_candidate(
            image_bytes=image_bytes, seed=seed
        )
        if self.design_failures <= 0:
            return report
        self.design_failures -= 1
        return CharacterViewQcReport(
            view=report.view,
            seed=seed,
            passed=False,
            reasons=("person_count_3",),
            observation=CharacterViewObservation(
                person_count=3,
                face_count=3,
                head_inside_frame=True,
                feet_inside_frame=True,
                orientation="front",
                confidence=1.0,
                provider="test",
            ),
            framing_metrics={},
        )


class _OfflineDesignGate:
    async def evaluate_design_candidate(
        self, *, image_bytes: bytes, seed: int, signature_marks=()
    ):
        del signature_marks
        del image_bytes
        return CharacterViewQcReport(
            view="DESIGN_CANDIDATE",
            seed=seed,
            passed=True,
            reasons=(),
            observation=CharacterViewObservation(
                person_count=1,
                face_count=1,
                head_inside_frame=True,
                feet_inside_frame=True,
                orientation="front",
                confidence=1.0,
                provider="test",
            ),
            framing_metrics={},
        )


def test_design_candidate_qc_quarantines_collage_and_retries(tmp_path):
    provider = FakeKeyframeGenerationProvider()
    storage = LocalFsStorage(str(tmp_path))
    gate = ScriptedViewGate(design_failures=1)
    service = CharacterDesignService(provider, storage, quality_gate=gate)

    pack = asyncio.run(service.generate_candidates(_brief(), count=1))

    assert len(pack.candidates) == 1
    assert len(gate.design_calls) == 2
    assert gate.design_calls[0] != gate.design_calls[1]
    quarantine = list((tmp_path / "characters/mira/designs").rglob("quarantine/*.png"))
    assert len(quarantine) == 1
    assert "person_count_3" in quarantine[0].name


def test_view_qc_quarantines_failure_and_retries_with_a_new_seed(tmp_path):
    provider = FakeKeyframeGenerationProvider()
    storage = LocalFsStorage(str(tmp_path))
    gate = ScriptedViewGate({"PROFILE_LEFT": 1})
    service = CharacterDesignService(provider, storage, quality_gate=gate)
    brief = _brief()
    candidate = asyncio.run(service.generate_candidates(brief, count=1)).candidates[0]
    approval = asyncio.run(
        service.approve_candidate(brief, candidate, approved_by="Kerem")
    )
    provider.requests.clear()

    pack = asyncio.run(service.generate_canonical_views(brief, approval))

    assert pack.status == "PENDING_HUMAN_REVIEW"
    assert len(pack.quarantined) == 1
    rejected = pack.quarantined[0]
    assert rejected.view == "PROFILE_LEFT"
    assert "person_count_2" in rejected.image_storage_key
    assert asyncio.run(storage.exists(rejected.image_storage_key))
    assert asyncio.run(storage.exists(rejected.report_storage_key))
    profile_seeds = [seed for view, seed in gate.calls if view == "PROFILE_LEFT"]
    assert len(profile_seeds) == 2
    assert profile_seeds[0] != profile_seeds[1]


def test_view_pack_blocks_after_three_failed_attempts(tmp_path):
    provider = FakeKeyframeGenerationProvider()
    storage = LocalFsStorage(str(tmp_path))
    gate = ScriptedViewGate({"FRONT": 3})
    service = CharacterDesignService(provider, storage, quality_gate=gate)
    brief = _brief()
    candidate = asyncio.run(service.generate_candidates(brief, count=1)).candidates[0]
    approval = asyncio.run(
        service.approve_candidate(brief, candidate, approved_by="Kerem")
    )

    pack = asyncio.run(service.generate_canonical_views(brief, approval))

    assert pack.status == "BLOCKED"
    assert [item.view for item in pack.drafts] == ["FACE_CLOSEUP"]
    assert len(pack.quarantined) == 3
    assert pack.contact_sheet_storage_key == ""


def test_view_pack_approval_locks_all_seven_hashes_atomically(tmp_path):
    provider = FakeKeyframeGenerationProvider()
    storage = LocalFsStorage(str(tmp_path))
    service = CharacterDesignService(provider, storage)
    brief = _brief()
    candidate = asyncio.run(service.generate_candidates(brief, count=1)).candidates[0]
    canonical = asyncio.run(
        service.approve_candidate(brief, candidate, approved_by="Kerem")
    )
    pack = asyncio.run(service.generate_canonical_views(brief, canonical))

    approval = asyncio.run(
        service.approve_view_pack(
            character_id=brief.character_id,
            character_version=1,
            approved_by="Kerem",
        )
    )

    assert approval.to_dict()["human_approved"] is True
    assert set(approval.view_hashes) == {draft.view for draft in pack.drafts}
    assert asyncio.run(
        storage.exists("characters/mira/v1/view-pack-approval.json")
    )
    assert (
        asyncio.run(
            service.require_view_pack_approval(
                character_id=brief.character_id, character_version=1
            )
        )
        == approval
    )
    assert asyncio.run(
        service.load_approved_view_pack(
            character_id=brief.character_id,
            character_version=1,
        )
    ) == pack


def test_blocked_view_pack_cannot_be_human_approved(tmp_path):
    provider = FakeKeyframeGenerationProvider()
    storage = LocalFsStorage(str(tmp_path))
    service = CharacterDesignService(
        provider, storage, quality_gate=ScriptedViewGate({"FRONT": 3})
    )
    brief = _brief()
    candidate = asyncio.run(service.generate_candidates(brief, count=1)).candidates[0]
    canonical = asyncio.run(
        service.approve_candidate(brief, candidate, approved_by="Kerem")
    )
    asyncio.run(service.generate_canonical_views(brief, canonical))

    with pytest.raises(ValueError, match="QC-passed"):
        asyncio.run(
            service.approve_view_pack(
                character_id=brief.character_id,
                character_version=1,
                approved_by="Kerem",
            )
        )
