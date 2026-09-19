from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image

from core.application.services.character_canonical_approval_service import (
    CharacterCanonicalApprovalService,
)
from core.application.services.character_design_service import CharacterDesignService
from core.application.services.character_pose_pack_batch_service import (
    CharacterPosePackBatchService,
)
from core.application.services.character_pose_pack_service import (
    CharacterPosePackService,
)
from core.domain.exceptions import KeyframeGenerationError
from core.domain.ports.keyframe_generation_port import KeyframeGenerationPort
from core.domain.value_objects.character_creation_brief import CharacterCreationBrief
from core.domain.value_objects.character_pose_pack import (
    POSE_PACK_HUMAN_CHECKS,
    POSE_PACK_POSE_IDS,
)
from core.domain.value_objects.character_view_qc import (
    CharacterViewObservation,
    CharacterViewQcReport,
)
from core.domain.value_objects.generated_keyframe import GeneratedKeyframe
from core.domain.value_objects.keyframe_generation_request import (
    KeyframeGenerationRequest,
)
from infrastructure.providers.keyframe.fake_keyframe_generation_provider import (
    FakeKeyframeGenerationProvider,
)
from infrastructure.storage.local_fs_storage import LocalFsStorage

ROOT = Path(__file__).parents[2]
POSE_SOURCE = ROOT / "assets" / "pose_templates"


def _brief() -> CharacterCreationBrief:
    return CharacterCreationBrief.from_dict(
        {
            "schema_version": 1,
            "name": "Mira",
            "concept": "Underground courier who manipulates sound",
            "gender_presentation": "feminine",
            "body_type": "athletic adult",
            "face": "angular face",
            "eyes": "amber eyes",
            "hair": "black bob with one red lock",
            "outfit": "cropped courier jacket and black boots",
            "props": ["folding baton"],
            "palette": ["charcoal", "burgundy"],
            "avoid": ["cape", "tattoos"],
        }
    )


class FullSizePoseProvider(KeyframeGenerationPort):
    def __init__(self, *, missing_provenance: bool = False) -> None:
        self.requests: list[KeyframeGenerationRequest] = []
        self.missing_provenance = missing_provenance
        self.image_bytes = self._image_bytes()

    @property
    def name(self) -> str:
        return "fake:pose-pack"

    async def generate_keyframe(self, request: KeyframeGenerationRequest) -> GeneratedKeyframe:
        self.requests.append(request)
        metadata = {} if self.missing_provenance else {
            "workflow_hash": hashlib.sha256(
                request.shot_contract_id.encode("utf-8")
            ).hexdigest(),
            "model_hashes": {"checkpoint": "a" * 64},
            "prompt_hash": hashlib.sha256(
                json.dumps(request.to_dict(), sort_keys=True).encode("utf-8")
            ).hexdigest(),
            "reference_content_hashes": [
                "b" * 64,
                "c" * 64,
            ],
        }
        return GeneratedKeyframe(
            image_bytes=self.image_bytes,
            content_type="image/png",
            width=768,
            height=1152,
            provider_asset_id=f"pose-{len(self.requests)}",
            metadata=metadata,
        )

    @staticmethod
    def _image_bytes() -> bytes:
        from io import BytesIO

        output = BytesIO()
        Image.new("RGB", (768, 1152), (40, 50, 60)).save(output, format="PNG")
        return output.getvalue()


def _canonical_approval(tmp_path, brief: CharacterCreationBrief):
    storage = LocalFsStorage(str(tmp_path))
    provider = FakeKeyframeGenerationProvider()
    design = CharacterDesignService(provider, storage)
    candidate = asyncio.run(design.generate_candidates(brief, count=1)).candidates[0]
    return asyncio.run(
        CharacterCanonicalApprovalService(storage).approve_candidate(
            brief, candidate, approved_by="Kerem"
        )
    )


def _style_path(tmp_path: Path) -> Path:
    path = tmp_path / "style.png"
    path.write_bytes((POSE_SOURCE / "pose_front.png").read_bytes())
    return path


def _service(tmp_path: Path, *, missing_provenance: bool = False):
    brief = _brief()
    approval = _canonical_approval(tmp_path, brief)
    storage = LocalFsStorage(str(tmp_path))
    provider = FullSizePoseProvider(missing_provenance=missing_provenance)
    service = CharacterPosePackService(provider, storage, max_attempts=1)
    return service, provider, storage, brief, approval


