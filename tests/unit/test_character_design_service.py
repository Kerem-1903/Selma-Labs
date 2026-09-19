from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import replace
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from core.application.services.character_design_service import CharacterDesignService
from core.application.services.character_turnaround_drift_service import (
    CharacterTurnaroundDriftService,
    DriftThresholds,
)
from core.application.services.character_view_pack_generation_service import (
    CharacterViewPackGenerationService,
)
from core.application.services.production_manifest_service import (
    ProductionManifestService,
)
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
    assert len(provider.requests) == 5
    assert all(
        request.action_constraints["primary_action"] == "neutral reference pose"
        for request in provider.requests
    )
    assert approval.face_anchor is not None
    assert approval.fullbody_anchor is not None
    profile_left, profile_right, quarter_left, quarter_right, back = provider.requests
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
    assert provider.requests == []
    assert approval.face_anchor.width == 1024
    assert approval.face_anchor.height == 1024
    assert approval.fullbody_anchor.width == 768
    assert approval.fullbody_anchor.height == 1152
    assert approval.anchor_provider == "deterministic:canonical-transform"
    assert approval.face_anchor.workflow_version == "dual-anchor-v2-deterministic"
    assert approval.fullbody_anchor.workflow_version == "dual-anchor-v2-deterministic"
    assert approval.face_anchor.model_hashes == {}
    assert approval.fullbody_anchor.model_hashes == {}


def test_canonical_face_and_front_views_reuse_deterministic_anchors(tmp_path):
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

    by_view = {draft.view: draft for draft in pack.drafts}
    assert by_view["FACE_CLOSEUP"].content_hash == approval.face_anchor.content_hash
    assert by_view["FRONT"].content_hash == approval.fullbody_anchor.content_hash
    assert all(
        request.shot_contract_id
        != f"character-reference-{brief.character_id}-FRONT-{approval.fullbody_anchor.seed}"
        for request in provider.requests
    )


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
    gate = ScriptedViewGate({"PROFILE_LEFT": 3})
    service = CharacterDesignService(provider, storage, quality_gate=gate)
    brief = _brief()
    candidate = asyncio.run(service.generate_candidates(brief, count=1)).candidates[0]
    approval = asyncio.run(
        service.approve_candidate(brief, candidate, approved_by="Kerem")
    )

    pack = asyncio.run(service.generate_canonical_views(brief, approval))

    assert pack.status == "BLOCKED"
    # One unproducible view must not cost the run: every view that does not
    # depend on it is still rendered, measured, and shown to the human.
    assert [item.view for item in pack.drafts] == [
        "FACE_CLOSEUP",
        "FRONT",
        "PROFILE_RIGHT",
        "THREE_QUARTER_LEFT",
        "THREE_QUARTER_RIGHT",
    ]
    assert len(pack.quarantined) == 3
    assert set(pack.blocked_views or {}) == {"PROFILE_LEFT", "BACK"}
    assert "blocked_by_reference" in pack.blocked_views["BACK"][0]
    # A partial pack still carries review evidence instead of hiding it.
    assert pack.contact_sheet_storage_key != ""


def _packed_design(tmp_path, gate=None):
    """Return a service, brief, approval and a complete seven-view pack."""
    provider = FakeKeyframeGenerationProvider()
    storage = LocalFsStorage(str(tmp_path))
    _seed_pose_templates(storage)
    service = CharacterDesignService(provider, storage, quality_gate=gate)
    brief = _brief()
    candidate = asyncio.run(service.generate_candidates(brief, count=1)).candidates[0]
    approval = asyncio.run(
        service.approve_candidate(brief, candidate, approved_by="Kerem")
    )
    pack = asyncio.run(service.generate_canonical_views(brief, approval))
    provider.requests.clear()
    return service, provider, storage, brief, approval, pack


