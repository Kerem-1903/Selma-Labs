from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from core.application.services.character_design_service import CharacterDesignService
from core.domain.exceptions import StorageError
from core.domain.value_objects.character_acceptance import (
    CharacterAcceptanceList,
    CharacterHumanCheck,
    acceptance_file_digest,
)
from core.domain.value_objects.character_creation_brief import CharacterCreationBrief
from core.domain.value_objects.character_view_qc import (
    CharacterViewObservation,
    CharacterViewQcReport,
)
from infrastructure.providers.keyframe.fake_keyframe_generation_provider import (
    FakeKeyframeGenerationProvider,
)
from infrastructure.storage.local_fs_storage import LocalFsStorage

_POSE_TEMPLATE_FILES = (
    "pose_front.png",
    "pose_back.png",
    "pose_profile_left.png",
    "pose_profile_right.png",
    "pose_three_quarter_left.png",
    "pose_three_quarter_right.png",
)
_POSE_TEMPLATE_SOURCE = Path(__file__).parents[2] / "assets" / "pose_templates"


def _seed_pose_templates(storage: LocalFsStorage) -> None:
    """Register the canonical pose templates in the test storage."""
    import asyncio

    for name in _POSE_TEMPLATE_FILES:
        key = f"characters/_pose_templates/{name}"
        if not asyncio.run(storage.exists(key)):
            asyncio.run(
                storage.save(key, (_POSE_TEMPLATE_SOURCE / name).read_bytes(), "image/png")
            )



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
    _seed_pose_templates(storage)
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
    assert "1girl, solo" in request.visual_constraints["prompt"]
    assert "clean precise anime line art" in request.visual_constraints["prompt"]
    assert "cape" in request.negative_prompts
    assert "1boy" in request.negative_prompts
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
    _seed_pose_templates(storage)
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
    _seed_pose_templates(storage)
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
    _seed_pose_templates(storage)
    service = CharacterDesignService(provider, storage)
    brief = _brief()
    candidate = asyncio.run(service.generate_candidates(brief, count=1)).candidates[0]
    asyncio.run(storage.save(candidate.storage_key, b"changed", "image/png"))

    with pytest.raises(ValueError, match="changed after generation"):
        asyncio.run(service.approve_candidate(brief, candidate, approved_by="Kerem"))


def test_approval_rejects_candidate_from_another_brief(tmp_path):
    provider = FakeKeyframeGenerationProvider()
    storage = LocalFsStorage(str(tmp_path))
    _seed_pose_templates(storage)
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
    _seed_pose_templates(storage)
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
    _seed_pose_templates(storage)
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


def test_reference_generation_installs_versioned_pose_templates(tmp_path):
    provider = FakeKeyframeGenerationProvider()
    storage = LocalFsStorage(str(tmp_path))
    service = CharacterDesignService(provider, storage)
    brief = _brief()
    candidate = asyncio.run(service.generate_candidates(brief, count=1)).candidates[0]
    approval = asyncio.run(
        service.approve_candidate(brief, candidate, approved_by="Kerem")
    )

    asyncio.run(service.generate_canonical_views(brief, approval))

    for name in _POSE_TEMPLATE_FILES:
        if name == "pose_front.png":
            continue
        installed = tmp_path / "characters" / "_pose_templates" / name
        assert installed.read_bytes() == (_POSE_TEMPLATE_SOURCE / name).read_bytes()


def test_reference_generation_rejects_tampered_pose_template(tmp_path):
    provider = FakeKeyframeGenerationProvider()
    storage = LocalFsStorage(str(tmp_path))
    service = CharacterDesignService(provider, storage)
    brief = _brief()
    candidate = asyncio.run(service.generate_candidates(brief, count=1)).candidates[0]
    approval = asyncio.run(
        service.approve_candidate(brief, candidate, approved_by="Kerem")
    )
    asyncio.run(
        storage.save(
            "characters/_pose_templates/pose_back.png",
            b"tampered",
            "image/png",
        )
    )

    with pytest.raises(StorageError, match="changed unexpectedly"):
        asyncio.run(service.generate_canonical_views(brief, approval))


def test_reference_prompt_uses_gender_presentation_instead_of_hardcoded_1girl(
    tmp_path,
):
    provider = FakeKeyframeGenerationProvider()
    storage = LocalFsStorage(str(tmp_path))
    _seed_pose_templates(storage)
    service = CharacterDesignService(provider, storage)
    masculine = CharacterCreationBrief.from_dict(
        {
            **_brief().to_dict(),
            "name": "Kaito",
            "gender_presentation": "masculine",
        }
    )
    candidate = asyncio.run(service.generate_candidates(masculine, count=1)).candidates[0]
    design_request = provider.requests[-1]
    assert "1boy, solo" in design_request.visual_constraints["prompt"]
    assert "1girl" in design_request.negative_prompts
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
    _seed_pose_templates(storage)
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
    _seed_pose_templates(storage)
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
    _seed_pose_templates(storage)
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
    _seed_pose_templates(storage)
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

    async def evaluate(
        self, *, image_bytes: bytes, view: str, seed: int, signature_marks=()
    ):
        del signature_marks
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
    _seed_pose_templates(storage)
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
    _seed_pose_templates(storage)
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
    _seed_pose_templates(storage)
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


