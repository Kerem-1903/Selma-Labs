from __future__ import annotations

import io
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from cli.main import build_parser
from core.application.services.character_turnaround_drift_service import (
    CharacterTurnaroundDriftService,
    DriftThresholds,
    load_drift_thresholds,
)

ROOT = Path(__file__).parents[2]
CALIBRATED = (
    ROOT / "config" / "character_acceptance" / "kaito-drift-thresholds-v1.json"
)

BACKDROP = (240, 240, 240)
SUBJECT = (60, 60, 60)
COBALT = (0, 71, 171)

# Subject box inside a 200x300 canvas: the head band is the top 18% (y 40..79).
_WIDTH, _HEIGHT = 200, 300


def _png(*, accent_columns: int = 2, accent_rows: int = 25, tint: int = 0) -> bytes:
    """Render a synthetic turnaround frame: flat backdrop, one blocky subject."""
    array = np.full((_HEIGHT, _WIDTH, 3), BACKDROP, dtype=np.uint8)
    array[40:261, 60:141] = np.clip(
        np.array(SUBJECT, dtype=np.int16) + tint, 0, 255
    ).astype(np.uint8)
    if accent_columns:
        array[45 : 45 + accent_rows, 95 : 95 + accent_columns] = COBALT
    buffer = io.BytesIO()
    Image.fromarray(array).save(buffer, format="PNG")
    return buffer.getvalue()


def _service(**overrides) -> CharacterTurnaroundDriftService:
    kwargs = {"accent_colour": "#0047AB", "mark_side": "left", **overrides}
    return CharacterTurnaroundDriftService(**kwargs)


def test_matching_view_is_within_tolerance():
    report = _service().evaluate(
        source_bytes=_png(), views={"PROFILE_LEFT": _png()}
    )

    assert report["status"] == "WITHIN_TOLERANCE"
    assert report["views"][0]["reasons"] == []
    assert report["views"][0]["metrics"]["head_accent_ratio"] == 1.0


def test_lost_signature_mark_is_flagged_on_a_visible_side_view():
    report = _service().evaluate(
        source_bytes=_png(accent_columns=2),
        views={"PROFILE_LEFT": _png(accent_columns=0)},
    )

    assert report["status"] == "DRIFT_FLAGGED"
    view = report["views"][0]
    assert view["mark_expectation"] == "visible"
    assert "signature_mark_missing_or_hidden" in view["reasons"]


def test_mark_conjured_onto_the_far_side_is_flagged_as_mirrored():
    report = _service().evaluate(
        source_bytes=_png(accent_columns=1, accent_rows=5),
        views={"PROFILE_RIGHT": _png(accent_columns=6, accent_rows=25)},
    )

    view = report["views"][0]
    assert view["mark_expectation"] == "hidden"
    assert "signature_mark_mirrored_onto_visible_side" in view["reasons"]