def test_generates_three_pose_pack_with_style_and_provenance(tmp_path):
    service, provider, storage, brief, approval = _service(tmp_path)

    manifest = asyncio.run(
        service.generate_pack(
            brief,
            approval,
            style_id="selma-production-anime-v1",
            style_reference_path=_style_path(tmp_path),
            run_id="batch-001",
        )
    )

    assert manifest.status == "PENDING_HUMAN_REVIEW"
    assert manifest.complete
    assert [pose.pose_id for pose in manifest.poses] == list(POSE_PACK_POSE_IDS)
    assert len(provider.requests) == len(POSE_PACK_POSE_IDS)
    assert all(request.width == 768 and request.height == 1152 for request in provider.requests)
    # The pose dialect chains exactly the two locked anchors and names them.
    # The SDXL production workflow owns two identity adapters, and the provider
    # selects one reference per conditioning entry, so a third unreachable
    # reference -- or an unnamed chain -- is rejected before any render.
    assert all(
        request.visual_constraints["identity_reference_weights"] == [0.75, 0.50]
        and request.visual_constraints["reference_views"] == ["FACE", "FULL_BODY"]
        and request.visual_constraints["identity_mode"] == "identity_only"
        and len(request.reference_storage_keys) == 2
        for request in provider.requests
    )
    assert asyncio.run(storage.exists(manifest.contact_sheet_storage_key))
    assert asyncio.run(storage.exists(manifest.manifest_storage_key))


def test_pose_pack_resumes_without_regenerating_completed_poses(tmp_path):
    service, provider, _storage, brief, approval = _service(tmp_path)
    first = asyncio.run(
        service.generate_pack(
            brief,
            approval,
            style_id="selma-style",
            style_reference_path=_style_path(tmp_path),
            run_id="resume-001",
        )
    )
    provider.requests.clear()

    second = asyncio.run(
        service.generate_pack(
            brief,
            approval,
            style_id="selma-style",
            style_reference_path=_style_path(tmp_path),
            run_id="resume-001",
        )
    )

    assert second == first
    assert provider.requests == []


