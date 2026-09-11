from __future__ import annotations

import pytest

from core.domain.exceptions import PreProductionValidationError
from core.domain.value_objects.trailer_brief import TrailerBrief


def test_trailer_brief_locks_creative_decisions_and_exact_duration():
    brief = TrailerBrief(trailer_id="esik80-trailer-v1")
    assert brief.duration_frames == 4320
    assert brief.narrator_enabled is False
    assert brief.system_voice_id == "MNEMOS"
    assert brief.allowed_reveals == ("FHD-80", "LIMEN")
    assert "Varga responsibility" in brief.hidden_reveals
    assert TrailerBrief.from_dict(brief.to_dict()) == brief


@pytest.mark.parametrize("field,value", [("fps", 30), ("duration_seconds", 179), ("narrator_enabled", True)])
def test_trailer_brief_rejects_unlocked_production_decisions(field, value):
    with pytest.raises(PreProductionValidationError):
        TrailerBrief(trailer_id="esik80-trailer-v1", **{field: value})
