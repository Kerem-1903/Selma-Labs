"""Silhouette comparison for turnaround views: is this the same pose?

Two renders of the same character cannot be compared by pixels when they came
from different seeds and were framed differently. They can be compared by
outline once scale is removed: threshold the subject against the background,
normalize for height, centre on the subject's own centroid, and intersect.

The trap this module exists to avoid: resizing the subject box to a *square*
stretches a tall figure horizontally by three or four times and inflates
agreement between any two tall figures. An early version of this measurement
did that and reported same-pose agreement for pairs that are visibly different
poses. Everything here preserves the aspect ratio.

A shared body means even genuinely different angles overlap somewhat, so a
number is only meaningful next to a baseline: `cross_view_baselines` returns
the pairs that must *not* agree, and a same-wing pair that scores near the
baseline is a real rotation, while one that scores far above it is a copy of
the reference pose.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

#: Sum of per-channel distance from the sampled background. On the studio
#: renders the subject is ~11% of the frame from 140 through 260, so the mask
#: is stable across this range; 190 sits safely inside it.
MASK_THRESHOLD = 190

#: Canvas the normalized silhouettes are drawn onto.
CANVAS = 400


def subject_mask(image: Image.Image, *, threshold: int = MASK_THRESHOLD) -> np.ndarray:
    """Boolean mask of the character, from a background sampled at the corners."""
    array = np.asarray(image.convert("RGB"), dtype=np.int16)
    height, width, _ = array.shape
    corner = max(1, min(height, width) // 12)
    background = np.median(
        np.concatenate(
            [
                array[:corner, :corner].reshape(-1, 3),
                array[:corner, -corner:].reshape(-1, 3),
                array[-corner:, :corner].reshape(-1, 3),
                array[-corner:, -corner:].reshape(-1, 3),
            ]
        ),
        axis=0,
    )
    return np.abs(array - background).sum(axis=2) > threshold


def subject_box(mask: np.ndarray) -> tuple[int, int, int, int]:
    """Bounding box of the masked subject, as (left, top, right, bottom)."""
    rows = np.where(mask.any(axis=1))[0]
    columns = np.where(mask.any(axis=0))[0]
    if rows.size == 0 or columns.size == 0:
        raise ValueError("Subject mask is empty; check the input framing.")
    return int(columns[0]), int(rows[0]), int(columns[-1]), int(rows[-1])


def normalized_silhouette(
    mask: np.ndarray, *, canvas: int = CANVAS
) -> np.ndarray:
    """The subject's outline at a fixed height, centred, aspect preserved."""
    left, top, right, bottom = subject_box(mask)
    tight = mask[top : bottom + 1, left : right + 1]
    height, width = tight.shape
    scaled_width = max(1, int(round(width * canvas / height)))
    scaled = Image.fromarray((tight * 255).astype("uint8")).resize(
        (scaled_width, canvas), Image.NEAREST
    )
    array = np.asarray(scaled) > 127
    canvas_shape = np.zeros((canvas, canvas), dtype=bool)
    _rows, columns = np.where(array)
    offset = canvas // 2 - int(round(columns.mean()))
    if offset >= 0:
        canvas_shape[:, offset : offset + scaled_width] = array[:, : canvas - offset]
    else:
        canvas_shape[:, :canvas] = array[:, -offset : -offset + canvas]
    return canvas_shape


def silhouette_iou(first: np.ndarray, second: np.ndarray) -> float:
    """Intersection over union of two normalized silhouettes."""
    union = (first | second).sum()
    if union == 0:
        raise ValueError("Both silhouettes are empty.")
    return float((first & second).sum() / union)


def compare_paths(first, second) -> float:
    """Convenience wrapper for two image paths."""
    return silhouette_iou(
        normalized_silhouette(subject_mask(Image.open(first))),
        normalized_silhouette(subject_mask(Image.open(second))),
    )
