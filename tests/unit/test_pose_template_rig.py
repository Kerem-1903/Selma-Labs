"""Guards for the yaw-projected pose templates.

The defect these pin down: the old generator put the profiles and the
three-quarters in one branch and then moved the three-quarter shoulders inward
instead of outward, so the three-quarter templates rendered *narrower* than the
profiles. That is moot now: the two three-quarter templates were removed, because
a 45-degree skeleton read as a near-frontal body and the pose pack is better
served by front, profile and back alone. Two independent checks still guard what
remains: the projection itself, and the rendered pixels.
"""

from __future__ import annotations

import hashlib
import json
import math
import pathlib

import pytest
from PIL import Image

from core.domain.services.pose_template_rig import (
    PROFILE_VIEWS,
    SHOULDER_HALF_WIDTH,
    VIEW_YAW,
    project,
    shoulder_separation,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]
SOURCE_DIR = ROOT / "assets" / "pose_templates"
CATALOG = SOURCE_DIR / "catalog.json"

#: The measurement band, as a fraction of the subject's own height, that covers
#: the shoulders. Everything below it is arm and leg, which a skeleton draws as
#: near-vertical lines and which would flatten the difference between views.
SHOULDER_BAND = (0.13, 0.20)


def _rig_module():
    import scripts.make_pose_templates as module

    return module


def _skeleton_band_width(image: Image.Image, *, band: tuple[float, float]) -> float:
    """Return a band's horizontal extent over the skeleton's own height.

    Deliberately independent of the production silhouette helper: these
    templates are pure black with saturated limbs, so "not black" is the exact
    subject mask and a bug in the shared helper cannot hide a bad template.
    """
    pixels = image.convert("RGB").load()
    width, height = image.size
    rows = [
        y
        for y in range(height)
        if any(pixels[x, y] != (0, 0, 0) for x in range(width))
    ]
    assert rows, "template is blank"
    top, bottom = rows[0], rows[-1]
    span = bottom - top
    start = top + int(band[0] * span)
    end = top + int(band[1] * span)
    columns = [
        x
        for y in range(start, max(end, start + 1))
        for x in range(width)
        if pixels[x, y] != (0, 0, 0)
    ]
    assert columns, "shoulder band is empty"
    return (max(columns) - min(columns)) / span


@pytest.mark.parametrize("view", sorted(VIEW_YAW))
def test_projected_shoulders_follow_the_cos_law(view: str) -> None:
    joints = project(view)
    measured = abs(joints["l_shoulder"][0] - joints["r_shoulder"][0])
    expected = 2.0 * SHOULDER_HALF_WIDTH * abs(
        math.cos(math.radians(VIEW_YAW[view]))
    )
    assert measured == pytest.approx(expected, abs=1e-9)
    assert measured == pytest.approx(shoulder_separation(view), abs=1e-9)


def test_front_and_back_carry_the_same_width() -> None:
    front = project("FRONT")
    back = project("BACK")
    assert abs(front["l_shoulder"][0] - front["r_shoulder"][0]) == pytest.approx(
        abs(back["l_shoulder"][0] - back["r_shoulder"][0]), abs=1e-9
    )
    assert shoulder_separation("FRONT") == pytest.approx(0.170, abs=1e-9)


def test_three_quarter_views_are_no_longer_projected() -> None:
    """A 45-degree skeleton read as a near-frontal body, so the two three-quarter
    templates were removed. A guide that cannot exist must not be reachable."""
    assert set(VIEW_YAW) == {"FRONT", "PROFILE_RIGHT", "BACK", "PROFILE_LEFT"}
    for view in ("THREE_QUARTER_LEFT", "THREE_QUARTER_RIGHT"):
        assert view not in VIEW_YAW
        with pytest.raises(KeyError):
            project(view)


@pytest.mark.parametrize("view", PROFILE_VIEWS)
def test_profile_collapses_the_eyes_onto_the_facing_edge(view: str) -> None:
    joints = project(view)
    assert joints["r_eye"][0] == pytest.approx(joints["l_eye"][0], abs=1e-9)
    # A right profile faces image right, a left profile image left, and the face
    # plane sits at positive depth, so the projection's sign is the check.
    facing = 1.0 if view.endswith("RIGHT") else -1.0
    assert math.copysign(1.0, joints["l_eye"][0]) == facing
    # The feet still stagger front-to-back, which is what makes the side view
    # read as a stance instead of a single vertical line.
    assert abs(joints["r_ankle"][0] - joints["l_ankle"][0]) > 0.05


@pytest.mark.parametrize("view", ["FRONT", "BACK"])
def test_drawn_views_do_not_collapse(view: str) -> None:
    module = _rig_module()
    width = _skeleton_band_width(module.render(view), band=SHOULDER_BAND)
    assert width > 0.10, f"{view} renders as a side view (band width {width:.3f})"


@pytest.mark.parametrize("view", PROFILE_VIEWS)
def test_drawn_profiles_are_the_narrowest(view: str) -> None:
    module = _rig_module()
    profile = _skeleton_band_width(module.render(view), band=SHOULDER_BAND)
    front = _skeleton_band_width(module.render("FRONT"), band=SHOULDER_BAND)
    assert profile < front


def test_shipped_templates_match_the_catalog() -> None:
    module = _rig_module()
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    listed = {
        str(item.get("filename")): str(item.get("sha256"))
        for item in [*catalog.get("templates", []), *catalog.get("aliases", [])]
        if isinstance(item, dict)
    }
    for view, filename in module.FILES.items():
        path = SOURCE_DIR / filename
        assert path.is_file(), f"{filename} is missing"
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert listed.get(filename) == digest, f"{filename} disagrees with the catalog"
        assert digest == hashlib.sha256(module.png_bytes(module.render(view))).hexdigest(), (
            f"{filename} was not produced by the yaw rig"
        )
    alias = module.BACK_ALIAS
    assert (SOURCE_DIR / alias).read_bytes() == (SOURCE_DIR / module.FILES["BACK"]).read_bytes()
    assert listed.get(alias) == hashlib.sha256((SOURCE_DIR / alias).read_bytes()).hexdigest()
