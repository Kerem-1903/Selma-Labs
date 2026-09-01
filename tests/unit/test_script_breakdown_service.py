from __future__ import annotations

import pytest

from core.application.services.script_breakdown_service import ScriptBreakdownService


def test_breakdown_creates_deterministic_unapproved_dialogue_and_action_shots():
    service = ScriptBreakdownService()
    script = """
    INT. ABANDONED HOSPITAL
    AKIRA: I remember this corridor.
    A red emergency light flickers above the sealed door.

    SCENE: ROOFTOP
    DOCTOR: They can send memories back to you.
    """

    shots = service.parse_script(script, "broken-record")

    assert [shot.id for shot in shots] == [
        "broken-record-shot-001",
        "broken-record-shot-002",
        "broken-record-shot-003",
    ]
    assert shots[0].dialogue == "I remember this corridor."
    assert shots[0].metadata["line_type"] == "dialogue"
    assert shots[1].metadata["line_type"] == "action"
    assert shots[2].metadata["line_type"] == "offscreen_dialogue"
    assert shots[0].requires_lipsync is True
    assert shots[1].requires_lipsync is False
    assert shots[2].requires_lipsync is False
    assert shots[0].scene_plan_id == "broken-record-scene-001"
    assert shots[2].scene_plan_id == "broken-record-scene-002"
    assert all(shot.keyframe_approved is False for shot in shots)
    assert all("akira_girl" in shot.prompt for shot in shots)


def test_breakdown_rejects_empty_script_and_unsafe_identifier():
    service = ScriptBreakdownService()

    with pytest.raises(ValueError, match="must not be empty"):
        service.parse_script("  ", "pilot")
    with pytest.raises(ValueError, match="storage-safe"):
        service.parse_script("Akira walks.", "../pilot")
