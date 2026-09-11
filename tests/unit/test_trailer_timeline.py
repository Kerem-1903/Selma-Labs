from __future__ import annotations

import pytest

from core.domain.exceptions import PreProductionValidationError
from core.domain.value_objects.trailer_brief import TrailerBrief
from core.domain.value_objects.trailer_timeline import TrailerTimeline


def test_trailer_timeline_uses_exact_four_beat_budget():
    timeline = TrailerTimeline.from_brief(TrailerBrief(trailer_id="esik80-trailer-v1"))
    assert [(beat.start_frame, beat.end_frame) for beat in timeline.beats] == [
        (0, 912), (912, 2064), (2064, 3624), (3624, 4320)
    ]
    assert timeline.beats[0].duration_frames == 912
    assert timeline.duration_frames == 4320


def test_trailer_timeline_rejects_gaps_or_overlap():
    timeline = TrailerTimeline.from_brief(TrailerBrief(trailer_id="esik80-trailer-v1"))
    broken = timeline.to_dict()
    broken["beats"][1]["start_frame"] = 913
    with pytest.raises(PreProductionValidationError):
        TrailerTimeline.from_dict(broken)
