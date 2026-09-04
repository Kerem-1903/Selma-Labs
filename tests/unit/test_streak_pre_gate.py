from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw

from core.application.services.streak_pre_gate import (
    HEAD_DOMINANT_VIEWS,
    StreakPreGate,
)
from core.domain.entities.character_bible import CharacterBible

APPROVED_ANCHOR = (
    Path(__file__).parents[2]
    / "assets"
    / "characters"
    / "akira"
    / "identity_lock"
    / "v2"
    / "akira-canonical-anchor-v2.png"
)


def _anchor_bytes() -> bytes:
    return APPROVED_ANCHOR.read_bytes()


def _anchor_with_left_blob() -> bytes:
    """Anchor plus a second red component on the viewer-left inside the head zone."""
    image = Image.open(io.BytesIO(_anchor_bytes())).convert("RGB")
    draw = ImageDraw.Draw(image)
    draw.ellipse((334, 240, 386, 320), fill="#C04838")  # left of midline 490.5
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _synthetic_streak(size: int) -> bytes:
    """Black frame with one red bar at the calibrated root, drawn in fractions."""
    mark = CharacterBible.akira().identity_constraints.structured_marks[0]
    image = Image.new("RGB", (size, size), (20, 20, 20))
    draw = ImageDraw.Draw(image)
    left, top, right, bottom = (value * size for value in mark.head_bbox)
    root_x = left + mark.anchor.x_center * (right - left)
    root_y = top + mark.anchor.y_root * (bottom - top)
    half = max(4.0, size * 0.012)
    draw.rectangle(
        (root_x - half, root_y, root_x + half, root_y + size * 0.24),
        fill=mark.color_hex,
    )
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_applicable_only_for_true_closeups():
    # FRONT recipes render chest-up; the calibrated close-up zone spills onto
    # the torso and reads the jacket lining as extra streak components.
    assert StreakPreGate.applicable_for("FACE_CLOSEUP") is True
    for view in ("FRONT", "BACK", "FULL_BODY", "PROFILE_LEFT", "PROFILE_RIGHT",
                 "THREE_QUARTER_LEFT", "UPPER_BODY", "ACTION_RUNNING"):
        assert StreakPreGate.applicable_for(view) is False
    assert HEAD_DOMINANT_VIEWS == frozenset({"FACE_CLOSEUP"})


def test_real_anchor_passes_the_streak_gate():
    result = StreakPreGate().evaluate(_anchor_bytes(), CharacterBible.akira().identity_constraints.structured_marks[0])

    assert result.applicable is True
    assert result.passed is True
    assert result.reason.startswith("single-streak check passed")
    assert result.report.detected_count == 1
    assert result.report.actual_side == "viewer_right"


def test_mirrored_streak_fails_the_streak_gate():
    result = StreakPreGate().evaluate(_anchor_with_left_blob(), CharacterBible.akira().identity_constraints.structured_marks[0])

    assert result.applicable is True
    assert result.passed is False
    assert "component_count" in result.report.failures
    assert "mirror_exclusivity" in result.report.failures
    assert result.reason.startswith("single-streak check failed")


def test_calibrated_zone_scales_to_any_resolution():
    gate = StreakPreGate()
    mark = CharacterBible.akira().identity_constraints.structured_marks[0]
    for size in (1024, 768, 512):
        result = gate.evaluate(_synthetic_streak(size), mark)
        assert result.applicable is True
        assert result.passed is True, f"size {size}: {result.reason}"
        assert result.report.detected_count == 1


def test_mark_without_calibration_is_not_applicable():
    mark = CharacterBible.akira().identity_constraints.structured_marks[0]
    bare = mark.__class__(
        id=mark.id,
        label=mark.label,
        color_hex=mark.color_hex,
        viewer_side=mark.viewer_side,
        count=mark.count,
        color_tolerance_delta_e=mark.color_tolerance_delta_e,
        anchor=mark.anchor,
        mirror_side=mark.mirror_side,
        shape_grammar=mark.shape_grammar,
        enforcement=mark.enforcement,
    )
    assert bare.head_bbox is None
    result = StreakPreGate().evaluate(_anchor_bytes(), bare)

    assert result.applicable is False
    assert result.passed is None
    assert "no calibrated head bbox" in result.reason


def test_calibrated_mark_picks_the_sealed_streak_mark():
    mark = StreakPreGate.calibrated_mark(CharacterBible.akira())

    assert mark is not None
    assert mark.id == "akira-red-streak"
    assert mark.head_bbox == (0.3105, 0.1670, 0.6475, 0.5947)
