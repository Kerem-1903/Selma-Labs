"""Redrawing a pose pack whose pose guide changed, in place.

A pose is bound to the guide behind it: `pose_template_hash` is copied into the
manifest and `_verify_manifest_assets` refuses the pack the moment the staged
template disagrees. That rule is right -- a pose stops being evidence once the
guide behind it is gone -- but it left no way forward for a pack that is still
unapproved, which is exactly where a corrected guide lands you. Raising the
character version is not a local option: the pose-pack root is
`v<canonical version>` and production mode requires an approved view pack at
that same version, so a bump drags a new canonical approval and a full
turnaround approval behind it.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from core.application.services.character_canonical_approval_service import (
    CharacterCanonicalApprovalService,
)
from core.application.services.character_design_service import CharacterDesignService
from core.application.services.character_pose_pack_service import (
    CharacterPosePackService,
)
from core.domain.exceptions import KeyframeGenerationError
from core.domain.value_objects.character_creation_brief import CharacterCreationBrief
from core.domain.value_objects.character_pose_pack import POSE_PACK_HUMAN_CHECKS
from core.domain.value_objects.character_view_qc import (
    CharacterViewObservation,
    CharacterViewQcReport,
)
from core.domain.value_objects.generated_keyframe import GeneratedKeyframe
from infrastructure.providers.keyframe.fake_keyframe_generation_provider import (
    FakeKeyframeGenerationProvider,
)
from infrastructure.storage.local_fs_storage import LocalFsStorage

ROOT = Path(__file__).parents[2]
POSE_SOURCE = ROOT / "assets" / "pose_templates"
GUIDE_KEY = "characters/_pose_templates/pose_profile_left.png"
MANIFEST_KEY = "characters/mira/v1/pose-pack/manifest.json"


class _VaryingPoseProvider:
    """Returns different bytes per render so a redraw is observable.

    The real dialect varies because the guide image changes; a double whose
    output never moved could not tell a redraw from a no-op, and every
    byte-level assertion here would pass vacuously.
    """

    name = "fake:pose-pack"

    def __init__(self) -> None:
        self.requests: list = []

    async def generate_keyframe(self, request) -> GeneratedKeyframe:
        self.requests.append(request)
        shade = (len(self.requests) * 37) % 200
        output = BytesIO()
        Image.new("RGB", (768, 1152), (shade, 50, 90)).save(output, format="PNG")
        return GeneratedKeyframe(
            image_bytes=output.getvalue(),
            content_type="image/png",
            width=768,
            height=1152,
            provider_asset_id=f"pose-{len(self.requests)}",
            metadata={
                "workflow_hash": hashlib.sha256(
                    request.shot_contract_id.encode("utf-8")
                ).hexdigest(),
                "model_hashes": {"checkpoint": "a" * 64},
                "prompt_hash": hashlib.sha256(
                    json.dumps(request.to_dict(), sort_keys=True).encode("utf-8")
                ).hexdigest(),
                "reference_content_hashes": ["b" * 64, "c" * 64],
            },
        )


class _FailingPoseGate:
    """Passes while the pack is drawn, then rejects the redraw.

    Arming it after the first pack matters: a gate that refused from the start
    would never get to the redraw at all, and the rollback path this covers
    would stay untested.
    """

    def __init__(self) -> None:
        self.armed = False

    async def evaluate(self, *, image_bytes, view, seed, signature_marks=()):
        del image_bytes, signature_marks
        return CharacterViewQcReport(
            view=view,
            seed=seed,
            passed=not self.armed,
            reasons=("feet_outside_frame",) if self.armed else (),
            observation=CharacterViewObservation(
                person_count=1,
                face_count=0 if view == "BACK" else 1,
                head_inside_frame=True,
                feet_inside_frame=not self.armed,
                orientation={
                    "FRONT": "front",
                    "PROFILE_LEFT": "profile_left",
                    "BACK": "back",
                }[view],
                confidence=1.0,
                provider="scripted:pose-qc",
            ),
            framing_metrics={},
        )


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


def _canonical_approval(tmp_path: Path, brief: CharacterCreationBrief):
    storage = LocalFsStorage(str(tmp_path))
    design = CharacterDesignService(FakeKeyframeGenerationProvider(), storage)
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


def _pack(tmp_path: Path, *, gate=None, max_attempts: int = 1):
    """Draw a pack, then forget the renders so a redraw is observable."""
    brief = _brief()
    approval = _canonical_approval(tmp_path, brief)
    storage = LocalFsStorage(str(tmp_path))
    provider = _VaryingPoseProvider()
    service = CharacterPosePackService(
        provider,
        storage,
        max_attempts=max_attempts,
        **({"quality_gate": gate} if gate is not None else {}),
    )
    manifest = asyncio.run(
        service.generate_pack(
            brief,
            approval,
            style_id="selma-style",
            style_reference_path=_style_path(tmp_path),
            run_id="guide-001",
        )
    )
    provider.requests.clear()
    return service, provider, storage, brief, approval, manifest


def _pretend_the_guide_moved(storage, stored_key: str, pose_id: str) -> dict:
    """Rewrite one recorded guide hash, which is exactly the stale state.

    A pack drawn before a guide correction carries the old template hash while
    the store already holds the new template. Editing the manifest reproduces
    that history without touching the repository's templates.
    """
    raw = asyncio.run(storage.load(stored_key))
    payload = json.loads(raw.decode("utf-8"))
    for pose in payload["poses"]:
        if pose["pose_id"] == pose_id:
            pose["pose_template_hash"] = "0" * 64
    asyncio.run(
        storage.save(
            stored_key,
            (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8"),
            "application/json",
        )
    )
    return payload


def test_guide_change_redraws_only_the_pose_whose_guide_moved(tmp_path):
    service, provider, storage, brief, approval, manifest = _pack(tmp_path)
    before = {pose.pose_id: pose.content_hash for pose in manifest.poses}
    staged = asyncio.run(storage.load(GUIDE_KEY))
    _pretend_the_guide_moved(storage, manifest.manifest_storage_key, "PROFILE_LEFT")

    redrawn = asyncio.run(
        service.rerender_with_changed_guide(
            brief,
            approval,
            manifest_storage_key=manifest.manifest_storage_key,
            authorized_by="Kerem",
            reason="the profile guide was redrawn at its stated angle",
        )
    )

    # Exactly one pose was drawn again, and it is the one whose guide moved.
    assert len(provider.requests) == 1
    request = provider.requests[0]
    assert request.visual_constraints["pose_storage_key"] == GUIDE_KEY
    # The recorded reference chain is reused rather than recomputed, so the
    # changed guide really is the only thing this redraw moves.
    original = next(
        pose for pose in manifest.poses if pose.pose_id == "PROFILE_LEFT"
    )
    assert request.reference_storage_keys == original.reference_storage_keys
    # This pack chained the frozen anchor pair, so it keeps that dialect's
    # labels; the provider resolves a named view by label, not by key.
    assert request.visual_constraints["reference_views"] == ["FACE", "FULL_BODY"]
    after = {pose.pose_id: pose.content_hash for pose in redrawn.poses}
    assert after["PROFILE_LEFT"] != before["PROFILE_LEFT"]
    for pose_id, digest in before.items():
        if pose_id != "PROFILE_LEFT":
            assert after[pose_id] == digest, f"{pose_id} was redrawn unasked"

    # The pack is verifiable again, which was the whole point of the command.
    entry = next(pose for pose in redrawn.poses if pose.pose_id == "PROFILE_LEFT")
    assert entry.pose_template_hash == hashlib.sha256(staged).hexdigest()
    assert entry.seed == next(
        pose.seed for pose in manifest.poses if pose.pose_id == "PROFILE_LEFT"
    ), "the recorded seed must be reused so the guide is the only variable"
    asyncio.run(service._verify_manifest_assets(redrawn))

    # The displaced bytes are kept: they are the only copy of what a human saw.
    archived = (
        tmp_path
        / "characters/mira/v1/pose-pack/quarantine"
        / (
            "profile_left-superseded_by_pose_guide_change-"
            f"{before['PROFILE_LEFT'][:12]}.png"
        )
    )
    assert archived.is_file()
    assert (
        hashlib.sha256(archived.read_bytes()).hexdigest()
        == before["PROFILE_LEFT"]
    )

    receipt = json.loads(
        (tmp_path / "characters/mira/v1/pose-pack/pose-guide-change.json").read_text(
            encoding="utf-8"
        )
    )
    assert receipt["authorized_by"] == "Kerem"
    assert receipt["reason"] == "the profile guide was redrawn at its stated angle"
    assert len(receipt["changes"]) == 1
    change = receipt["changes"][0]
    assert change["pose_id"] == "PROFILE_LEFT"
    assert change["previous_pose_hash"] == before["PROFILE_LEFT"]
    assert change["previous_template_hash"] == "0" * 64
    assert change["pose_template_hash"] == entry.pose_template_hash


def test_guide_change_refuses_when_no_guide_moved(tmp_path):
    """Otherwise this would be a way to re-roll a pose a human merely disliked."""
    service, provider, _storage, brief, approval, manifest = _pack(tmp_path)
    with pytest.raises(ValueError, match="nothing to redraw"):
        asyncio.run(
            service.rerender_with_changed_guide(
                brief,
                approval,
                manifest_storage_key=manifest.manifest_storage_key,
                authorized_by="Kerem",
                reason="trying it on",
            )
        )
    assert provider.requests == []


@pytest.mark.parametrize(
    "authorized_by, reason, message",
    [
        ("   ", "the guide moved", "named operator"),
        ("Kerem", "   ", "requires a reason"),
    ],
)
def test_guide_change_requires_a_named_operator_and_a_reason(
    tmp_path, authorized_by, reason, message
):
    service, provider, storage, brief, approval, manifest = _pack(tmp_path)
    _pretend_the_guide_moved(storage, manifest.manifest_storage_key, "PROFILE_LEFT")
    with pytest.raises(ValueError, match=message):
        asyncio.run(
            service.rerender_with_changed_guide(
                brief,
                approval,
                manifest_storage_key=manifest.manifest_storage_key,
                authorized_by=authorized_by,
                reason=reason,
            )
        )
    assert provider.requests == []


def test_guide_change_refuses_an_approved_pack(tmp_path):
    service, provider, storage, brief, approval, manifest = _pack(tmp_path)
    asyncio.run(
        service.approve_pack(
            manifest_storage_key=manifest.manifest_storage_key,
            approved_by="Kerem",
            confirmed_checks=list(POSE_PACK_HUMAN_CHECKS),
        )
    )
    _pretend_the_guide_moved(storage, manifest.manifest_storage_key, "PROFILE_LEFT")
    with pytest.raises(ValueError, match="approved pose pack cannot be redrawn"):
        asyncio.run(
            service.rerender_with_changed_guide(
                brief,
                approval,
                manifest_storage_key=manifest.manifest_storage_key,
                authorized_by="Kerem",
                reason="redraw it anyway",
            )
        )
    assert provider.requests == []


def test_guide_change_refuses_a_rejected_pack(tmp_path):
    service, provider, storage, brief, approval, manifest = _pack(tmp_path)
    asyncio.run(
        service.reject_pack(
            manifest_storage_key=manifest.manifest_storage_key,
            rejected_by="Kerem",
            reason="the poses are unusable",
        )
    )
    _pretend_the_guide_moved(storage, manifest.manifest_storage_key, "PROFILE_LEFT")
    with pytest.raises(ValueError):
        asyncio.run(
            service.rerender_with_changed_guide(
                brief,
                approval,
                manifest_storage_key=manifest.manifest_storage_key,
                authorized_by="Kerem",
                reason="redraw it anyway",
            )
        )
    assert provider.requests == []


def test_guide_change_puts_everything_back_when_the_redraw_fails(tmp_path):
    """Images first, manifest last, everything journalled.

    A half-applied redraw leaves a manifest whose hashes do not describe what is
    on disk, which is a pack that cannot be loaded at all -- the failure mode
    that had to be recovered by hand on the view-pack side.
    """
    gate = _FailingPoseGate()
    service, provider, storage, brief, approval, manifest = _pack(tmp_path, gate=gate)
    manifest_key = manifest.manifest_storage_key
    before_hashes = {pose.pose_id: pose.content_hash for pose in manifest.poses}
    _pretend_the_guide_moved(storage, manifest_key, "PROFILE_LEFT")
    stale_manifest = asyncio.run(storage.load(manifest_key))
    gate.armed = True

    with pytest.raises(KeyframeGenerationError, match="nothing was redrawn"):
        asyncio.run(
            service.rerender_with_changed_guide(
                brief,
                approval,
                manifest_storage_key=manifest_key,
                authorized_by="Kerem",
                reason="the guide was corrected",
            )
        )

    assert asyncio.run(storage.load(manifest_key)) == stale_manifest
    assert not (tmp_path / "characters/mira/v1/pose-pack/pose-guide-change.json").exists()
    for pose in manifest.poses:
        assert (
            hashlib.sha256(asyncio.run(storage.load(pose.storage_key))).hexdigest()
            == before_hashes[pose.pose_id]
        )
    # The rejected render stays on the record rather than vanishing with the
    # rollback: it is the only evidence of what the new guide produced.
    quarantine = tmp_path / "characters/mira/v1/pose-pack/quarantine"
    rejected = sorted(quarantine.glob("profile_left-attempt-1-*.bin"))
    assert len(rejected) == 1
    report = json.loads(
        (quarantine / rejected[0].name.replace(".bin", ".json")).read_text(
            encoding="utf-8"
        )
    )
    assert "feet_outside_frame" in report["reason"]
