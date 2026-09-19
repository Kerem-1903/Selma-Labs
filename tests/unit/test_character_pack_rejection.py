"""A rejected character pack must stay rejected.

Before rejection receipts existed, a pack a human turned down stayed
``PENDING_HUMAN_REVIEW`` on disk, so a later run could still approve it. These
tests pin the rules that closed that hole: the refusal is durable, it blocks
both the approval path and the downstream guard, and it is scoped to exactly
one character version so the replacement is unaffected.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import pytest

from core.application.services.character_view_pack_approval_service import (
    CharacterViewPackApprovalService,
)
from core.domain.exceptions import PreProductionValidationError
from core.domain.value_objects.character_pack_rejection import CharacterPackRejection
from infrastructure.storage.local_fs_storage import LocalFsStorage


def _rejection(**overrides) -> CharacterPackRejection:
    payload = {
        "schema_version": 1,
        "character_id": "akira",
        "character_version": 5,
        "artifact": "VIEW_PACK",
        "reason": "Refused after human review.",
        "rejected_by": "LOQ",
        "rejected_at": datetime(2026, 9, 16, tzinfo=timezone.utc),
        "rejected_hashes": {},
    }
    payload.update(overrides)
    return CharacterPackRejection(**payload)


def test_rejection_is_bound_to_one_version_and_artifact():
    assert _rejection().storage_filename == "view-pack-rejection.json"
    assert (
        _rejection(artifact="POSE_PACK").storage_filename == "rejection.json"
    )
    assert "v5" in _rejection().refusal_message()
    assert "v6" in _rejection(superseded_by_version=6).refusal_message()


@pytest.mark.parametrize(
    "overrides",
    [
        {"schema_version": 2},
        {"artifact": "STORYBOARD"},
        {"character_version": 0},
        {"rejected_by": "   "},
        {"reason": ""},
        {"superseded_by_version": 5},
    ],
)
def test_invalid_rejection_receipts_are_refused(overrides):
    with pytest.raises(PreProductionValidationError):
        _rejection(**overrides)


def test_rejection_round_trips_through_its_serialised_form():
    rejection = _rejection(superseded_by_version=6)
    assert CharacterPackRejection.from_dict(rejection.to_dict()) == rejection


def _service(tmp_path) -> CharacterViewPackApprovalService:
    return CharacterViewPackApprovalService(LocalFsStorage(str(tmp_path)))


def test_rejected_view_pack_can_never_be_approved(tmp_path):
    service = _service(tmp_path)

    rejection = asyncio.run(
        service.reject_view_pack(
            character_id="akira",
            character_version=5,
            rejected_by="LOQ",
            reason="Refused by the workspace owner after reviewing the contact sheet.",
            superseded_by_version=6,
        )
    )
    assert rejection.artifact == "VIEW_PACK"
    assert rejection.superseded_by_version == 6
    assert (
        tmp_path / "characters/akira/v5/view-pack-rejection.json"
    ).is_file()

    with pytest.raises(ValueError, match="was rejected"):
        asyncio.run(
            service.approve_view_pack(
                character_id="akira",
                character_version=5,
                approved_by="LOQ",
            )
        )


def test_a_rejection_does_not_leak_into_the_replacement_version(tmp_path):
    service = _service(tmp_path)
    asyncio.run(
        service.reject_view_pack(
            character_id="akira",
            character_version=5,
            rejected_by="LOQ",
            reason="Refused.",
            superseded_by_version=6,
        )
    )

    assert (
        asyncio.run(
            service.load_view_pack_rejection(
                character_id="akira", character_version=6
            )
        )
        is None
    )
    # v6 has no manifest yet, so this fails on the missing pack -- proving the
    # refusal is scoped to v5 rather than blocking the character outright.
    with pytest.raises(Exception) as error:
        asyncio.run(
            service.approve_view_pack(
                character_id="akira",
                character_version=6,
                approved_by="LOQ",
            )
        )
    assert "was rejected" not in str(error.value)


def test_the_same_refusal_records_once_and_a_different_one_is_refused(tmp_path):
    service = _service(tmp_path)
    first = asyncio.run(
        service.reject_view_pack(
            character_id="akira",
            character_version=5,
            rejected_by="LOQ",
            reason="Refused.",
        )
    )
    again = asyncio.run(
        service.reject_view_pack(
            character_id="akira",
            character_version=5,
            rejected_by="LOQ",
            reason="Refused.",
        )
    )
    assert again.rejected_at == first.rejected_at

    with pytest.raises(ValueError, match="cannot be rewritten"):
        asyncio.run(
            service.reject_view_pack(
                character_id="akira",
                character_version=5,
                rejected_by="Someone else",
                reason="Actually I changed my mind.",
            )
        )

    stored = json.loads(
        (tmp_path / "characters/akira/v5/view-pack-rejection.json").read_text(
            encoding="utf-8"
        )
    )
    assert stored["rejected_by"] == "LOQ"
    assert stored["human_rejected"] is True
