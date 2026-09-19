from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from PIL import Image

from core.application.services.character_canonical_approval_service import (
    CharacterCanonicalApprovalService,
)
from core.application.services.character_design_service import CharacterDesignService
from core.domain.value_objects.character_creation_brief import CharacterCreationBrief
from infrastructure.providers.keyframe.fake_keyframe_generation_provider import (
    FakeKeyframeGenerationProvider,
)
from infrastructure.storage.local_fs_storage import LocalFsStorage


def _brief() -> CharacterCreationBrief:
    return CharacterCreationBrief.from_dict(
        {
            "schema_version": 1,
            "name": "Provided Hero",
            "concept": "A quiet courier",
            "gender_presentation": "masculine",
            "body_type": "adult athletic",
            "face": "angular anime face",
            "hair": "short black hair",
            "outfit": "charcoal jacket and black boots",
            "style_preset": "selma-anime-v1",
        }
    )


def _image(path: Path) -> None:
    Image.new("RGB", (768, 1152), "gray").save(path, format="PNG")


def test_supplied_image_becomes_one_unapproved_candidate_without_provider_generation(tmp_path):
    image = tmp_path / "provided.png"
    _image(image)
    provider = FakeKeyframeGenerationProvider()
    storage = LocalFsStorage(str(tmp_path / "storage"))
    service = CharacterDesignService(provider, storage)

    pack = asyncio.run(service.import_candidate(_brief(), image, run_id="provided-001"))

    assert len(pack.candidates) == 1
    candidate = pack.candidates[0]
    assert candidate.source_type == "PROVIDED_IMAGE"
    assert candidate.provider == "human:provided-image"
    assert provider.requests == []
    assert candidate.storage_key.endswith("/candidates/provided-" + candidate.content_hash[:12] + ".png")


def test_provided_image_requires_explicit_brief_consistency_confirmation_before_lock(tmp_path):
    image = tmp_path / "provided.png"
    _image(image)
    storage = LocalFsStorage(str(tmp_path / "storage"))
    service = CharacterDesignService(FakeKeyframeGenerationProvider(), storage)
    brief = _brief()
    candidate = asyncio.run(service.import_candidate(brief, image)).candidates[0]
    approval_service = CharacterCanonicalApprovalService(storage)

    with pytest.raises(ValueError, match="brief"):
        asyncio.run(approval_service.approve_candidate(brief, candidate, approved_by="reviewer"))

    approval = asyncio.run(
        approval_service.approve_candidate(
            brief,
            candidate,
            approved_by="reviewer",
            brief_consistency_confirmed=True,
        )
    )

    assert approval.identity_source == "PROVIDED_IMAGE"
    assert approval.identity_source_hash == approval.canonical_content_hash
    assert approval.brief_consistency_confirmed is True
    assert approval.identity_contract_hash
