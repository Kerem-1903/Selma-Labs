from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image

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
                "d" * 64,
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
    return asyncio.run(design.approve_candidate(brief, candidate, approved_by="Kerem"))


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


def test_generates_five_pose_pack_with_style_and_provenance(tmp_path):
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
    assert len(provider.requests) == 5
    assert all(request.width == 768 and request.height == 1152 for request in provider.requests)
    assert all(
        request.visual_constraints["style_seed_weight"] == 0.20
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
