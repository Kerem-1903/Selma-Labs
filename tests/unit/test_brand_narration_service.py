from __future__ import annotations

import pytest

from core.application.services.brand_narration_service import BrandNarrationService
from core.domain.entities.script import Script
from core.domain.value_objects.narrative_contract import NarrativeBeat


def _script(text: str, beats: tuple[NarrativeBeat, ...] = ()) -> Script:
    return Script.create(
        topic="Octopus hearts",
        full_text=text,
        target_duration_seconds=24,
        provider_used="test",
        narrative_beats=beats,
    )


def test_signature_is_inserted_after_hook_not_before_it():
    service = BrandNarrationService("Welcome to Strange Things.")

    branded = service.apply(
        _script("An octopus has three hearts. Two pump blood to its gills.")
    )

    assert branded.full_text == (
        "An octopus has three hearts. Welcome to Strange Things. "
        "Two pump blood to its gills."
    )
    assert branded.estimated_word_count == len(branded.full_text.split())


def test_signature_is_idempotent():
    service = BrandNarrationService()
    branded = service.apply(_script("A surprising hook. The explanation follows."))

    assert service.apply(branded) == branded
    assert branded.full_text.count("Welcome to Strange Things.") == 1


def test_brand_beat_is_inserted_after_hook_and_indices_are_rebuilt():
    beats = (
        NarrativeBeat(0, "hook", "A surprising hook.", "promise"),
        NarrativeBeat(1, "evidence", "Evidence follows.", "evidence"),
        NarrativeBeat(2, "payoff", "The answer.", "answer", True),
    )

    branded = BrandNarrationService().apply(
        _script("A surprising hook. Evidence follows. The answer.", beats)
    )

    assert [beat.role for beat in branded.narrative_beats] == [
        "hook",
        "brand_signature",
        "evidence",
        "payoff",
    ]
    assert [beat.index for beat in branded.narrative_beats] == [0, 1, 2, 3]


def test_signature_rejects_long_or_empty_branding():
    with pytest.raises(ValueError, match="must not be empty"):
        BrandNarrationService("  ")
    with pytest.raises(ValueError, match="six words or fewer"):
        BrandNarrationService("one two three four five six seven")
