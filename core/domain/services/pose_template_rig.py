"""Yaw-projected OpenPose rig behind the canonical view templates.

The turnaround has no structural conditioning of its own: the FLUX.2 edit graph
carries text plus up to three `ReferenceLatent` images and nothing that can hold
a camera angle (see `docs/REJECTED_APPROACHES.md` for the lineage that tried).
That makes the pose templates the only place a view's angle is ever stated in
pixels -- which is why they have to be right.

They were not. The previous generator put the two profiles **and** the two
three-quarters into one code path that collapsed the skeleton toward the body
midline, and then widened the shoulders for a three-quarter with
``r_shoulder = cx + tq - 0.02`` / ``l_shoulder = cx - tq + 0.02`` -- an offset
that *narrows* the pair instead of widening it. Measured as shoulder width over
body height: front 0.167, profile 0.047, three-quarter 0.039. A true
45-degree template has to sit near ``0.167 * cos 45 = 0.118``, so the
three-quarter templates came out narrower than the profiles they sit beside.

This module replaces the special cases with one rig in three dimensions and one
orthographic projection, so every view's width follows ``cos(yaw)`` by
construction and no per-view fudge can reintroduce the collapse.

Frame: ``x`` is image-right at the front view, ``y`` runs top to bottom as a
fraction of the frame, ``z`` is depth with the face at positive ``z``. A view is
a rotation of the body about the vertical axis through the midline; the camera
stays put:

    screen_x = x * cos(yaw) + z * sin(yaw)
    screen_y = y

so ``yaw = 0`` is the front, ``+90`` turns the character's right side to the
camera (nose to image right) and ``-90`` their left.

``project`` returns *body-centred* coordinates: the midline is ``x = 0`` and the
values are signed. Frame coordinates -- what a renderer needs -- come from
``project_frame``, which adds :data:`MIDLINE`. Skipping that offset puts most
joints at negative pixel columns, off the left edge of the canvas, where they
still produce a plausible-looking strip of colour that is not a skeleton.
"""

from __future__ import annotations

import math

#: Yaw in degrees per canonical view. Positive turns the character's right side
#: toward the camera, which puts the nose on the image right.
VIEW_YAW: dict[str, float] = {
    "FRONT": 0.0,
    "PROFILE_RIGHT": 90.0,
    "BACK": 180.0,
    "PROFILE_LEFT": -90.0,
}

#: Horizontal centre of the frame. Body-centred coordinates are shifted by this
#: much to become frame coordinates.
MIDLINE = 0.5

#: Half the shoulder-to-shoulder distance at the front view. Every other view is
#: this value times ``cos(yaw)``; the tests assert exactly that, so a per-view
#: special case cannot come back.
SHOULDER_HALF_WIDTH = 0.085

#: The rig, in the frame described in the module docstring. Depths are small on
#: purpose: they only have to make a side view read as a stance (feet staggered,
#: face forward of the neck) rather than a single vertical line. Arms are given
#: slightly different depths so that in a profile the two arm lines stay
#: distinguishable instead of collapsing onto each other exactly.
_RIG: dict[str, tuple[float, float, float]] = {
    "head": (0.000, 0.115, 0.020),
    "neck": (0.000, 0.205, 0.010),
    "r_shoulder": (-SHOULDER_HALF_WIDTH, 0.225, 0.000),
    "l_shoulder": (SHOULDER_HALF_WIDTH, 0.225, 0.000),
    "r_elbow": (-0.115, 0.345, 0.020),
    "l_elbow": (0.115, 0.345, 0.010),
    "r_wrist": (-0.125, 0.455, 0.030),
    "l_wrist": (0.125, 0.455, 0.020),
    "r_hip": (-0.055, 0.500, 0.000),
    "l_hip": (0.055, 0.500, 0.000),
    "r_knee": (-0.060, 0.700, -0.015),
    "l_knee": (0.060, 0.700, 0.015),
    "r_ankle": (-0.070, 0.915, -0.030),
    "l_ankle": (0.070, 0.915, 0.030),
    "r_eye": (-0.022, 0.105, 0.035),
    "l_eye": (0.022, 0.105, 0.035),
    "r_ear": (-0.040, 0.115, 0.005),
    "l_ear": (0.040, 0.115, 0.005),
}

#: COCO-18 limb pairs, drawn in the official OpenPose colours by the renderer.
LIMBS: tuple[tuple[str, str], ...] = (
    ("neck", "head"),
    ("neck", "r_shoulder"),
    ("neck", "l_shoulder"),
    ("r_shoulder", "r_elbow"),
    ("r_elbow", "r_wrist"),
    ("l_shoulder", "l_elbow"),
    ("l_elbow", "l_wrist"),
    ("neck", "r_hip"),
    ("neck", "l_hip"),
    ("r_hip", "r_knee"),
    ("r_knee", "r_ankle"),
    ("l_hip", "l_knee"),
    ("l_knee", "l_ankle"),
    ("neck", "r_eye"),
    ("r_eye", "r_ear"),
    ("neck", "l_eye"),
    ("l_eye", "l_ear"),
)

JOINTS: tuple[str, ...] = tuple(_RIG)


def project(view: str) -> dict[str, tuple[float, float]]:
    """Return the joint positions of one view in normalized frame coordinates."""
    if view not in VIEW_YAW:
        raise KeyError(f"Unknown canonical view: {view}")
    yaw = math.radians(VIEW_YAW[view])
    cos_yaw, sin_yaw = math.cos(yaw), math.sin(yaw)
    return {
        name: (x * cos_yaw + z * sin_yaw, y)
        for name, (x, y, z) in _RIG.items()
    }


def project_frame(view: str) -> dict[str, tuple[float, float]]:
    """Return the joint positions of one view in 0..1 frame coordinates."""
    return {
        name: (MIDLINE + x, y) for name, (x, y) in project(view).items()
    }


def shoulder_separation(view: str) -> float:
    """Return the shoulder-to-shoulder distance a view must project to."""
    return 2.0 * SHOULDER_HALF_WIDTH * abs(
        math.cos(math.radians(VIEW_YAW[view]))
    )


#: Views whose two eyes must collapse onto the facing edge of the head, which is
#: how a side view is written in the COCO-18 convention.
PROFILE_VIEWS: tuple[str, ...] = ("PROFILE_LEFT", "PROFILE_RIGHT")


__all__ = [
    "JOINTS",
    "LIMBS",
    "MIDLINE",
    "PROFILE_VIEWS",
    "SHOULDER_HALF_WIDTH",
    "VIEW_YAW",
    "project",
    "project_frame",
    "shoulder_separation",
]