def test_a_plain_rerun_still_returns_the_pack_untouched(tmp_path):
    """The reason targeted re-render had to exist at all.

    Seeds are a pure function of the brief hash, the view index, the attempt and
    the slot, so repeating a turnaround reproduces the same frames; the pack is
    handed straight back and the GPU is never asked for anything.
    """
    service, provider, _storage, brief, approval, pack = _packed_design(tmp_path)

    again = asyncio.run(service.generate_canonical_views(brief, approval))

    assert provider.requests == []
    assert {draft.view: draft.content_hash for draft in again.drafts} == {
        draft.view: draft.content_hash for draft in pack.drafts
    }


def test_targeted_rerender_replaces_only_the_named_view(tmp_path):
    """The fake engine returns a constant image, so "a different frame was
    drawn" is asserted through the seed and the measured view -- the seed is
    exactly what selects the frame on a real engine.
    """
    gate = ScriptedViewGate()
    service, provider, storage, brief, approval, pack = _packed_design(
        tmp_path, gate=gate
    )
    gate.calls.clear()
    seed_by_view = {draft.view: draft.seed for draft in pack.drafts}

    rerendered = asyncio.run(
        service.generate_canonical_views(
            brief, approval, rerender_views=["THREE_QUARTER_RIGHT"]
        )
    )

    # Exactly one view was drawn and measured, and it is the named one.
    assert [view for view, _seed in gate.calls] == ["THREE_QUARTER_RIGHT"]
    assert len(provider.requests) == 1
    new_seed = gate.calls[0][1]
    assert new_seed not in set(seed_by_view.values())
    assert rerendered.status == "PENDING_HUMAN_REVIEW"

    # The replacement comes from an attempt block that had never been drawn.
    base_seed = int(brief.content_hash[8:16], 16)
    index = [draft.view for draft in pack.drafts].index("THREE_QUARTER_RIGHT")
    assert (new_seed - base_seed - index * 10_000) // 1_000 > (
        seed_by_view["THREE_QUARTER_RIGHT"] - base_seed - index * 10_000
    ) // 1_000
    assert {
        view: seed for view, seed in seed_by_view.items() if view != "THREE_QUARTER_RIGHT"
    } == {
        draft.view: draft.seed
        for draft in rerendered.drafts
        if draft.view != "THREE_QUARTER_RIGHT"
    }

    # The render that was replaced is kept as recorded evidence, not dropped.
    superseded = [
        item
        for item in rerendered.quarantined
        if item.reasons == ("superseded_by_targeted_rerender",)
    ]
    assert len(superseded) == 1
    assert superseded[0].view == "THREE_QUARTER_RIGHT"
    assert superseded[0].seed == seed_by_view["THREE_QUARTER_RIGHT"]
    assert asyncio.run(storage.exists(superseded[0].image_storage_key))
    assert asyncio.run(storage.exists(superseded[0].report_storage_key))


def test_a_failed_targeted_rerender_puts_the_replaced_renders_back(tmp_path, monkeypatch):
    """A half-applied re-render must not survive as a pack.

    Images are replaced as the loop reaches them and the pack manifest is
    written last, so an error in between used to leave a pack whose recorded
    hashes no longer matched its files -- a pack that then refuses to load.
    """
    gate = ScriptedViewGate()
    service, _provider, storage, brief, approval, pack = _packed_design(
        tmp_path, gate=gate
    )
    before = {draft.view: draft.content_hash for draft in pack.drafts}

    async def explode(self, **_kwargs):
        raise RuntimeError("storage died after the overwrite")

    # The compatibility facade builds a fresh generation service per call, so
    # the patch has to land on the class.
    monkeypatch.setattr(
        CharacterViewPackGenerationService, "_persist_view_pack", explode
    )

    with pytest.raises(RuntimeError, match="storage died after the overwrite"):
        asyncio.run(
            service.generate_canonical_views(
                brief, approval, rerender_views=["PROFILE_RIGHT"]
            )
        )

    for draft in pack.drafts:
        stored = asyncio.run(storage.load(draft.storage_key))
        assert hashlib.sha256(stored).hexdigest() == before[draft.view]

    # And the pack still loads: the failure left it exactly as it was.
    monkeypatch.undo()
    reloaded = asyncio.run(service.generate_canonical_views(brief, approval))
    assert {draft.view: draft.content_hash for draft in reloaded.drafts} == before