def _acceptance_file(
    tmp_path,
    brief,
    *,
    checks=("same_facial_identity", "back_view_no_face"),
    evidence=(
        "canonical-approval.json",
        "face_anchor.png",
        "fullbody_anchor.png",
        "view-pack.json",
        "contact-sheets/views.png",
    ),
    character_id=None,
    brief_hash=None,
    automatic_checks=("exactly_one_person",),
):
    directory = tmp_path / "acceptance"
    directory.mkdir(parents=True, exist_ok=True)
    source = directory / f"{character_id or brief.character_id}-v1.json"
    acceptance = CharacterAcceptanceList(
        schema_version=1,
        character_id=character_id or brief.character_id,
        character_version=1,
        brief_hash=brief_hash or brief.content_hash,
        blocking_policy="All automatic and human checks must pass.",
        automatic_checks=tuple(automatic_checks),
        human_checks=tuple(
            CharacterHumanCheck(id=check, label=check.replace("_", " "))
            for check in checks
        ),
        required_evidence=tuple(evidence),
    )
    source.write_text(
        json.dumps(acceptance.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return source


def _approve(success_service, brief, acceptance_path, checks=()):
    return asyncio.run(
        success_service.approve_view_pack(
            character_id=brief.character_id,
            character_version=1,
            approved_by="Kerem",
            acceptance_path=acceptance_path,
            confirmed_checks=list(checks),
        )
    )


def _packed_service(tmp_path):
    provider = FakeKeyframeGenerationProvider()
    storage = LocalFsStorage(str(tmp_path))
    _seed_pose_templates(storage)
    service = CharacterDesignService(provider, storage)
    brief = _brief()
    candidate = asyncio.run(service.generate_candidates(brief, count=1)).candidates[0]
    canonical = asyncio.run(
        service.approve_candidate(brief, candidate, approved_by="Kerem")
    )
    pack = asyncio.run(service.generate_canonical_views(brief, canonical))
    return service, storage, brief, pack


def test_style_seeded_candidates_bind_reference_and_weight(tmp_path):
    provider = FakeKeyframeGenerationProvider()
    storage = LocalFsStorage(str(tmp_path))
    _seed_pose_templates(storage)
    service = CharacterDesignService(provider, storage)
    brief = _brief()
    style_file = tmp_path / "akira-style.png"
    style_file.write_bytes((_POSE_TEMPLATE_SOURCE / "pose_front.png").read_bytes())

    pack = asyncio.run(
        service.generate_candidates(
            brief,
            count=1,
            style_reference_path=str(style_file),
            style_weight=0.4,
        )
    )

    request = provider.requests[0]
    assert len(request.reference_storage_keys) == 1
    assert len(request.reference_asset_ids) == 1
    style_key = request.reference_storage_keys[0]
    assert style_key.startswith(
        f"characters/mira/designs/{brief.content_hash}/runs/{pack.run_id}/style/"
    )
    assert (tmp_path / style_key).is_file()
    assert request.reference_asset_ids[0].startswith("style:")
    assert request.visual_constraints["identity_reference_weights"] == [0.4]
    assert request.visual_constraints["style_seed_weight"] == 0.4
    assert request.visual_constraints["identity_mode"] == "style_only"
    manifest = json.loads(
        (tmp_path / f"characters/mira/designs/{brief.content_hash}/runs/"
         f"{pack.run_id}/run-manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["style_reference"]["storage_key"] == style_key
    assert manifest["style_reference"]["weight"] == 0.4
    assert "source_path" not in manifest["style_reference"]


def test_style_seeded_candidates_validate_weight_and_source(tmp_path):
    provider = FakeKeyframeGenerationProvider()
    storage = LocalFsStorage(str(tmp_path))
    _seed_pose_templates(storage)
    service = CharacterDesignService(provider, storage)
    brief = _brief()
    style_file = tmp_path / "akira-style.png"
    style_file.write_bytes((_POSE_TEMPLATE_SOURCE / "pose_front.png").read_bytes())

    with pytest.raises(ValueError, match="style_weight"):
        asyncio.run(
            service.generate_candidates(
                brief, count=1, style_reference_path=str(style_file), style_weight=0.0
            )
        )
    with pytest.raises(FileNotFoundError):
        asyncio.run(
            service.generate_candidates(
                brief,
                count=1,
                style_reference_path=str(tmp_path / "missing.png"),
                style_weight=0.4,
            )
        )
    assert len(provider.requests) == 0


def test_view_pack_approval_requires_signed_acceptance_and_locks_hashes(tmp_path):
    service, storage, brief, pack = _packed_service(tmp_path)
    acceptance_path = _acceptance_file(tmp_path, brief)

    approval = _approve(
        service,
        brief,
        acceptance_path,
        checks=["same_facial_identity", "back_view_no_face"],
    )

    payload = approval.to_dict()
    assert payload["human_approved"] is True
    assert set(approval.view_hashes) == {draft.view for draft in pack.drafts}
    assert payload["acceptance_sha256"] == acceptance_file_digest(acceptance_path)
    assert [check["id"] for check in payload["human_checks"]] == [
        "same_facial_identity",
        "back_view_no_face",
    ]
    assert "view-pack.json" in payload["verified_evidence"]
    assert "view-pack-approval.json" not in payload["verified_evidence"]
    assert payload["automatic_checks_verified"] == ["exactly_one_person"]
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


def test_view_pack_approval_is_idempotent_for_the_same_acceptance(tmp_path):
    service, _storage, brief, _pack = _packed_service(tmp_path)
    acceptance_path = _acceptance_file(tmp_path, brief)
    checks = ["same_facial_identity", "back_view_no_face"]

    first = _approve(service, brief, acceptance_path, checks=checks)
    second = _approve(service, brief, acceptance_path, checks=checks)

    assert second == first


def test_view_pack_approval_rejects_missing_acceptance_list(tmp_path):
    service, _storage, brief, _pack = _packed_service(tmp_path)

    with pytest.raises(ValueError, match="Acceptance list"):
        asyncio.run(
            service.approve_view_pack(
                character_id=brief.character_id,
                character_version=1,
                approved_by="Kerem",
            )
        )


def test_view_pack_approval_rejects_unconfirmed_human_check(tmp_path):
    service, _storage, brief, _pack = _packed_service(tmp_path)
    acceptance_path = _acceptance_file(
        tmp_path,
        brief,
        checks=(
            "same_facial_identity",
            "bag_character_right_never_mirrored",
        ),
    )

    with pytest.raises(ValueError, match="bag_character_right_never_mirrored"):
        _approve(
            service,
            brief,
            acceptance_path,
            checks=["same_facial_identity"],
        )


def test_view_pack_approval_rejects_unknown_automatic_check(tmp_path):
    service, _storage, brief, _pack = _packed_service(tmp_path)
    acceptance_path = _acceptance_file(
        tmp_path,
        brief,
        automatic_checks=("unimplemented_magic_check",),
    )

    with pytest.raises(ValueError, match="unsupported automatic checks"):
        _approve(
            service,
            brief,
            acceptance_path,
            checks=["same_facial_identity", "back_view_no_face"],
        )


def test_view_pack_approval_rejects_missing_provenance_manifest(tmp_path):
    service, _storage, brief, _pack = _packed_service(tmp_path)
    acceptance_path = _acceptance_file(
        tmp_path,
        brief,
        automatic_checks=("provenance_hashes",),
    )

    with pytest.raises(ValueError, match="provenance_hashes"):
        _approve(
            service,
            brief,
            acceptance_path,
            checks=["same_facial_identity", "back_view_no_face"],
        )


def test_view_pack_approval_rejects_missing_evidence(tmp_path):
    service, storage, brief, _pack = _packed_service(tmp_path)
    acceptance_path = _acceptance_file(
        tmp_path,
        brief,
        checks=("same_facial_identity",),
        evidence=("view-pack.json", "manifest.json"),
    )

    with pytest.raises(ValueError, match="is missing"):
        _approve(
            service,
            brief,
            acceptance_path,
            checks=["same_facial_identity"],
        )
    assert not asyncio.run(
        storage.exists("characters/mira/v1/view-pack-approval.json")
    )


def test_view_pack_approval_rejects_acceptance_bound_to_another_brief(tmp_path):
    service, _storage, brief, _pack = _packed_service(tmp_path)
    acceptance_path = _acceptance_file(
        tmp_path,
        brief,
        checks=("same_facial_identity",),
        brief_hash="f" * 64,
    )

    with pytest.raises(ValueError, match="another brief"):
        _approve(
            service,
            brief,
            acceptance_path,
            checks=["same_facial_identity"],
        )


def test_view_pack_approval_rejects_acceptance_for_another_character(tmp_path):
    service, _storage, brief, _pack = _packed_service(tmp_path)
    acceptance_path = _acceptance_file(tmp_path, brief, character_id="other")

    with pytest.raises(ValueError, match="another character version"):
        _approve(
            service,
            brief,
            acceptance_path,
            checks=["same_facial_identity", "back_view_no_face"],
        )


def test_blocked_view_pack_cannot_be_human_approved(tmp_path):
    provider = FakeKeyframeGenerationProvider()
    storage = LocalFsStorage(str(tmp_path))
    _seed_pose_templates(storage)
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