def _png_with_streak(*, streak_pixels: int) -> bytes:
    """A larger frame, so a handful of pixels really is below the floor.

    The 200x300 fixture above has a head region of only ~3.2k pixels, so even a
    single accent pixel clears the measured-density floor. This fixture keeps
    the same blocky subject on a 400x800 canvas where the head band is ~17.4k
    pixels and three stray pixels sit under it.
    """
    width, height = 400, 800
    array = np.full((height, width, 3), BACKDROP, dtype=np.uint8)
    array[120:721, 120:281] = SUBJECT
    for index in range(streak_pixels):
        array[130 + index // 20, 150 + index % 20] = COBALT
    buffer = io.BytesIO()
    Image.fromarray(array).save(buffer, format="PNG")
    return buffer.getvalue()


def test_a_source_without_a_measurable_streak_disables_the_mark_check():
    """Three anti-aliased edge pixels are not a signature mark.

    Without this gate the metric reads silhouette noise as a streak and then
    reports the approved source against itself as missing its own mark, which
    is exactly what made the v6 drift report unusable.
    """
    report = _service().evaluate(
        source_bytes=_png_with_streak(streak_pixels=3),
        views={"PROFILE_LEFT": _png_with_streak(streak_pixels=0)},
    )

    view = report["views"][0]
    assert view["mark_measurable"] is False
    assert report["source_metrics"]["mark_measurable"] is False
    assert view["reasons"] == []
    assert report["status"] == "WITHIN_TOLERANCE"


def test_a_real_streak_keeps_the_mark_check_armed():
    report = _service().evaluate(
        source_bytes=_png_with_streak(streak_pixels=60),
        views={"PROFILE_LEFT": _png_with_streak(streak_pixels=0)},
    )

    view = report["views"][0]
    assert view["mark_measurable"] is True
    assert "signature_mark_missing_or_hidden" in view["reasons"]


def test_back_view_never_expects_a_front_hair_mark():
    report = _service().evaluate(
        source_bytes=_png(accent_columns=2),
        views={"BACK": _png(accent_columns=0)},
    )

    view = report["views"][0]
    assert view["mark_expectation"] == "hidden"
    assert view["reasons"] == []


def test_unknown_mark_side_disables_mark_judgements_only():
    report = _service(mark_side="").evaluate(
        source_bytes=_png(accent_columns=2),
        views={"PROFILE_LEFT": _png(accent_columns=0)},
    )

    view = report["views"][0]
    assert view["mark_expectation"] is None
    assert not any(reason.startswith("signature_mark") for reason in view["reasons"])


def test_palette_and_subject_drift_are_flagged():
    report = _service(mark_side="").evaluate(
        source_bytes=_png(),
        views={"FRONT_ALT": _png(tint=90)},
    )

    assert "palette_drift" in report["views"][0]["reasons"]


def _png_at(width: int, height: int) -> bytes:
    array = np.full((height, width, 3), BACKDROP, dtype=np.uint8)
    array[40 : height - 39, 60:141] = SUBJECT
    buffer = io.BytesIO()
    Image.fromarray(array).save(buffer, format="PNG")
    return buffer.getvalue()


def test_a_different_canvas_aspect_is_named_instead_of_blamed_on_the_character():
    """Frame arithmetic must not read as character drift.

    The box metrics are normalized by frame size. On the v6 pack the square
    source and the portrait views had matching absolute subject heights and a
    13-point normalized delta -- a flag with nothing wrong behind it.
    """
    report = _service(mark_side="").evaluate(
        source_bytes=_png_at(200, 300),
        views={"PROFILE_LEFT": _png_at(200, 200)},
    )

    view = report["views"][0]
    assert view["canvas_comparable"] is False
    assert view["reasons"][0] == "canvas_aspect_mismatch"
    assert report["summary"]["canvas_comparable"] is False
    assert report["source_metrics"]["canvas"] == [200, 300]
    assert view["canvas"] == [200, 200]


def test_a_matching_canvas_keeps_the_measurement_clean():
    report = _service().evaluate(
        source_bytes=_png_at(200, 300),
        views={"PROFILE_LEFT": _png_at(200, 300)},
    )

    view = report["views"][0]
    assert view["canvas_comparable"] is True
    assert "canvas_aspect_mismatch" not in view["reasons"]
    assert report["summary"]["canvas_comparable"] is True


def test_report_is_explicitly_advisory():
    report = _service().evaluate(
        source_bytes=_png(), views={"PROFILE_LEFT": _png()}
    )

    assert report["advisory_only"] is True
    assert "never approve" in report["approval_policy"]


def test_calibration_widens_observed_spread_but_keeps_a_usable_floor():
    thresholds = _service().calibrate(
        source_bytes=_png(), views={"PROFILE_LEFT": _png()}, margin=1.35
    )

    assert thresholds.subject_height_ratio_delta == pytest.approx(0.02)
    assert thresholds.palette_distance == pytest.approx(0.05)
    assert thresholds.mark_presence_ratio == 0.35

    with pytest.raises(ValueError, match="margin"):
        _service().calibrate(source_bytes=_png(), views={"A": _png()}, margin=0.5)


def test_evaluation_requires_at_least_one_view():
    with pytest.raises(ValueError, match="at least one view"):
        _service().evaluate(source_bytes=_png(), views={})


def test_unreadable_input_is_rejected():
    with pytest.raises(ValueError, match="not a readable image"):
        _service().evaluate(source_bytes=b"nope", views={"PROFILE_LEFT": _png()})


def test_accent_colour_and_mark_side_are_validated():
    with pytest.raises(ValueError, match="mark_side"):
        CharacterTurnaroundDriftService(mark_side="sideways")
    with pytest.raises(ValueError, match="#RRGGBB"):
        CharacterTurnaroundDriftService(accent_colour="cobalt")


def test_calibrated_kaito_thresholds_file_is_readable():
    thresholds = DriftThresholds.from_dict(
        json.loads(CALIBRATED.read_text(encoding="utf-8"))
    )

    assert thresholds.mark_presence_ratio == 0.35
    assert thresholds.subject_height_ratio_delta == pytest.approx(0.02)
    assert thresholds.palette_distance > 0.0


def test_loader_returns_the_calibrated_band_with_its_provenance():
    band, source = load_drift_thresholds(CALIBRATED)

    assert band.subject_height_ratio_delta == pytest.approx(0.02)
    assert len(source["sha256"]) == 64
    assert source["path"].endswith("kaito-drift-thresholds-v1.json")
    assert source["character_id"] == "kaito"
    assert "observed spread" in source["calibration_method"]


def test_loader_fails_closed_instead_of_falling_back_to_defaults(tmp_path):
    with pytest.raises(ValueError, match="unreadable"):
        load_drift_thresholds(tmp_path / "missing.json")

    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="not valid JSON"):
        load_drift_thresholds(broken)

    array = tmp_path / "array.json"
    array.write_text("[]", encoding="utf-8")
    with pytest.raises(TypeError, match="object"):
        load_drift_thresholds(array)