def test_targeted_rerender_refuses_views_that_are_never_drawn(tmp_path):
    """Re-drawing the front image would replace the character's identity."""
    service, _provider, _storage, brief, approval, _pack = _packed_design(tmp_path)

    with pytest.raises(ValueError, match="contract copies"):
        asyncio.run(
            service.generate_canonical_views(brief, approval, rerender_views=["FRONT"])
        )


def test_targeted_rerender_refuses_an_unknown_view(tmp_path):
    service, _provider, _storage, brief, approval, _pack = _packed_design(tmp_path)

    with pytest.raises(ValueError, match="Unknown turnaround views"):
        asyncio.run(
            service.generate_canonical_views(
                brief, approval, rerender_views=["SIDE_LEFT"]
            )
        )


def test_targeted_rerender_needs_an_existing_pack(tmp_path):
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
    with pytest.raises(ValueError, match="run a full turnaround first"):
        asyncio.run(
            service.generate_canonical_views(brief, approval, rerender_views=["BACK"])
        )
    assert provider.requests == []


class _ProvenancedKeyframeProvider(FakeKeyframeGenerationProvider):
    """The offline fake, with a frame and a provenance per request.

    Two gaps in the plain fake had to be closed before a restore could be
    tested. It returns one constant 1x1 PNG for every request, so a test could
    not tell the archived render from the render that displaced it; and it
    records no ``model_hashes`` or ``workflow_hash``, which the approval gate
    requires as proof of where a drawn view came from -- so a restore built on
    it would fail the provenance rule for the wrong reason.
    """

    @property
    def name(self) -> str:
        return "fake:keyframe"

    async def generate_keyframe(self, request):
        generated = await super().generate_keyframe(request)
        digest = hashlib.sha256(
            json.dumps(request.to_dict(), sort_keys=True).encode("utf-8")
        ).digest()
        buffer = BytesIO()
        _synthetic_studio_frame(digest).save(buffer, format="PNG")
        return replace(
            generated,
            image_bytes=buffer.getvalue(),
            metadata={
                **generated.metadata,
                "model_checkpoint": "test-model",
                "model_hashes": {"diffusion_model": "a" * 64},
                "workflow_hash": hashlib.sha256(b"test-workflow").hexdigest(),
                "render_duration_sec": 1.5,
            },
        )


