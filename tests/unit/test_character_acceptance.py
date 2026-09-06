from __future__ import annotations

from pathlib import Path

import pytest

from core.domain.exceptions import PreProductionValidationError
from core.domain.value_objects.character_acceptance import (
    CharacterAcceptanceList,
    CharacterHumanCheck,
    acceptance_file_digest,
    load_character_acceptance,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
KAITO_ACCEPTANCE = REPO_ROOT / "config" / "character_acceptance" / "kaito-v1.json"

EXPECTED_KAITO_CHECKS = {
    "same_facial_identity",
    "hair_black_single_cobalt_streak",
    "streak_character_left_never_mirrored",
    "bag_character_right_never_mirrored",
    "outfit_layers_consistent",
    "body_proportions_consistent",
    "single_person_no_collage_no_text",
    "back_view_no_face",
}


def _list(
    checks: tuple[tuple[str, str], ...] = (("face_match", "same face"),),
    character_id: str = "kaito",
    character_version: int = 1,
    brief_hash: str = "a" * 64,
    evidence: tuple[str, ...] = ("view-pack.json",),
) -> CharacterAcceptanceList:
    return CharacterAcceptanceList(
        schema_version=1,
        character_id=character_id,
        character_version=character_version,
        brief_hash=brief_hash,
        blocking_policy="All checks must pass.",
        automatic_checks=("exactly_one_person",),
        human_checks=tuple(
            CharacterHumanCheck(id=check_id, label=label)
            for check_id, label in checks
        ),
        required_evidence=evidence,
    )


def test_kaito_acceptance_file_parses_with_expected_checks_and_hash_binding():
    acceptance = load_character_acceptance(KAITO_ACCEPTANCE)

    assert acceptance.schema_version == 1
    assert acceptance.character_id == "kaito"
    assert acceptance.character_version == 1
    assert (
        acceptance.brief_hash
        == "7a398fec879cb66ffe3e77abae918a3f7c519f7e47a7280633adf6b5b0cd8fb8"
    )
    assert {check.id for check in acceptance.human_checks} == EXPECTED_KAITO_CHECKS
    assert len(acceptance.automatic_checks) == 7
    assert "view-pack-approval.json" in acceptance.required_evidence
    assert len(acceptance_file_digest(KAITO_ACCEPTANCE)) == 64


def test_acceptance_round_trips_through_dict():
    acceptance = _list(
        checks=(
            ("same_facial_identity", "same face"),
            ("back_view_no_face", "no face in back view"),
        ),
        evidence=("view-pack.json", "contact-sheets/views.png"),
    )

    restored = CharacterAcceptanceList.from_dict(acceptance.to_dict())

    assert restored == acceptance
    assert restored.content_hash() == acceptance.content_hash()


def test_acceptance_rejects_duplicate_human_check_ids():
    with pytest.raises(PreProductionValidationError, match="unique"):
        _list(checks=(("face_match", "same face"), ("face_match", "other face")))


def test_acceptance_rejects_empty_human_checks():
    with pytest.raises(PreProductionValidationError, match="at least one"):
        _list(checks=())


def test_acceptance_rejects_plain_text_human_check_item():
    payload = _list().to_dict()
    payload["human_checks"] = ["same facial identity in all seven views"]
    with pytest.raises(PreProductionValidationError, match="id and label"):
        CharacterAcceptanceList.from_dict(payload)


def test_acceptance_rejects_portable_id_violations():
    with pytest.raises(PreProductionValidationError, match="portable id"):
        _list(checks=(("bag side/right", "bag side"),))


def test_acceptance_rejects_evidence_escaping_version_root():
    with pytest.raises(PreProductionValidationError, match="inside"):
        _list(evidence=("../secrets.json",))
    with pytest.raises(PreProductionValidationError, match="inside"):
        _list(evidence=("/etc/passwd",))


def test_acceptance_rejects_bad_schema_version_and_missing_brief_hash():
    payload = _list().to_dict()
    payload["schema_version"] = 2
    with pytest.raises(PreProductionValidationError, match="schema_version"):
        CharacterAcceptanceList.from_dict(payload)

    payload = _list().to_dict()
    payload["brief_hash"] = ""
    with pytest.raises(PreProductionValidationError, match="brief_hash"):
        CharacterAcceptanceList.from_dict(payload)


def test_loader_rejects_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_character_acceptance(tmp_path / "nope.json")
