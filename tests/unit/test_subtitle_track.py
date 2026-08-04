"""
Unit tests for the SubtitleTrack entity and SubtitleCue value object.

Pure data-shape tests, same style as test_timeline_service.py's
inline coverage of Timeline.to_dict(). SubtitleTrack deliberately exposes
no to_srt()/to_vtt() -- see test_subtitle_formatter.py for that coverage.
"""
from __future__ import annotations

from core.domain.entities.subtitle_track import SubtitleTrack
from core.domain.value_objects.subtitle_cue import SubtitleCue


def _cue(index: int, scene_index: int, start: float, end: float, text: str = "Hello.") -> SubtitleCue:
    return SubtitleCue(index=index, scene_index=scene_index, start_time=start, end_time=end, text=text)


def test_create_assigns_id_and_created_at():
    track = SubtitleTrack.create(scene_plan_id="plan-1", cues=[])
    assert track.id
    assert track.scene_plan_id == "plan-1"
    assert track.created_at is not None


def test_total_duration_is_the_last_cues_end_time():
    cues = [
        _cue(1, 0, 0.0, 3.0),
        _cue(2, 1, 3.0, 9.5),
    ]
    track = SubtitleTrack.create(scene_plan_id="plan-1", cues=cues)
    assert track.total_duration_seconds == 9.5


def test_total_duration_defaults_to_zero_for_empty_cues():
    track = SubtitleTrack.create(scene_plan_id="plan-1", cues=[])
    assert track.total_duration_seconds == 0.0


def test_to_dict_includes_all_cue_fields():
    cues = [_cue(1, 0, 0.0, 3.0, text="A ship sails.\nAt night.")]
    track = SubtitleTrack.create(scene_plan_id="plan-1", cues=cues)

    data = track.to_dict()

    assert data["scene_plan_id"] == "plan-1"
    assert data["total_duration_seconds"] == 3.0
    assert len(data["cues"]) == 1
    cue_data = data["cues"][0]
    assert cue_data["index"] == 1
    assert cue_data["scene_index"] == 0
    assert cue_data["start_time"] == 0.0
    assert cue_data["end_time"] == 3.0
    assert cue_data["text"] == "A ship sails.\nAt night."


def test_subtitle_track_has_no_format_methods():
    """SubtitleTrack must remain format-agnostic -- see module docstring
    and SubtitleFormatter's own docstring for the full reasoning. This
    test exists specifically to catch a future regression that
    accidentally re-adds to_srt()/to_vtt() to the entity."""
    track = SubtitleTrack.create(scene_plan_id="plan-1", cues=[])
    assert not hasattr(track, "to_srt")
    assert not hasattr(track, "to_vtt")


def test_subtitle_cue_is_frozen():
    cue = _cue(1, 0, 0.0, 1.0)
    try:
        cue.text = "changed"  # type: ignore[misc]
        assert False, "SubtitleCue must be immutable"
    except Exception:
        pass
