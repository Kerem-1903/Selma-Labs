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
    "style_line_and_shading_consistent",
    "palette_and_materials_consistent",
    "neutral_studio_background_consistent",
    "single_person_no_collage_no_text",
    "back_view_no_face",
    "profile_views_are_true_side_views",
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
    assert len(acceptance.automatic_checks) == 8
    assert "consistency_contract_bound" in acceptance.automatic_checks
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


ACCEPTANCE_DIR = REPO_ROOT / "config" / "character_acceptance"
KAITO_DOC = REPO_ROOT / "docs" / "KAITO_V1_ACCEPTANCE.md"


def test_operator_document_lists_exactly_the_machine_acceptance_checks():
    """The ritual and the gate must describe the same list of checks."""
    import re

    acceptance = load_character_acceptance(KAITO_ACCEPTANCE)
    documented = set(
        re.findall(r"--check\s+([a-z0-9_]+)", KAITO_DOC.read_text(encoding="utf-8"))
    )

    assert documented == {check.id for check in acceptance.human_checks}


def test_operator_document_names_every_required_evidence_file():
    acceptance = load_character_acceptance(KAITO_ACCEPTANCE)
    document = KAITO_DOC.read_text(encoding="utf-8")

    missing = [
        entry
        for entry in acceptance.required_evidence
        if Path(entry).name not in document
    ]

    assert missing == []


def test_version_bound_acceptance_files_do_not_diverge():
    """One character, one policy: only ``character_version`` may differ.

    Kaito's acceptance list is duplicated per version because the gate binds a
    list to exactly one version. That duplication is only safe while the copies
    stay identical; this test is what keeps a future edit from updating one file
    and silently leaving the other behind.
    """
    import json

    files = sorted(ACCEPTANCE_DIR.glob("kaito-v*.json"))
    assert len(files) >= 2, "expected at least one per-version copy beside v1"

    payloads = {path: json.loads(path.read_text(encoding="utf-8")) for path in files}
    baseline_path, baseline = next(iter(payloads.items()))
    reference = {
        key: value for key, value in baseline.items() if key != "character_version"
    }

    for path, payload in payloads.items():
        assert payload["character_version"] == int(
            path.stem.rsplit("-v", 1)[1]
        ), f"{path.name} must declare the version in its own filename"
        assert {
            key: value for key, value in payload.items() if key != "character_version"
        } == reference, f"{path.name} diverged from {baseline_path.name}"


def test_acceptance_lists_bind_to_the_locked_kaito_brief():
    """Every version copy must name the brief the lineage was locked against.

    There is more than one Kaito brief on disk (iterations plus a benchmark
    brief), and they hash differently.``kaito.json`` is the one the approved
    canonical image and the live acceptance list are bound to; binding a new
    acceptance copy to a different brief would make the turnaround refuse to
    start, or worse, approve a package that was rendered from another brief.
    """
    import json

    from core.domain.value_objects.character_creation_brief import (
        CharacterCreationBrief,
    )

    payload = json.loads(
        (
            REPO_ROOT / "assets" / "character_creation_briefs" / "kaito.json"
        ).read_text(encoding="utf-8")
    )
    brief = CharacterCreationBrief.from_dict(
        payload.get("character_creation_brief", payload)
    )

    for path in sorted(ACCEPTANCE_DIR.glob("kaito-v*.json")):
        acceptance = load_character_acceptance(path)
        assert acceptance.character_id == "kaito"
        assert acceptance.brief_hash == brief.content_hash, (
            f"{path.name} is bound to another brief; re-lock the lineage or "
            f"review which brief the turnaround will run with"
        )
