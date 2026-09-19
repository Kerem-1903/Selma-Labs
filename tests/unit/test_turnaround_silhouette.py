"""The silhouette comparison decides whether a profile view really rotated.

It has already been used three times to answer a question about shipped packs,
and its first version was wrong: resizing each subject box to a square stretched
a tall figure horizontally and reported same-pose agreement for pairs that are
visibly different poses. These tests pin the method's properties -- height
invariance, aspect preservation, and a gap that separates same-pose pairs from
different ones -- so the next answer cannot quietly come from a stretching
artefact.
"""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image, ImageDraw

from scripts.turnaround_silhouette import (
    compare_paths,
    normalized_silhouette,
    silhouette_iou,
    subject_box,
    subject_mask,
)

_CANVAS = 400


def _studio_frame(
    path,
    *,
    size=(200, 200),
    box=(80, 40, 120, 180),
    plus=None,
    background=(244, 244, 244),
):
    """A dark subject on a light plain background, like the real renders."""
    image = Image.new("RGB", size, background)
    draw = ImageDraw.Draw(image)
    draw.rectangle(list(box), fill=(38, 40, 44))
    if plus is not None:
        draw.rectangle(list(plus), fill=(38, 40, 44))
    image.save(path)
    return path


def _square_normalized(mask: np.ndarray) -> np.ndarray:
    """The rejected method: stretch the subject box to a square, ignoring aspect."""
    left, top, right, bottom = subject_box(mask)
    tight = mask[top : bottom + 1, left : right + 1]
    resized = Image.fromarray((tight * 255).astype("uint8")).resize(
        (_CANVAS, _CANVAS), Image.NEAREST
    )
    return np.asarray(resized) > 127


def test_mask_and_box_find_the_subject_not_the_background(tmp_path):
    path = _studio_frame(tmp_path / "frame.png")

    mask = subject_mask(Image.open(path))

    assert 0.0 < mask.mean() < 0.5
    assert subject_box(mask) == (80, 40, 120, 180)


def test_an_empty_frame_is_refused_rather_than_scored(tmp_path):
    path = tmp_path / "empty.png"
    Image.new("RGB", (64, 64), (244, 244, 244)).save(path)

    with pytest.raises(ValueError, match="mask is empty"):
        subject_box(subject_mask(Image.open(path)))


def test_normalization_is_height_invariant(tmp_path):
    """The same figure at two resolutions must normalize to the same outline."""
    small = _studio_frame(tmp_path / "small.png", size=(200, 200), box=(80, 40, 120, 180))
    large = _studio_frame(tmp_path / "large.png", size=(400, 400), box=(160, 80, 240, 360))

    first = normalized_silhouette(subject_mask(Image.open(small)))
    second = normalized_silhouette(subject_mask(Image.open(large)))

    assert silhouette_iou(first, second) > 0.97


def test_a_square_resize_would_call_two_different_poses_the_same(tmp_path):
    """The regression this module exists for.

    Both figures are the same height, so stretching each subject box to a square
    makes the narrow one as wide as the wide one and scores them as one pose.
    With the aspect ratio preserved they stay distinct.
    """
    narrow = subject_mask(
        Image.open(_studio_frame(tmp_path / "narrow.png", box=(88, 40, 112, 180)))
    )
    wide = subject_mask(
        Image.open(_studio_frame(tmp_path / "wide.png", box=(40, 40, 160, 180)))
    )

    height_preserving = silhouette_iou(
        normalized_silhouette(narrow), normalized_silhouette(wide)
    )
    square = silhouette_iou(_square_normalized(narrow), _square_normalized(wide))

    assert height_preserving < 0.7
    assert square > 0.9


def test_same_pose_different_framing_scores_far_above_a_different_pose(tmp_path):
    """A shared body always overlaps; the gap is what carries the verdict."""
    reference = _studio_frame(tmp_path / "reference.png", box=(80, 40, 120, 180))
    same_pose = _studio_frame(
        tmp_path / "same.png", size=(260, 260), box=(104, 60, 156, 240)
    )
    other_pose = _studio_frame(
        tmp_path / "other.png", box=(80, 40, 120, 180), plus=(40, 120, 70, 180)
    )

    assert compare_paths(reference, same_pose) > 0.9
    assert compare_paths(reference, same_pose) > compare_paths(
        reference, other_pose
    ) + 0.1
