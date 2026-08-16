import pytest

from core.application.services.hook_variant_scoring_service import (
    HookVariantScoringService,
)
from core.domain.exceptions import NarrativeQualityError


def test_hook_variants_are_ranked_and_experiment_changes_only_opening_hook():
    experiment = HookVariantScoringService().prepare_experiment(
        topic="Self-healing materials",
        variants=[
            "Self-healing materials exist.",
            "What if a material could seal its own wounds?",
            "You won't believe this insane truth.",
        ],
    )

    assert experiment.principal_variable == "opening_hook"
    assert experiment.selected.text == "What if a material could seal its own wounds?"
    assert experiment.selected.score >= 11
    assert experiment.control.text == "Self-healing materials exist."
    assert experiment.experiment_id.startswith("hook-")


def test_hook_experiment_fails_when_every_candidate_is_weak():
    with pytest.raises(NarrativeQualityError, match="No hook variant"):
        HookVariantScoringService().prepare_experiment(
            topic="Self-healing materials",
            variants=["Interesting topic.", "Learn more today."],
        )
