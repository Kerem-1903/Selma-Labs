from __future__ import annotations

import pytest

from core.domain.value_objects.character_view_consistency_qc import (
    HUMAN_REQUIRED_CONSISTENCY_CHECKS,
    CharacterViewConsistencyQc,
)


def test_consistency_qc_keeps_visual_identity_checks_human_required():
    evidence = CharacterViewConsistencyQc(
        contract_hash="a" * 64,
        view="PROFILE_RIGHT",
        reference_hashes=("b" * 64, "c" * 64),
        automatic_checks={
            "identity_contract_bound": True,
            "reference_chain_bound": True,
            "single_view_contract": True,
        },
    )

    assert evidence.automatic_passed is True
    assert evidence.status == "HUMAN_REVIEW_REQUIRED"
    assert evidence.to_dict()["human_required_checks"] == list(
        HUMAN_REQUIRED_CONSISTENCY_CHECKS
    )
    assert evidence.to_dict()["measurements"] == {}


def test_consistency_qc_rejects_missing_contract_hash():
    with pytest.raises(ValueError, match="identity contract hash"):
        CharacterViewConsistencyQc(
            contract_hash="",
            view="FRONT",
            reference_hashes=("a" * 64,),
            automatic_checks={"identity_contract_bound": True},
        )


def test_consistency_qc_exposes_failed_automatic_binding():
    evidence = CharacterViewConsistencyQc(
        contract_hash="a" * 64,
        view="BACK",
        reference_hashes=(),
        automatic_checks={
            "identity_contract_bound": True,
            "reference_chain_bound": False,
        },
    )

    assert evidence.automatic_passed is False