def test_missing_real_provenance_is_quarantined_and_blocks_pack(tmp_path):
    service, provider, _storage, brief, approval = _service(
        tmp_path, missing_provenance=True
    )

    with pytest.raises(KeyframeGenerationError, match="FRONT_NEUTRAL"):
        asyncio.run(
            service.generate_pack(
                brief,
                approval,
                style_id="selma-style",
                style_reference_path=_style_path(tmp_path),
            )
        )

    assert len(provider.requests) == 1
    quarantine = list((tmp_path / "characters/mira/v1/pose-pack/quarantine").glob("*.json"))
    assert len(quarantine) == 1
    manifest = json.loads(
        (tmp_path / "characters/mira/v1/pose-pack/manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["status"] == "BLOCKED"


def test_pose_pack_approval_requires_all_checks_and_locks_manifest(tmp_path):
    service, _provider, storage, brief, approval = _service(tmp_path)
    manifest = asyncio.run(
        service.generate_pack(
            brief,
            approval,
            style_id="selma-style",
            style_reference_path=_style_path(tmp_path),
        )
    )

    with pytest.raises(ValueError, match="every human check"):
        asyncio.run(
            service.approve_pack(
                manifest_storage_key=manifest.manifest_storage_key,
                approved_by="Kerem",
                confirmed_checks=[],
            )
        )

    approved = asyncio.run(
        service.approve_pack(
            manifest_storage_key=manifest.manifest_storage_key,
            approved_by="Kerem",
            confirmed_checks=POSE_PACK_HUMAN_CHECKS,
        )
    )
    assert approved.to_dict()["human_approved"] is True
    assert asyncio.run(
        service.require_approved_pack(
            manifest_storage_key=manifest.manifest_storage_key,
            approval_storage_key="characters/mira/v1/pose-pack/approval.json",
        )
    ) == approved
    assert asyncio.run(storage.exists("characters/mira/v1/pose-pack/approval.json"))


def test_rejected_pose_pack_can_never_be_approved(tmp_path):
    service, _provider, _storage, brief, approval = _service(tmp_path)
    manifest = asyncio.run(
        service.generate_pack(
            brief,
            approval,
            style_id="selma-style",
            style_reference_path=_style_path(tmp_path),
        )
    )

    rejection = asyncio.run(
        service.reject_pack(
            manifest_storage_key=manifest.manifest_storage_key,
            rejected_by="Kerem",
            reason="Refused after reviewing the three-pose contact sheet.",
        )
    )
    assert rejection.artifact == "POSE_PACK"
    # The receipt records what was actually turned down, not just that a pack was.
    assert set(rejection.rejected_hashes) == set(POSE_PACK_POSE_IDS)

    with pytest.raises(ValueError, match="was rejected"):
        asyncio.run(
            service.approve_pack(
                manifest_storage_key=manifest.manifest_storage_key,
                approved_by="Kerem",
                confirmed_checks=POSE_PACK_HUMAN_CHECKS,
            )
        )


def test_a_pose_pack_rejected_after_approval_stops_feeding_downstream(tmp_path):
    service, _provider, _storage, brief, approval = _service(tmp_path)
    manifest = asyncio.run(
        service.generate_pack(
            brief,
            approval,
            style_id="selma-style",
            style_reference_path=_style_path(tmp_path),
        )
    )
    asyncio.run(
        service.approve_pack(
            manifest_storage_key=manifest.manifest_storage_key,
            approved_by="Kerem",
            confirmed_checks=POSE_PACK_HUMAN_CHECKS,
        )
    )
    asyncio.run(
        service.reject_pack(
            manifest_storage_key=manifest.manifest_storage_key,
            rejected_by="Kerem",
            reason="Withdrawn after approval on a second look.",
        )
    )

    with pytest.raises(ValueError, match="was rejected"):
        asyncio.run(
            service.require_approved_pack(
                manifest_storage_key=manifest.manifest_storage_key,
            )
        )


def test_production_batch_requires_style_lock_inputs(tmp_path):
    service, _provider, _storage, brief, approval = _service(tmp_path)
    brief_path = tmp_path / "brief.json"
    approval_path = tmp_path / "approval.json"
    brief_path.write_text(
        json.dumps({"character_creation_brief": brief.to_dict()}), encoding="utf-8"
    )
    approval_path.write_text(json.dumps(approval.to_dict()), encoding="utf-8")

    with pytest.raises(ValueError, match="Production batch requires"):
        asyncio.run(
            CharacterPosePackBatchService(service).run(
                [
                    {
                        "character_id": brief.character_id,
                        "brief": str(brief_path),
                        "approval": str(approval_path),
                    }
                ],
                output_manifest=tmp_path / "batch.json",
                active_series_path=tmp_path / "series.json",
            )
        )


def test_batch_records_each_character_failure_without_stopping_other_jobs(tmp_path):
    service, _provider, _storage, brief, approval = _service(tmp_path)
    jobs = [
        {
            "character_id": brief.character_id,
            "brief": str(tmp_path / "brief.json"),
            "approval": str(tmp_path / "approval.json"),
            "style_id": "selma-style",
            "style_reference": str(_style_path(tmp_path)),
        },
        {
            "character_id": "bad-character",
            "brief": str(tmp_path / "missing-brief.json"),
            "approval": str(tmp_path / "missing-approval.json"),
            "style_id": "selma-style",
            "style_reference": str(_style_path(tmp_path)),
        },
    ]
    (tmp_path / "brief.json").write_text(
        json.dumps({"character_creation_brief": brief.to_dict()}), encoding="utf-8"
    )
    (tmp_path / "approval.json").write_text(
        json.dumps(approval.to_dict()), encoding="utf-8"
    )

    payload = asyncio.run(
        CharacterPosePackBatchService(service).run(
            jobs,
            output_manifest=tmp_path / "batch.json",
        )
    )

    assert payload["status"] == "PARTIAL_FAILURE"
    assert payload["characters"][0]["status"] == "PENDING_HUMAN_REVIEW"
    assert payload["characters"][1]["status"] == "FAILED"


def test_production_pose_pack_requires_a_view_pack_approval_guard(tmp_path):
    """An absent guard must mean "no gate" loudly, never silently."""
    service, provider, _storage, brief, approval = _service(tmp_path)

    with pytest.raises(ValueError, match="view-pack approval guard"):
        asyncio.run(service.generate_pack(brief, approval, mode="PRODUCTION"))

    assert provider.requests == []


def test_production_pose_pack_is_refused_without_an_approved_view_pack(tmp_path):
    async def refusing_guard(character_id: str, character_version: int):
        raise FileNotFoundError("no approved seven-view pack")

    _service_result, provider, storage, brief, approval = _service(tmp_path)
    guarded = CharacterPosePackService(
        provider,
        storage,
        max_attempts=1,
        view_pack_approval_guard=refusing_guard,
    )

    with pytest.raises(ValueError, match="approved, unchanged seven-view pack"):
        asyncio.run(guarded.generate_pack(brief, approval, mode="PRODUCTION"))

    assert provider.requests == []


def test_production_pose_pack_asks_the_guard_for_the_exact_identity(tmp_path):
    calls: list[tuple[str, int]] = []

    async def approving_guard(character_id: str, character_version: int):
        calls.append((character_id, character_version))
        return object()

    _service_result, provider, storage, brief, approval = _service(tmp_path)
    guarded = CharacterPosePackService(
        provider,
        storage,
        max_attempts=1,
        view_pack_approval_guard=approving_guard,
    )

    # The guard is consulted for the character under review, and generation then
    # continues to the style lock -- proving the view-pack gate is a gate, not a
    # replacement for the rest of the production preconditions.
    with pytest.raises(ValueError, match="style lock"):
        asyncio.run(guarded.generate_pack(brief, approval, mode="PRODUCTION"))

    assert calls == [(brief.character_id, approval.character_version)]


def test_discovery_pose_pack_does_not_require_a_view_pack_guard(tmp_path):
    """Discovery is a pre-approval exploration; only production is gated."""
    service, provider, _storage, brief, approval = _service(tmp_path)

    manifest = asyncio.run(
        service.generate_pack(
            brief,
            approval,
            style_id="selma-style",
            style_reference_path=_style_path(tmp_path),
        )
    )

    assert manifest.complete
    assert len(provider.requests) == len(POSE_PACK_POSE_IDS)


def _approved_views(*views: str):
    from types import SimpleNamespace

    return SimpleNamespace(
        drafts=tuple(
            SimpleNamespace(
                view=view,
                storage_key=f"characters/kaito/v7/views/{view.casefold().replace('_', '-')}.png",
                content_hash=hashlib.sha256(view.encode("utf-8")).hexdigest(),
            )
            for view in views
        )
    )


def test_each_pose_is_conditioned_on_its_matching_approved_view(tmp_path):
    """The anchors always depict the front, so the front anchor pair cannot be
    the only chain: a profile or back pose conditioned on it reverts to the
    orientation the references show and ignores the pose guide."""
    service, _provider, _storage, brief, approval = _service(tmp_path)
    pack = _approved_views(
        "FRONT",
        "FACE_CLOSEUP",
        "PROFILE_LEFT",
        "PROFILE_RIGHT",
        "THREE_QUARTER_LEFT",
        "THREE_QUARTER_RIGHT",
        "BACK",
    )

    for pose_id, matched_view in CharacterPosePackService._POSE_MATCH_VIEW.items():
        references = service._pose_identity_references(pose_id, approval, pack)
        assert references is not None
        assert [reference[0] for reference in references] == [matched_view, "FACE"]
        assert references[0][2] == hashlib.sha256(matched_view.encode("utf-8")).hexdigest()
        assert references[1][2] == approval.face_anchor.content_hash

        request = service._build_request(
            brief,
            approval,
            style_key="series-style/selma/seed.png",
            style_hash="a" * 64,
            pose_id=pose_id,
            expected_view=matched_view,
            seed=7,
            approved_view_pack=pack,
        )
        assert request.visual_constraints["reference_views"] == [matched_view, "FACE"]
        assert request.visual_constraints["identity_reference_weights"] == [0.75, 0.50]
        assert len(request.reference_storage_keys) == 2


def test_pose_conditioning_never_substitutes_a_wrong_orientation(tmp_path):
    """A missing approved view falls back to the anchors; it must never be
    replaced by a view that depicts a different orientation."""
    service, _provider, _storage, brief, approval = _service(tmp_path)
    # A pack that holds the front views but not the profile ones: the profile
    # pose must decline the match rather than substituting a front view.
    partial = _approved_views("FRONT", "FACE_CLOSEUP", "THREE_QUARTER_LEFT")

    assert service._pose_identity_references("PROFILE_LEFT", approval, None) is None
    assert service._pose_identity_references("PROFILE_LEFT", approval, partial) is None
    assert (
        service._pose_identity_references("BACK_FULL_BODY", approval, partial) is None
    )
    assert (
        service._pose_identity_references("FRONT_NEUTRAL", approval, partial)
        is not None
    )

    fallback = service._build_request(
        brief,
        approval,
        style_key="series-style/selma/seed.png",
        style_hash="a" * 64,
        pose_id="PROFILE_LEFT",
        expected_view="PROFILE_LEFT",
        seed=7,
        approved_view_pack=partial,
    )
    assert fallback.visual_constraints["reference_views"] == ["FACE", "FULL_BODY"]
    assert fallback.visual_constraints["identity_reference_weights"] == [0.75, 0.50]


class _ScriptedPoseGate:
    """Fails a scripted number of renders, then passes every later one.

    Mirrors the real gate's contract: it reports reasons and never decides what
    happens next, so the service is the only place that chooses between spending
    another seed and locking the render into the pack.
    """

    _ORIENTATION = {
        "FRONT": "front",
        "THREE_QUARTER_LEFT": "three_quarter_left",
        "PROFILE_LEFT": "profile_left",
        "THREE_QUARTER_RIGHT": "three_quarter_right",
        "BACK": "back",
    }

    def __init__(self, *, fail_calls: int, reason: str = "feet_outside_frame") -> None:
        self.fail_calls = fail_calls
        self.reason = reason
        self.calls = 0

    async def evaluate(self, *, image_bytes, view, seed, signature_marks=()):
        del image_bytes, signature_marks
        self.calls += 1
        failed = self.calls <= self.fail_calls
        return CharacterViewQcReport(
            view=view,
            seed=seed,
            passed=not failed,
            reasons=(self.reason,) if failed else (),
            observation=CharacterViewObservation(
                person_count=1,
                face_count=0 if view == "BACK" else 1,
                head_inside_frame=True,
                feet_inside_frame=not failed,
                orientation=self._ORIENTATION[view],
                confidence=1.0,
                provider="scripted:pose-qc",
            ),
            framing_metrics={},
        )


def _scripted_service(tmp_path, gate: _ScriptedPoseGate, *, max_attempts: int):
    brief = _brief()
    approval = _canonical_approval(tmp_path, brief)
    storage = LocalFsStorage(str(tmp_path))
    provider = FullSizePoseProvider()
    service = CharacterPosePackService(
        provider, storage, quality_gate=gate, max_attempts=max_attempts
    )
    return service, provider, brief, approval


def test_pose_qc_failure_spends_another_seed_instead_of_locking_the_render(tmp_path):
    """A render the QC gate rejects is a seed that ignored the pose guide.

    Before this, the attempt loop accepted the first structurally valid render
    whatever the gate said, so a clipped or wrongly facing pose was locked in and
    the human approval list had to cover it. Measurable QC failures must consume
    the next attempt instead.
    """
    gate = _ScriptedPoseGate(fail_calls=1)
    service, provider, brief, approval = _scripted_service(
        tmp_path, gate, max_attempts=3
    )

    manifest = asyncio.run(
        service.generate_pack(
            brief,
            approval,
            style_id="selma-style",
            style_reference_path=_style_path(tmp_path),
            run_id="qc-retry",
        )
    )

    assert manifest.status == "PENDING_HUMAN_REVIEW"
    # Five poses, one rejected seed re-rendered: exactly one extra render.
    assert len(provider.requests) == len(POSE_PACK_POSE_IDS) + 1
    assert all(pose.qc_report["passed"] for pose in manifest.poses)
    assert len(manifest.quarantined) == 1
    assert "Pose QC failed" in manifest.quarantined[0]["reason"]
    assert gate.reason in manifest.quarantined[0]["reason"]


def test_pose_pack_blocks_when_no_seed_satisfies_the_measurable_qc(tmp_path):
    """Retrying must not become an excuse to ship: if every attempt fails the
    measurable criteria, the pack stops instead of locking a known-bad render."""
    gate = _ScriptedPoseGate(fail_calls=99)
    service, provider, brief, approval = _scripted_service(
        tmp_path, gate, max_attempts=2
    )

    with pytest.raises(KeyframeGenerationError, match="FRONT_NEUTRAL"):
        asyncio.run(
            service.generate_pack(
                brief,
                approval,
                style_id="selma-style",
                style_reference_path=_style_path(tmp_path),
                run_id="qc-blocked",
            )
        )

    assert len(provider.requests) == 2
    manifest = json.loads(
        (tmp_path / "characters/mira/v1/pose-pack/manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["status"] == "BLOCKED"
    assert manifest["poses"] == []
    assert len(manifest["quarantined"]) == 2