def test_calibrated_band_is_stricter_than_the_builtin_defaults():
    """The silent downgrade the loader exists to prevent."""
    band, _source = load_drift_thresholds(CALIBRATED)
    defaults = DriftThresholds()

    assert band.palette_distance < defaults.palette_distance
    assert band.line_density_ratio_delta < defaults.line_density_ratio_delta
    assert band.accent_fraction_delta < defaults.accent_fraction_delta
    # The mark band is deliberately *not* calibrated: the reference pack is
    # where the streak was lost, so calibrating against it would bake the
    # defect in. It must stay identical to the fixed default.
    assert band.mark_presence_ratio == defaults.mark_presence_ratio
    assert band.mark_mirror_ratio == defaults.mark_mirror_ratio


def test_report_records_which_band_produced_the_verdict():
    band, source = load_drift_thresholds(CALIBRATED)
    service = _service(thresholds=band, threshold_source=source)

    report = service.evaluate(source_bytes=_png(), views={"FRONT": _png()})

    assert report["thresholds"]["palette_distance"] == pytest.approx(
        band.palette_distance
    )
    assert report["threshold_source"]["sha256"] == source["sha256"]
    assert (
        report["threshold_source"]["calibration_method"]
        == source["calibration_method"]
    )


def test_builtin_band_is_used_when_no_calibration_is_configured():
    report = _service().evaluate(source_bytes=_png(), views={"FRONT": _png()})

    assert report["thresholds"] == DriftThresholds().to_dict()
    assert report["threshold_source"] == {}


def test_cli_defers_to_the_configured_identity_when_flags_are_omitted(tmp_path):
    arguments = build_parser().parse_args(
        [
            "character",
            "drift-report",
            "--source",
            str(tmp_path / "source.png"),
            "--pack",
            str(tmp_path / "pack"),
        ]
    )

    # ``None`` (not "") separates "omitted" from an explicit opt-out, so the
    # handler can fall back to the configured accent and side. An empty default
    # made every mark check silently disappear from the default run.
    assert arguments.mark_side is None
    assert arguments.accent_colour is None


def test_cli_accepts_the_drift_report_command(tmp_path):
    arguments = build_parser().parse_args(
        [
            "character",
            "drift-report",
            "--source",
            str(tmp_path / "source.png"),
            "--pack",
            str(tmp_path / "pack"),
            "--accent-colour",
            "#0047AB",
            "--mark-side",
            "left",
            "--output",
            str(tmp_path / "drift.json"),
        ]
    )

    assert arguments.character_command == "drift-report"
    assert arguments.mark_side == "left"
    assert arguments.calibrate is False