def _synthetic_studio_frame(digest) -> Image.Image:
    """A subject on a studio gradient, which is what drift can be measured on.

    A flat colour has no subject mask at all -- ``Subject mask is empty`` -- so
    the frame has to look like the thing the measurement expects: a soft
    gradient with a body standing in front of it, plus one accent patch in the
    head region for the signature-mark metrics to find.
    """
    image = Image.new("RGB", (64, 64), (246, 246, 246))
    draw = ImageDraw.Draw(image)
    for row in range(64):
        draw.line([(0, row), (63, row)], fill=(240 + row // 8, 240 + row // 8, 241 + row // 8))
    body = (24 + digest[0] % 12, 26 + digest[1] % 12, 30 + digest[2] % 12)
    draw.rectangle([20, 10, 43, 61], fill=body)
    # One narrow front lock in the accent colour, inside the head region.
    draw.rectangle([24, 12, 27, 20], fill=(0xC0, 0x48, 0x38))
    return image


def _packed_design_with_manifest(tmp_path, gate=None, *, drift=None, brief=None):
    """A seven-view pack produced with the manifest a real run writes.

    ``_packed_design`` leaves the production manifest unset, which is enough
    for generation and re-rendering; a restore additionally has to prove where
    the archived bytes came from, so these tests need the real thing.
    """
    provider = _ProvenancedKeyframeProvider()
    storage = LocalFsStorage(str(tmp_path))
    _seed_pose_templates(storage)
    service = CharacterDesignService(
        provider,
        storage,
        quality_gate=gate,
        production_manifest=ProductionManifestService(tmp_path),
        drift_service=drift,
    )
    brief = brief if brief is not None else _brief()
    candidate = asyncio.run(service.generate_candidates(brief, count=1)).candidates[0]
    approval = asyncio.run(
        service.approve_candidate(brief, candidate, approved_by="Kerem")
    )
    pack = asyncio.run(service.generate_canonical_views(brief, approval))
    provider.requests.clear()
    return service, provider, storage, brief, approval, pack


def _marked_brief():
    """A brief that declares a signature mark in a colour of its own."""
    payload = _brief().to_dict()
    payload["signature_marks"] = [
        {
            "label": "single narrow deep-red front hair lock",
            "count": 1,
            "character_side": "left",
            "colour": "#C04838",
        }
    ]
    return CharacterCreationBrief.from_dict(payload)


def test_drift_evidence_is_measured_with_the_characters_own_mark_colour(tmp_path):
    """The configured accent is one deployment-wide colour.

    Measuring a red-locked character with a blue one reported no accent at all
    -- ``accent_fraction = 0.0``, every drawn view flagged ``palette_drift`` --
    which is an alarm the bytes cannot support.
    """
    drift = CharacterTurnaroundDriftService(accent_colour="#0047AB", mark_side="right")
    brief = _marked_brief()
    _service, _provider, storage, brief, approval, _pack = _packed_design_with_manifest(
        tmp_path, drift=drift, brief=brief
    )

    report = json.loads(
        asyncio.run(
            storage.load(
                f"characters/{brief.character_id}/v{approval.character_version}/drift-report.json"
            )
        ).decode("utf-8")
    )

    assert report["accent_colour"] == "#C04838"
    assert report["mark_side"] == "left"
    # Only the accent is re-aimed; the calibrated band travels over, so the
    # verdict stays comparable with the reports taken before this change.
    assert report["thresholds"] == DriftThresholds().to_dict()


def test_a_brief_without_signature_marks_keeps_the_configured_measurement(tmp_path):
    drift = CharacterTurnaroundDriftService(accent_colour="#0047AB", mark_side="right")
    _service, _provider, storage, brief, approval, _pack = _packed_design_with_manifest(
        tmp_path, drift=drift
    )

    report = json.loads(
        asyncio.run(
            storage.load(
                f"characters/{brief.character_id}/v{approval.character_version}/drift-report.json"
            )
        ).decode("utf-8")
    )

    assert report["accent_colour"] == "#0047AB"
    assert report["mark_side"] == "right"


def _rerender_then_measure(tmp_path, view="THREE_QUARTER_RIGHT"):
    """Return the service and both sides of one targeted re-render."""
    gate = ScriptedViewGate()
    service, provider, storage, brief, approval, pack = _packed_design_with_manifest(
        tmp_path, gate=gate
    )
    before = {draft.view: draft for draft in pack.drafts}
    rerendered = asyncio.run(
        service.generate_canonical_views(brief, approval, rerender_views=[view])
    )
    after = {draft.view: draft for draft in rerendered.drafts}
    return service, storage, brief, approval, before, after


def test_restore_puts_the_archived_render_back_and_files_the_displaced_one(tmp_path):
    """Seed is a pure function of the pack, so only bytes can undo a re-render."""
    service, storage, brief, approval, before, after = _rerender_then_measure(tmp_path)
    view = "THREE_QUARTER_RIGHT"
    assert after[view].content_hash != before[view].content_hash

    restored = asyncio.run(
        service.restore_superseded_views(
            brief,
            approval,
            views=[view],
            restored_by="Kerem",
            reason="the thigh pouch wrap matches the source in the archived render",
        )
    )

    by_view = {draft.view: draft for draft in restored.drafts}
    assert by_view[view].content_hash == before[view].content_hash
    assert by_view[view].seed == before[view].seed
    assert asyncio.run(storage.load(by_view[view].storage_key)) == asyncio.run(
        storage.load(before[view].storage_key)
    )
    # Every other view is untouched, byte for byte.
    for other, draft in after.items():
        if other != view:
            assert by_view[other].content_hash == draft.content_hash

    # The displaced render is kept as evidence, and so is the first archive.
    reasons = [tuple(item.reasons) for item in restored.quarantined if item.view == view]
    assert ("superseded_by_restored_render",) in reasons
    assert ("superseded_by_targeted_rerender",) in reasons
    displaced = next(
        item
        for item in restored.quarantined
        if item.reasons == ("superseded_by_restored_render",)
    )
    assert displaced.content_hash == after[view].content_hash
    assert asyncio.run(storage.exists(displaced.image_storage_key))

    # The verdict is attributed and dated, not implied.
    receipt = json.loads(
        asyncio.run(storage.load(f"characters/mira/v1/view-pack-restore.json")).decode(
            "utf-8"
        )
    )
    entry = receipt["restores"][0]
    assert entry["restored_by"] == "Kerem"
    assert "thigh pouch" in entry["reason"]
    assert entry["restored_at"].endswith("Z")
    assert entry["views"][0]["restored_seed"] == before[view].seed

    # Provenance travels with the restored bytes: an approved pack is checked
    # against the manifest, and a restore that skipped this could never be
    # approved again.
    manifest = json.loads(
        asyncio.run(storage.load("characters/mira/v1/manifest.json")).decode("utf-8")
    )
    record = next(
        item
        for item in manifest["assets"]
        if item["storage_key"] == by_view[view].storage_key
        and item["content_hash"] == by_view[view].content_hash
    )
    assert record["prompt_hash"] == by_view[view].prompt_hash
    assert record["workflow_hash"] == by_view[view].workflow_hash
    assert record["model_hashes"]
    assert record["state"] == "QC_PASSED"
    assert asyncio.run(_pack_loads(storage, brief))


async def _pack_loads(storage, brief) -> bool:
    """The pack is re-readable, which a half-applied restore would break."""
    payload = json.loads(
        (await storage.load(f"characters/{brief.character_id}/v1/view-pack.json")).decode(
            "utf-8"
        )
    )
    for draft in payload["views"]:
        data = await storage.load(draft["storage_key"])
        if hashlib.sha256(data).hexdigest() != draft["content_hash"]:
            return False
        if not draft["qc_report"]["passed"]:
            return False
    return payload["status"] == "PENDING_HUMAN_REVIEW"


def test_a_failed_restore_puts_the_displaced_render_back(tmp_path, monkeypatch):
    """Same half-applied hazard as a re-render, in the other direction."""
    service, storage, brief, approval, before, after = _rerender_then_measure(tmp_path)

    async def explode(self, **_kwargs):
        raise RuntimeError("storage died after the swap")

    monkeypatch.setattr(CharacterViewPackGenerationService, "_persist_view_pack", explode)

    with pytest.raises(RuntimeError, match="storage died after the swap"):
        asyncio.run(
            service.restore_superseded_views(
                brief, approval, views=["THREE_QUARTER_RIGHT"], restored_by="Kerem"
            )
        )

    monkeypatch.undo()
    # The pack still describes the bytes it holds, so it still loads.
    assert asyncio.run(_pack_loads(storage, brief))
    by_view = {
        draft["view"]: draft
        for draft in json.loads(
            asyncio.run(
                storage.load("characters/mira/v1/view-pack.json")
            ).decode("utf-8")
        )["views"]
    }
    assert by_view["THREE_QUARTER_RIGHT"]["content_hash"] == after[
        "THREE_QUARTER_RIGHT"
    ].content_hash
    assert before["THREE_QUARTER_RIGHT"].content_hash != by_view["THREE_QUARTER_RIGHT"][
        "content_hash"
    ]


def test_restore_refuses_a_view_that_was_never_superseded(tmp_path):
    service, _provider, _storage, brief, approval, _pack = _packed_design_with_manifest(
        tmp_path
    )

    with pytest.raises(ValueError, match="nothing to restore"):
        asyncio.run(
            service.restore_superseded_views(
                brief, approval, views=["BACK"], restored_by="Kerem"
            )
        )


def test_restore_refuses_views_that_are_never_drawn(tmp_path):
    """Re-drawing, or restoring, the front image would change the identity."""
    service, storage, brief, approval, _before, _after = _rerender_then_measure(tmp_path)

    with pytest.raises(ValueError, match="contract copies"):
        asyncio.run(
            service.restore_superseded_views(
                brief, approval, views=["FRONT"], restored_by="Kerem"
            )
        )
    assert not asyncio.run(storage.exists("characters/mira/v1/view-pack-restore.json"))


def test_restore_refuses_an_unnamed_human_or_an_empty_view_list(tmp_path):
    service, _storage, brief, approval, _before, _after = _rerender_then_measure(tmp_path)

    with pytest.raises(ValueError, match="human who decided it"):
        asyncio.run(
            service.restore_superseded_views(
                brief, approval, views=["BACK"], restored_by="   "
            )
        )
    with pytest.raises(ValueError, match="at least one view"):
        asyncio.run(
            service.restore_superseded_views(brief, approval, views=[], restored_by="Kerem")
        )


def test_restore_refuses_a_pack_that_was_already_approved(tmp_path):
    """An approval points at bytes; replacing them would leave it pointing at air."""
    service, storage, brief, approval, _before, _after = _rerender_then_measure(tmp_path)
    asyncio.run(
        storage.save(
            "characters/mira/v1/view-pack-approval.json", b'{"schema_version": 1}', "application/json"
        )
    )

    with pytest.raises(ValueError, match="already approved"):
        asyncio.run(
            service.restore_superseded_views(
                brief, approval, views=["THREE_QUARTER_RIGHT"], restored_by="Kerem"
            )
        )


def test_restore_refuses_a_pack_a_human_rejected(tmp_path):
    service, storage, brief, approval, _before, _after = _rerender_then_measure(tmp_path)
    asyncio.run(
        storage.save(
            "characters/mira/v1/view-pack-rejection.json", b'{"schema_version": 1}', "application/json"
        )
    )

    with pytest.raises(ValueError, match="rejected by a human"):
        asyncio.run(
            service.restore_superseded_views(
                brief, approval, views=["THREE_QUARTER_RIGHT"], restored_by="Kerem"
            )
        )


def test_restore_refuses_archived_bytes_that_no_longer_match(tmp_path):
    service, storage, brief, approval, _before, _after = _rerender_then_measure(tmp_path)
    payload = json.loads(
        asyncio.run(storage.load("characters/mira/v1/view-pack.json")).decode("utf-8")
    )
    archived = next(
        item
        for item in payload["quarantined"]
        if item["reasons"] == ["superseded_by_targeted_rerender"]
    )
    asyncio.run(
        storage.save(
            archived["image_storage_key"], b"not the archived render", "image/png"
        )
    )

    with pytest.raises(ValueError, match="no longer matches the hash"):
        asyncio.run(
            service.restore_superseded_views(
                brief, approval, views=["THREE_QUARTER_RIGHT"], restored_by="Kerem"
            )
        )


def test_restore_can_undo_itself_when_the_human_changes_their_mind(tmp_path):
    """The archives are an undo stack, not a one-way door.

    A restore files the frame it displaces, so the same command puts back the
    replacement -- which is the only route back once a human has looked at the
    images more closely and reversed their own verdict.
    """
    service, storage, brief, approval, before, after = _rerender_then_measure(tmp_path)
    view = "THREE_QUARTER_RIGHT"
    asyncio.run(
        service.restore_superseded_views(
            brief, approval, views=[view], restored_by="Kerem", reason="first read"
        )
    )

    again = asyncio.run(
        service.restore_superseded_views(
            brief,
            approval,
            views=[view],
            restored_by="Kerem",
            reason="closer crops changed my mind",
        )
    )

    by_view = {draft.view: draft for draft in again.drafts}
    assert by_view[view].content_hash == after[view].content_hash
    assert by_view[view].seed == after[view].seed
    assert by_view[view].content_hash != before[view].content_hash
    # Both directions are recorded, so the flip-flop is auditable.
    reasons = [
        tuple(item.reasons) for item in again.quarantined if item.view == view
    ]
    assert reasons.count(("superseded_by_targeted_rerender",)) == 1
    assert reasons.count(("superseded_by_restored_render",)) == 2
    receipt = json.loads(
        asyncio.run(
            storage.load("characters/mira/v1/view-pack-restore.json")
        ).decode("utf-8")
    )
    assert [entry["reason"] for entry in receipt["restores"]] == [
        "first read",
        "closer crops changed my mind",
    ]
    assert receipt["restores"][1]["views"][0]["archive_reason"] == [
        "superseded_by_restored_render"
    ]
    assert asyncio.run(_pack_loads(storage, brief))


def test_restore_never_reaches_for_a_render_that_failed_a_check(tmp_path):
    """Only displacement archives are candidates; a QC failure stays rejected.

    Otherwise "restore" would be a way to smuggle a frame back that the gate
    threw out on merit.
    """
    gate = ScriptedViewGate(failures={"BACK": 1})
    service, _provider, storage, brief, approval, pack = _packed_design_with_manifest(
        tmp_path, gate=gate
    )
    failed = [
        item
        for item in pack.quarantined
        if item.view == "BACK" and item.reasons == ("person_count_2",)
    ]
    assert failed, "the fixture should have quarantined a failed BACK render"
    assert asyncio.run(storage.exists(failed[0].image_storage_key))

    with pytest.raises(ValueError, match="nothing to restore"):
        asyncio.run(
            service.restore_superseded_views(
                brief, approval, views=["BACK"], restored_by="Kerem"
            )
        )


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
    character_version=1,
):
    directory = tmp_path / "acceptance"
    directory.mkdir(parents=True, exist_ok=True)
    source = directory / (
        f"{character_id or brief.character_id}-v{character_version}.json"
    )
    acceptance = CharacterAcceptanceList(
        schema_version=1,
        character_id=character_id or brief.character_id,
        character_version=character_version,
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

    # The message must name the offending character: the old generic wording
    # left the operator guessing which of the two files to fix.
    with pytest.raises(ValueError, match=r"governs character 'other', not"):
        _approve(
            service,
            brief,
            acceptance_path,
            checks=["same_facial_identity", "back_view_no_face"],
        )


def test_view_pack_approval_names_both_versions_on_mismatch(tmp_path):
    service, _storage, brief, _pack = _packed_service(tmp_path)
    acceptance_path = _acceptance_file(tmp_path, brief, character_version=2)

    with pytest.raises(ValueError) as rejected:
        _approve(
            service,
            brief,
            acceptance_path,
            checks=["same_facial_identity", "back_view_no_face"],
        )

    message = str(rejected.value)
    assert "governs character version v2" in message
    assert "pack under review is v1" in message
    assert f"{brief.character_id}-v1.json" in message


def test_blocked_view_pack_cannot_be_human_approved(tmp_path):
    provider = FakeKeyframeGenerationProvider()
    storage = LocalFsStorage(str(tmp_path))
    _seed_pose_templates(storage)
    service = CharacterDesignService(
        provider, storage, quality_gate=ScriptedViewGate({"PROFILE_LEFT": 3})
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


# ----------------------------------------------------------------------
# Provenance for views copied from an approved artifact
# ----------------------------------------------------------------------
_EDIT_VIEWS = (
    "FACE_CLOSEUP",
    "FRONT",
    "THREE_QUARTER_LEFT",
    "PROFILE_LEFT",
    "THREE_QUARTER_RIGHT",
    "PROFILE_RIGHT",
    "BACK",
)


def _provenance_fixture(tmp_path, *, front_is_a_copy: bool):
    """Build a pack whose FRONT and FACE_CLOSEUP are contract copies.

    This is the shape every pack from v5 onward had: two views are copied from
    approved artifacts, so no model ran, so their model/prompt/workflow hashes
    are empty by construction.
    """
    import hashlib

    from core.application.services.character_view_pack_approval_service import (
        CharacterViewPackApprovalService,
    )
    from core.domain.value_objects.character_design import (
        CharacterReferenceDraft,
        CharacterReferenceDraftPack,
    )

    storage = LocalFsStorage(str(tmp_path))
    root = "characters/mira/v1"
    (tmp_path / root).mkdir(parents=True, exist_ok=True)
    canonical = b"canonical-source-bytes"
    face = b"face-anchor-bytes"
    (tmp_path / f"{root}/canonical_source.png").write_bytes(canonical)
    (tmp_path / f"{root}/face_anchor.png").write_bytes(face)
    (tmp_path / f"{root}/fullbody_anchor.png").write_bytes(b"fullbody-bytes")

    def digest(payload: bytes) -> str:
        return hashlib.sha256(payload).hexdigest()

    copies = {
        "FRONT": digest(canonical) if front_is_a_copy else digest(b"an edit"),
        "FACE_CLOSEUP": digest(face),
    }
    drafts = []
    assets = []
    for view in _EDIT_VIEWS:
        payload = f"drawn-{view}".encode()
        key = f"{root}/views/{view.casefold().replace('_', '-')}.png"
        (tmp_path / key).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / key).write_bytes(payload)
        if view in copies:
            draft = CharacterReferenceDraft(
                view=view,
                storage_key=key,
                content_hash=copies[view],
                seed=1,
                width=1024,
                height=1024,
                prompt_hash="",
                workflow_hash="",
            )
            assets.append(
                {"storage_key": key, "content_hash": copies[view]}
            )
        else:
            draft = CharacterReferenceDraft(
                view=view,
                storage_key=key,
                content_hash=digest(payload),
                seed=1,
                width=992,
                height=992,
                prompt_hash="prompt-hash",
                workflow_hash="workflow-hash",
            )
            assets.append(
                {
                    "storage_key": key,
                    "content_hash": digest(payload),
                    "prompt_hash": "prompt-hash",
                    "workflow_hash": "workflow-hash",
                    "model_hashes": {"diffusion_model": "abc"},
                }
            )
        drafts.append(draft)
    (tmp_path / f"{root}/manifest.json").write_text(
        json.dumps({"schema_version": 1, "status": "PENDING", "assets": assets}),
        encoding="utf-8",
    )
    pack = CharacterReferenceDraftPack(
        schema_version=1,
        character_id="mira",
        character_version=1,
        brief_hash="b" * 64,
        canonical_storage_key=f"{root}/canonical_source.png",
        drafts=tuple(drafts),
        status="PENDING_HUMAN_REVIEW",
        contact_sheet_storage_key=f"{root}/contact-sheets/views.png",
        contact_sheet_content_hash=digest(b"sheet"),
    )
    return CharacterViewPackApprovalService(storage), root, pack, digest(face)


def test_provenance_accepts_a_view_copied_from_the_approved_source(tmp_path):
    """The unsatisfiable check that kept every pack from v5 onward unapproved."""
    service, root, pack, _face = _provenance_fixture(
        tmp_path, front_is_a_copy=True
    )

    assert asyncio.run(service._verify_view_provenance(root=root, pack=pack)) is True


def test_provenance_rejects_a_copy_claim_that_is_not_byte_identical(tmp_path):
    """A drawn view may not borrow the copy exemption."""
    service, root, pack, _face = _provenance_fixture(
        tmp_path, front_is_a_copy=False
    )

    assert asyncio.run(service._verify_view_provenance(root=root, pack=pack)) is False
